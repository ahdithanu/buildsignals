from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ai_usage import AiWorkflowUsageDailyRollup
from app.models.evaluation import EvalDataset, EvalResult, EvalRun


def _date_bucket(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).date()


@dataclass(frozen=True)
class AiUsageAccumulator:
    organization_id: str
    usage_date: date
    workflow: str
    model: str
    prompt_version: str
    run_ids: set[str]
    total_results: int = 0
    known_cost_results: int = 0
    known_token_results: int = 0
    known_latency_results: int = 0
    total_tokens_input: int | None = None
    total_tokens_output: int | None = None
    total_latency_ms: float | None = None
    total_cost_usd: float | None = None
    last_run_at: datetime | None = None


def _add_optional_number(current: int | float | None, value: int | float | None) -> int | float | None:
    if value is None:
        return current
    return value if current is None else current + value


def rebuild_ai_usage_rollups(db: Session, *, organization_id: str) -> int:
    db.query(AiWorkflowUsageDailyRollup).filter(
        AiWorkflowUsageDailyRollup.organization_id == organization_id,
    ).delete(synchronize_session=False)

    rows = (
        db.query(EvalResult, EvalRun, EvalDataset)
        .join(EvalRun, EvalRun.id == EvalResult.run_id)
        .join(EvalDataset, EvalDataset.id == EvalRun.dataset_id)
        .filter(EvalResult.organization_id == organization_id)
        .order_by(EvalResult.created_at.asc(), EvalResult.id.asc())
        .all()
    )
    buckets: dict[tuple[str, date, str, str, str], dict] = {}
    for result, run, dataset in rows:
        usage_date = _date_bucket(result.created_at)
        key = (
            result.organization_id,
            usage_date,
            dataset.workflow,
            result.model,
            result.prompt_version,
        )
        bucket = buckets.setdefault(
            key,
            {
                "run_ids": set(),
                "total_results": 0,
                "known_cost_results": 0,
                "known_token_results": 0,
                "known_latency_results": 0,
                "total_tokens_input": None,
                "total_tokens_output": None,
                "total_latency_ms": None,
                "total_cost_usd": None,
                "last_run_at": None,
            },
        )
        bucket["run_ids"].add(run.id)
        bucket["total_results"] += 1
        if result.cost_usd is not None:
            bucket["known_cost_results"] += 1
            bucket["total_cost_usd"] = _add_optional_number(bucket["total_cost_usd"], result.cost_usd)
        if result.tokens_input is not None and result.tokens_output is not None:
            bucket["known_token_results"] += 1
            bucket["total_tokens_input"] = _add_optional_number(bucket["total_tokens_input"], result.tokens_input)
            bucket["total_tokens_output"] = _add_optional_number(bucket["total_tokens_output"], result.tokens_output)
        if result.latency_ms is not None:
            bucket["known_latency_results"] += 1
            bucket["total_latency_ms"] = _add_optional_number(bucket["total_latency_ms"], result.latency_ms)
        if bucket["last_run_at"] is None or run.started_at > bucket["last_run_at"]:
            bucket["last_run_at"] = run.started_at

    now = datetime.now(timezone.utc)
    for (org_id, usage_date, workflow, model, prompt_version), bucket in buckets.items():
        db.add(
            AiWorkflowUsageDailyRollup(
                organization_id=org_id,
                usage_date=usage_date,
                workflow=workflow,
                model=model,
                prompt_version=prompt_version,
                total_runs=len(bucket["run_ids"]),
                total_results=bucket["total_results"],
                known_cost_results=bucket["known_cost_results"],
                known_token_results=bucket["known_token_results"],
                known_latency_results=bucket["known_latency_results"],
                total_tokens_input=bucket["total_tokens_input"],
                total_tokens_output=bucket["total_tokens_output"],
                total_latency_ms=bucket["total_latency_ms"],
                total_cost_usd=bucket["total_cost_usd"],
                last_run_at=bucket["last_run_at"],
                updated_at=now,
            )
        )
    db.commit()
    return len(rows)


def list_ai_usage_rollups(db: Session, *, organization_id: str) -> list[AiWorkflowUsageDailyRollup]:
    return (
        db.query(AiWorkflowUsageDailyRollup)
        .filter(AiWorkflowUsageDailyRollup.organization_id == organization_id)
        .order_by(
            AiWorkflowUsageDailyRollup.usage_date.desc(),
            AiWorkflowUsageDailyRollup.workflow.asc(),
            AiWorkflowUsageDailyRollup.model.asc(),
        )
        .all()
    )


def summarize_ai_usage(db: Session, *, organization_id: str) -> dict:
    rows = list_ai_usage_rollups(db, organization_id=organization_id)
    totals = {
        "total_runs": sum(row.total_runs for row in rows),
        "total_results": sum(row.total_results for row in rows),
        "total_tokens_input": None,
        "total_tokens_output": None,
        "total_cost_usd": None,
        "total_latency_ms": None,
        "known_cost_results": sum(row.known_cost_results for row in rows),
        "known_token_results": sum(row.known_token_results for row in rows),
        "known_latency_results": sum(row.known_latency_results for row in rows),
    }
    for row in rows:
        totals["total_tokens_input"] = _add_optional_number(totals["total_tokens_input"], row.total_tokens_input)
        totals["total_tokens_output"] = _add_optional_number(totals["total_tokens_output"], row.total_tokens_output)
        totals["total_cost_usd"] = _add_optional_number(totals["total_cost_usd"], row.total_cost_usd)
        totals["total_latency_ms"] = _add_optional_number(totals["total_latency_ms"], row.total_latency_ms)
    return {"totals": totals, "daily": rows}


def count_eval_results_without_rollup(db: Session, *, organization_id: str) -> int:
    return int(
        db.query(func.count(EvalResult.id))
        .filter(EvalResult.organization_id == organization_id)
        .scalar()
        or 0
    )
