from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.llm_client import OpenRouterClient  # noqa: E402
from app.services.scoring_service import deterministic_score_payload, score_rubric_text  # noqa: E402

HERE = Path(__file__).resolve().parent
GOLDEN_PATH = HERE / "golden.jsonl"
MODELS_PATH = HERE / "models.json"
RESULTS_CSV = HERE / "results.csv"
RESULTS_FULL = HERE / "results_full.jsonl"
RESULTS_MD = HERE / "results.md"

STATUSES = {"ok", "check_fail", "api_error"}
MAX_TOKENS_BY_TASK = {"score": 900, "enrich": 700, "memo": 1_800}
NUMBER_PATTERN = re.compile(r"(?<![\w.])[$]?\d+(?:,\d{3})*(?:\.\d+)?%?(?![\w.])")
KEY_URL_PATTERN = re.compile(r"https?://\S*/keys/\S+")
USER_ID_PATTERN = re.compile(r"\buser_[A-Za-z0-9]{8,}\b")


@dataclass
class EvalResult:
    model: str
    example_id: str
    task: str
    run: int
    status: str
    passed: bool
    strict_parse: bool | None
    expected: str
    actual: str
    full_actual: str
    resolved_model: str | None
    provider: str | None
    latency_ms: int | None
    cost: float | None
    error: str | None
    ungrounded_numbers: str


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_models(path: Path) -> list[str]:
    with path.open() as handle:
        data = json.load(handle)
    return ["deterministic", *list(data["models"])]


def _prompt(example: dict[str, Any]) -> tuple[str, str]:
    task = example["task"]
    payload = json.dumps(example["input"], sort_keys=True)
    if task == "score":
        system = (
            "You score commercial real-estate deals. Return only JSON with keys "
            "score, risk_level, and breakdown. Score must be 0-100. risk_level "
            "must be low for score >= 70, medium for score >= 40 and < 70, "
            f"otherwise high. Use this rubric exactly: {score_rubric_text()}. "
            "For each breakdown item return max and earned."
        )
        return system, f"Score this deal JSON:\n{payload}"
    if task == "enrich":
        system = (
            "You enrich commercial real-estate deal records. Return only JSON with "
            "property_type, units, sq_ft, year_built, asking_price, address, city, "
            "state, zip_code. Preserve known values. Use null when evidence is missing."
        )
        return system, f"Enrich this deal JSON:\n{payload}"
    if task == "memo":
        system = (
            "You are BuildSignals' real-estate investment memo analyst. Return only "
            "markdown. Include Executive Summary, Property Overview, Risk Assessment, "
            "and Recommendation. Do not invent unavailable facts."
        )
        return system, f"Generate a concise memo from this deal JSON:\n{payload}"
    raise ValueError(f"Unsupported task: {task}")


def _parse_json(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
        raise


def _strict_parse(content: str, task: str) -> bool | None:
    if task not in {"score", "enrich"}:
        return None
    try:
        json.loads(content)
    except json.JSONDecodeError:
        return False
    return True


def _score(example: dict[str, Any], content: str) -> bool:
    expected = example["expected"]
    task = example["task"]
    if task in {"score", "enrich"}:
        actual = _parse_json(content)
        if not isinstance(actual, dict):
            return False
        for key, expected_value in expected.items():
            if key == "breakdown":
                for factor, fields in expected_value.items():
                    breakdown = actual.get("breakdown", {})
                    if not isinstance(breakdown, dict):
                        return False
                    actual_factor = breakdown.get(factor, {})
                    if not isinstance(actual_factor, dict):
                        return False
                    for field, field_value in fields.items():
                        if actual_factor.get(field) != field_value:
                            return False
            elif actual.get(key) != expected_value:
                return False
        return True
    if task == "memo":
        lowered = content.casefold()
        return all(fragment.casefold() in lowered for fragment in expected["contains"])
    raise ValueError(f"Unsupported task: {task}")


def _expected_text(example: dict[str, Any]) -> str:
    return json.dumps(example["expected"], sort_keys=True)


def _truncate(value: str, limit: int = 500) -> str:
    compact = value.replace("\n", "\\n")
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def redact_sensitive_text(value: str) -> str:
    redacted = KEY_URL_PATTERN.sub("[REDACTED_KEY_URL]", value)
    redacted = USER_ID_PATTERN.sub("user_[REDACTED]", redacted)
    return redacted.replace("'user_[REDACTED]':", "'user_id':")


def _number_variants(value: str) -> set[str]:
    stripped = value.strip()
    base = stripped.replace("$", "").replace(",", "").rstrip("%")
    variants = {stripped, base}
    try:
        numeric = float(base)
    except ValueError:
        return {variant for variant in variants if variant}
    if numeric.is_integer():
        integer = str(int(numeric))
        variants.add(integer)
        variants.add(f"{int(numeric):,}")
        variants.add(f"${int(numeric):,}")
        variants.add(f"{integer}.0")
        variants.add(f"{integer}.00")
    variants.add(f"{numeric}")
    return {variant for variant in variants if variant}


def _input_numbers(value: Any) -> set[str]:
    numbers: set[str] = set()
    if isinstance(value, bool) or value is None:
        return numbers
    if isinstance(value, (int, float)):
        numbers.update(_number_variants(str(value)))
        return numbers
    if isinstance(value, str):
        for match in NUMBER_PATTERN.findall(value):
            numbers.update(_number_variants(match))
        return numbers
    if isinstance(value, dict):
        for child in value.values():
            numbers.update(_input_numbers(child))
        return numbers
    if isinstance(value, list):
        for child in value:
            numbers.update(_input_numbers(child))
    return numbers


def _ungrounded_numbers(example: dict[str, Any], content: str) -> str:
    if example["task"] != "memo":
        return ""
    grounded = _input_numbers(example["input"])
    ungrounded: list[str] = []
    for match in NUMBER_PATTERN.findall(content):
        if not (_number_variants(match) & grounded) and match not in ungrounded:
            ungrounded.append(match)
    return json.dumps(ungrounded)


def _deterministic_content(example: dict[str, Any]) -> str:
    if example["task"] == "score":
        return json.dumps(deterministic_score_payload(example["input"]), sort_keys=True)
    if example["task"] == "enrich":
        return json.dumps(example["input"], sort_keys=True)
    input_data = example["input"]
    return "\n".join(
        [
            "## Executive Summary",
            str(input_data.get("name", "Unknown")),
            str(input_data.get("city", "Unknown")),
            str(input_data.get("property_type", "Unknown")),
            "## Recommendation",
        ]
    )


def _result_from_content(
    *,
    model: str,
    example: dict[str, Any],
    run: int,
    expected: str,
    content: str,
    resolved_model: str | None,
    provider: str | None,
    latency_ms: int | None,
    cost: float | None,
) -> EvalResult:
    passed = _score(example, content)
    return EvalResult(
        model=model,
        example_id=example["id"],
        task=example["task"],
        run=run,
        status="ok" if passed else "check_fail",
        passed=passed,
        strict_parse=_strict_parse(content, example["task"]),
        expected=expected,
        actual=_truncate(content),
        full_actual=content,
        resolved_model=resolved_model,
        provider=provider,
        latency_ms=latency_ms,
        cost=cost,
        error=None,
        ungrounded_numbers=_ungrounded_numbers(example, content),
    )


def _run_one(client: OpenRouterClient, model: str, example: dict[str, Any], run: int) -> EvalResult:
    system, user = _prompt(example)
    expected = _expected_text(example)
    if model == "deterministic":
        return _result_from_content(
            model=model,
            example=example,
            run=run,
            expected=expected,
            content=_deterministic_content(example),
            resolved_model="deterministic",
            provider="local",
            latency_ms=0,
            cost=0,
        )
    try:
        response = client.chat_completion(
            primary_model=model,
            fallback_models=[],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            max_tokens=MAX_TOKENS_BY_TASK[example["task"]],
            response_format={"type": "json_object"} if example["task"] in {"score", "enrich"} else None,
        )
        return _result_from_content(
            model=model,
            example=example,
            run=run,
            expected=expected,
            content=response.content,
            resolved_model=response.served_model,
            provider=response.provider,
            latency_ms=response.latency_ms,
            cost=response.cost,
        )
    except Exception as exc:  # noqa: BLE001 - benchmark should record provider/model failures.
        return EvalResult(
            model=model,
            example_id=example["id"],
            task=example["task"],
            run=run,
            status="api_error",
            passed=False,
            strict_parse=None,
            expected=expected,
            actual="",
            full_actual="",
            resolved_model=None,
            provider=None,
            latency_ms=None,
            cost=None,
            error=redact_sensitive_text(f"{exc.__class__.__name__}: {exc}"),
            ungrounded_numbers="",
        )


def _write_csv(results: list[EvalResult]) -> None:
    with RESULTS_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            lineterminator="\n",
            fieldnames=[
                "model",
                "example_id",
                "task",
                "run",
                "status",
                "passed",
                "strict_parse",
                "expected",
                "actual",
                "resolved_model",
                "provider",
                "latency_ms",
                "cost",
                "error",
                "ungrounded_numbers",
            ],
        )
        writer.writeheader()
        for result in results:
            row = asdict(result)
            row.pop("full_actual")
            writer.writerow(row)


def _write_full_jsonl(results: list[EvalResult]) -> None:
    with RESULTS_FULL.open("w") as handle:
        for result in results:
            handle.write(json.dumps(asdict(result), sort_keys=True) + "\n")


def _read_existing_results() -> list[EvalResult]:
    if not RESULTS_CSV.exists():
        return []
    rows = []
    with RESULTS_CSV.open() as handle:
        for row in csv.DictReader(handle):
            status = row.get("status") or ("api_error" if row.get("error") else "check_fail")
            rows.append(
                EvalResult(
                    model=row["model"],
                    example_id=row["example_id"],
                    task=row["task"],
                    run=int(row.get("run") or 1),
                    status=status if status in STATUSES else "check_fail",
                    passed=str(row.get("passed")).lower() == "true",
                    strict_parse=(
                        None
                        if row.get("strict_parse") in {None, ""}
                        else str(row.get("strict_parse")).lower() == "true"
                    ),
                    expected=row.get("expected") or "",
                    actual=row.get("actual") or "",
                    full_actual="",
                    resolved_model=row.get("resolved_model") or None,
                    provider=row.get("provider") or None,
                    latency_ms=int(row["latency_ms"]) if row.get("latency_ms") else None,
                    cost=float(row["cost"]) if row.get("cost") else None,
                    error=row.get("error") or None,
                    ungrounded_numbers=row.get("ungrounded_numbers") or "",
                )
            )
    return rows


def _percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * pct))
    return ordered[index]


def _summary_row(rows: list[EvalResult]) -> tuple[int, int, float, float]:
    scored_rows = [row for row in rows if row.status in {"ok", "check_fail"}]
    passed = sum(1 for row in scored_rows if row.passed)
    accuracy = passed / len(scored_rows) if scored_rows else 0
    api_error_rate = sum(1 for row in rows if row.status == "api_error") / len(rows) if rows else 0
    return passed, len(scored_rows), accuracy, api_error_rate


def _write_markdown(results: list[EvalResult]) -> None:
    by_model_task: dict[tuple[str, str], list[EvalResult]] = {}
    by_model_example: dict[tuple[str, str], list[EvalResult]] = {}
    for result in results:
        by_model_task.setdefault((result.model, result.task), []).append(result)
        by_model_example.setdefault((result.model, result.example_id), []).append(result)

    lines = [
        "# Model Routing Benchmark",
        "",
        "Small directional benchmark over checked-in BuildSignals examples. No LLM judge is used.",
        "Accuracy excludes `api_error` rows; API error rate is reported separately.",
        "",
        "| Model | Task | Passed | Accuracy | API error rate | p50 latency ms | p95 latency ms | Cost per 1k calls |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for (model, task), rows in sorted(by_model_task.items()):
        passed, total, accuracy, api_error_rate = _summary_row(rows)
        latencies = [row.latency_ms for row in rows if row.latency_ms is not None]
        costs = [row.cost for row in rows if row.cost is not None]
        cost_per_1k = (statistics.mean(costs) * 1000) if costs else None
        lines.append(
            "| {model} | {task} | {passed}/{total} | {accuracy:.1%} | {api_error_rate:.1%} | {p50} | {p95} | {cost} |".format(
                model=model,
                task=task,
                passed=passed,
                total=total,
                accuracy=accuracy,
                api_error_rate=api_error_rate,
                p50=_percentile(latencies, 0.50) if latencies else "n/a",
                p95=_percentile(latencies, 0.95) if latencies else "n/a",
                cost=f"{cost_per_1k:.4f}" if cost_per_1k is not None else "n/a",
            )
        )

    lines.extend(["", "## Per-Example Pass Rates", ""])
    for (model, example_id), rows in sorted(by_model_example.items()):
        passed = sum(1 for row in rows if row.passed)
        lines.append(f"- `{model}` / `{example_id}`: {passed}/{len(rows)}")

    lines.extend(["", "## Failure Cases", ""])
    for row in results:
        if row.status != "ok":
            lines.append(
                f"- `{row.model}` / `{row.example_id}` run {row.run} "
                f"({row.task}, {row.status}): {row.error or 'check failed'}"
            )

    score_failures = [
        row for row in results if row.status != "ok" and row.example_id.startswith("score_")
    ]
    if score_failures:
        lines.extend(["", "## Failed Score Expected Vs Actual", ""])
        for row in score_failures:
            lines.extend(
                [
                    f"### {row.model} / {row.example_id} / run {row.run}",
                    "",
                    f"- Expected: `{row.expected}`",
                    f"- Actual: `{row.actual or row.error or ''}`",
                    "",
                ]
            )

    RESULTS_MD.write_text("\n".join(lines) + "\n")


def _print_failed_score_cases(results: list[EvalResult]) -> None:
    failures = [
        row for row in results if row.status == "check_fail" and row.example_id.startswith("score_")
    ]
    if not failures:
        return
    print("Failed score_* expected vs actual:")
    for row in failures:
        print(f"- {row.model} / {row.example_id} / run {row.run}")
        print(f"  expected: {row.expected}")
        print(f"  actual: {row.actual or row.error or ''}")


def _planned_runs(
    *,
    examples: list[dict[str, Any]],
    models: list[str],
    existing: list[EvalResult],
    only_errors: bool,
) -> list[tuple[str, dict[str, Any], int]]:
    examples_by_id = {example["id"]: example for example in examples}
    if only_errors:
        return [
            (row.model, examples_by_id[row.example_id], row.run)
            for row in existing
            if row.status == "api_error" and row.example_id in examples_by_id
        ]
    return [
        (model, example, run)
        for model in models
        for example in examples
        for run in range(1, 4)
    ]


def _merge_results(existing: list[EvalResult], replacements: list[EvalResult]) -> list[EvalResult]:
    by_key = {(row.model, row.example_id, row.run): row for row in existing}
    for row in replacements:
        by_key[(row.model, row.example_id, row.run)] = row
    return sorted(by_key.values(), key=lambda row: (row.model, row.example_id, row.run))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--only-errors", action="store_true")
    args = parser.parse_args(argv)

    examples = _load_jsonl(GOLDEN_PATH)
    models = _load_models(MODELS_PATH)
    if any(model != "deterministic" for model in models) and not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is required to run LLM benchmark arms.", file=sys.stderr)
        return 2

    existing = _read_existing_results() if args.only_errors else []
    runs = _planned_runs(
        examples=examples,
        models=models,
        existing=existing,
        only_errors=args.only_errors,
    )
    client = OpenRouterClient(fallback_models=[])

    def run(args_tuple: tuple[str, dict[str, Any], int]) -> EvalResult:
        model, example, run_number = args_tuple
        return _run_one(client, model, example, run_number)

    if args.concurrency <= 1:
        replacements = [run(item) for item in runs]
    else:
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            replacements = list(executor.map(run, runs))

    results = _merge_results(existing, replacements) if args.only_errors else replacements
    _write_csv(results)
    _write_full_jsonl(results)
    _write_markdown(results)
    _print_failed_score_cases(results)
    print(f"Wrote {RESULTS_CSV}, {RESULTS_FULL}, and {RESULTS_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
