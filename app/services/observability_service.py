"""Read-only, organization-scoped aggregates for the admin dashboard."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models.evaluation import EvalDataset, EvalResult, EvalRun
from app.models.ingestion import IngestionRun
from app.schemas.observability import (
    AttentionItem,
    DailyCounts,
    EvaluationCounts,
    IngestionCounts,
    ObservabilityOverview,
    WorkflowCounts,
)


def _count_when(condition):
    return func.sum(case((condition, 1), else_=0))


def get_overview(db: Session, org_id: str, days: int, now: datetime | None = None) -> ObservabilityOverview:
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    run_filter = and_(EvalRun.organization_id == org_id, EvalRun.started_at >= start, EvalRun.started_at < now)
    run_row = db.execute(select(
        func.count(EvalRun.id),
        _count_when(EvalRun.status == "completed"),
        _count_when(EvalRun.status == "failed"),
        _count_when(EvalRun.status == "running"),
        _count_when(and_(EvalRun.status == "completed", EvalRun.gate_passed.is_(True))),
        _count_when(EvalRun.mode == "live"),
        _count_when(EvalRun.mode == "replay"),
    ).where(run_filter)).one()
    runs, completed, failed, running, gates_passed, live_runs, replay_runs = (int(value or 0) for value in run_row)

    result_row = db.execute(select(
        func.count(EvalResult.id),
        _count_when(EvalResult.status == "error"),
        func.sum(EvalResult.cost_usd),
        _count_when(EvalResult.cost_usd.is_not(None)),
        func.sum(EvalResult.tokens_input),
        func.sum(EvalResult.tokens_output),
        _count_when(and_(EvalResult.tokens_input.is_not(None), EvalResult.tokens_output.is_not(None))),
        func.avg(EvalResult.latency_ms),
        _count_when(EvalResult.latency_ms.is_not(None)),
        _count_when(EvalResult.tokens_input.is_not(None)),
        _count_when(EvalResult.tokens_output.is_not(None)),
    ).join(EvalRun, and_(EvalResult.run_id == EvalRun.id, EvalResult.organization_id == EvalRun.organization_id))
      .where(run_filter, EvalResult.organization_id == org_id)).one()
    results = int(result_row[0] or 0)
    case_errors = int(result_row[1] or 0)
    cost_reported = int(result_row[3] or 0)
    tokens_reported = int(result_row[6] or 0)
    latency_reported = int(result_row[8] or 0)
    input_tokens_reported = int(result_row[9] or 0)
    output_tokens_reported = int(result_row[10] or 0)

    workflows = db.execute(select(
        EvalDataset.workflow, func.count(EvalRun.id),
        _count_when(and_(EvalRun.status == "completed", EvalRun.gate_passed.is_(True))),
        _count_when(EvalRun.status == "failed"),
    ).join(EvalDataset, and_(EvalRun.dataset_id == EvalDataset.id, EvalRun.organization_id == EvalDataset.organization_id))
      .where(run_filter, EvalDataset.organization_id == org_id).group_by(EvalDataset.workflow)).all()

    # The date expression uses UTC on PostgreSQL; SQLite stores UTC timestamps for local tests.
    date_expr = (func.date(func.timezone("UTC", EvalRun.started_at))
                 if db.bind and db.bind.dialect.name == "postgresql" else func.date(EvalRun.started_at))
    run_days = {str(day): count for day, count in db.execute(
        select(date_expr, func.count(EvalRun.id)).where(run_filter).group_by(date_expr)).all()}
    error_days = {str(day): count for day, count in db.execute(select(date_expr, func.count(EvalResult.id))
        .join(EvalRun, and_(EvalResult.run_id == EvalRun.id, EvalResult.organization_id == EvalRun.organization_id))
        .where(run_filter, EvalResult.organization_id == org_id, EvalResult.status == "error")
        .group_by(date_expr)).all()}
    first_day = start.date()
    last_day = now.date()
    daily = [DailyCounts(date=day.isoformat(), runs=int(run_days.get(day.isoformat(), 0)),
                         case_errors=int(error_days.get(day.isoformat(), 0)))
             for day in (first_day + timedelta(days=i) for i in range((last_day - first_day).days + 1))]

    ingest_filter = and_(IngestionRun.organization_id == org_id, IngestionRun.started_at >= start,
                         IngestionRun.started_at < now)
    ingest_row = db.execute(select(
        func.count(IngestionRun.id),
        _count_when(IngestionRun.status == "completed"),
        _count_when(IngestionRun.status == "failed"),
        _count_when(IngestionRun.status.in_(("partial", "partial_with_errors"))),
        _count_when(IngestionRun.status == "partial_with_errors"),
        _count_when(IngestionRun.status == "running"),
        func.sum(IngestionRun.records_seen), func.sum(IngestionRun.records_failed),
        _count_when(and_(IngestionRun.status == "running", IngestionRun.heartbeat_at < now - timedelta(minutes=15))),
    ).where(ingest_filter)).one()
    ingestion = IngestionCounts(**dict(zip(
        ("runs", "completed", "failed", "partial", "partial_with_errors", "running", "records_seen", "records_failed", "stalled_runs"),
        (int(value or 0) for value in ingest_row),
    )))
    attention = []
    for code, count, summary, href in (
        ("stalled_ingestion", ingestion.stalled_runs, "Ingestion runs have not reported a heartbeat in 15 minutes", "/source-health"),
        ("failed_ingestion", ingestion.failed, "Ingestion runs failed", "/source-health"),
        ("partial_ingestion_errors", ingestion.partial_with_errors, "Partial ingestion runs had record errors", "/source-health"),
        ("failed_evaluations", failed, "Evaluation runs failed", "/admin/evals"),
        ("evaluation_case_errors", case_errors, "Evaluation cases returned errors", "/admin/evals"),
    ):
        if count:
            attention.append(AttentionItem(code=code, level="warning", summary=summary, count=count, href=href))

    return ObservabilityOverview(
        generated_at=now, window_start=start, window_end=now, days=days,
        evaluations=EvaluationCounts(
            runs=runs, completed=completed, failed=failed, running=running, gates_passed=gates_passed,
            live_runs=live_runs, replay_runs=replay_runs, results=results, case_errors=case_errors,
            cost_usd_known=float(result_row[2]) if cost_reported else None,
            cost_reported_results=cost_reported, cost_unknown_results=results - cost_reported,
            tokens_input_known=int(result_row[4]) if result_row[4] is not None else None,
            tokens_output_known=int(result_row[5]) if result_row[5] is not None else None,
            tokens_reported_results=tokens_reported, tokens_unknown_results=results - tokens_reported,
            input_tokens_reported_results=input_tokens_reported,
            input_tokens_unknown_results=results - input_tokens_reported,
            output_tokens_reported_results=output_tokens_reported,
            output_tokens_unknown_results=results - output_tokens_reported,
            avg_latency_ms_known=float(result_row[7]) if latency_reported else None,
            latency_reported_results=latency_reported, latency_unknown_results=results - latency_reported,
            by_workflow=[WorkflowCounts(workflow=w, runs=int(n), gate_passed=int(g or 0), failed=int(f or 0))
                         for w, n, g, f in workflows], daily=daily,
        ), ingestion=ingestion, attention=attention,
    )
