from __future__ import annotations

import csv
import json

from eval import bench


def test_load_models_includes_deterministic_arm_and_pinned_haiku():
    models = bench._load_models(bench.MODELS_PATH)  # noqa: SLF001

    assert models[0] == "deterministic"
    assert "anthropic/claude-haiku-5.5" in models
    assert "~anthropic/claude-haiku-latest" not in models


def test_deterministic_benchmark_arm_uses_no_api_call():
    example = {
        "id": "score_case",
        "task": "score",
        "input": {
            "asking_price": 42_000_000,
            "units": 240,
            "contacts_count": 2,
            "has_assumptions": True,
            "year_built": 2015,
        },
        "expected": {
            "score": 60,
            "risk_level": "medium",
            "breakdown": {
                "has_asking_price": {"earned": 10},
                "price_per_unit_or_sqft": {"earned": 20},
                "has_contacts": {"earned": 10},
                "has_assumptions": {"earned": 10},
                "year_built_after_1970": {"earned": 10},
            },
        },
    }

    result = bench._run_one(None, "deterministic", example, 1)  # noqa: SLF001

    assert result.status == "ok"
    assert result.passed is True
    assert result.strict_parse is True
    assert result.cost == 0
    assert result.provider == "local"


def test_api_error_rows_are_separate_from_check_failures():
    example = {"id": "memo_case", "task": "memo", "input": {}, "expected": {"contains": ["x"]}}

    class FailingClient:
        def chat_completion(self, **_kwargs):
            raise RuntimeError("provider down")

    result = bench._run_one(FailingClient(), "openai/gpt-4o-mini", example, 1)  # noqa: SLF001

    assert result.status == "api_error"
    assert result.passed is False
    assert result.error == "RuntimeError: provider down"


def test_api_error_text_is_redacted_before_results_are_written():
    example = {"id": "memo_case", "task": "memo", "input": {}, "expected": {"contains": ["x"]}}

    class SensitiveProviderError(Exception):
        def __str__(self):
            return (
                "user_id='user_3KeduS5tqTwM8Pfit3EmAIMfQdf' "
                "visit https://openrouter.ai/workspaces/default/keys/abc123"
            )

    class FailingClient:
        def chat_completion(self, **_kwargs):
            raise SensitiveProviderError()

    result = bench._run_one(FailingClient(), "openai/gpt-4o-mini", example, 1)  # noqa: SLF001

    assert "user_3KeduS5tqTwM8Pfit3EmAIMfQdf" not in result.error
    assert "https://openrouter.ai/workspaces/default/keys/abc123" not in result.error
    assert "user_id=" in result.error
    assert "user_[REDACTED]" in result.error
    assert "[REDACTED_KEY_URL]" in result.error


def test_csv_truncates_actual_and_full_jsonl_keeps_full_output(tmp_path, monkeypatch):
    csv_path = tmp_path / "results.csv"
    full_path = tmp_path / "results_full.jsonl"
    monkeypatch.setattr(bench, "RESULTS_CSV", csv_path)
    monkeypatch.setattr(bench, "RESULTS_FULL", full_path)
    result = bench.EvalResult(
        model="deterministic",
        example_id="memo_case",
        task="memo",
        run=1,
        status="check_fail",
        passed=False,
        strict_parse=None,
        expected="{}",
        actual="x" * 500,
        full_actual="x" * 900,
        resolved_model="deterministic",
        provider="local",
        latency_ms=0,
        cost=0,
        error=None,
        ungrounded_numbers="[]",
    )

    bench._write_csv([result])  # noqa: SLF001
    bench._write_full_jsonl([result])  # noqa: SLF001

    with csv_path.open() as handle:
        row = next(csv.DictReader(handle))
    assert "full_actual" not in row
    assert len(row["actual"]) == 500

    full_row = json.loads(full_path.read_text())
    assert full_row["full_actual"] == "x" * 900


def test_memo_rows_report_ungrounded_numbers_without_affecting_pass_status():
    example = {
        "id": "memo_case",
        "task": "memo",
        "input": {
            "name": "Main Street Retail",
            "asking_price": 42000000,
            "score": 82.5,
            "notes": "95% occupied with 12 suites.",
        },
        "expected": {"contains": ["Main Street Retail", "Recommendation"]},
    }

    result = bench._result_from_content(  # noqa: SLF001
        model="deterministic",
        example=example,
        run=1,
        expected="{}",
        content=(
            "## Executive Summary\n"
            "Main Street Retail is offered at $42,000,000 and is 95% occupied.\n"
            "## Recommendation\n"
            "Review the 24-month rollover schedule."
        ),
        resolved_model="deterministic",
        provider="local",
        latency_ms=0,
        cost=0,
    )

    assert result.passed is True
    assert json.loads(result.ungrounded_numbers) == ["24"]
