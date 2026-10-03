"""Read-only, organization-scoped aggregates for the admin dashboard."""

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.config import (
    CORS_ALLOWED_ORIGINS,
    DATABASE_URL,
    DEMO_LOGIN_EMAIL,
    DEMO_LOGIN_ENABLED,
    DEMO_LOGIN_PASSWORD,
    ENVIRONMENT,
    IS_PRODUCTION,
)
from app.models.evaluation import EvalDataset, EvalResult, EvalRun
from app.models.ingestion import IngestionRun
from app.schemas.observability import (
    AttentionItem,
    DailyCounts,
    DeploymentReadiness,
    DeploymentReadinessCheck,
    EvaluationCounts,
    IngestionCounts,
    ObservabilityOverview,
    WorkflowCounts,
)


def _count_when(condition):
    return func.sum(case((condition, 1), else_=0))


def _readiness_check(
    code: str,
    label: str,
    ok: bool,
    summary_ok: str,
    summary_fail: str,
    *,
    action: str | None = None,
    warn: bool = False,
) -> DeploymentReadinessCheck:
    status = "pass" if ok else "warning" if warn else "fail"
    return DeploymentReadinessCheck(
        code=code,
        label=label,
        status=status,
        summary=summary_ok if ok else summary_fail,
        action=None if ok else action,
    )


def get_deployment_readiness() -> DeploymentReadiness:
    app_base_url = os.environ.get("APP_BASE_URL", "").strip()
    metrics_token = os.environ.get("METRICS_TOKEN", "").strip()
    redis_url = os.environ.get("REDIS_URL", "").strip()
    sentry_dsn = os.environ.get("SENTRY_DSN", "").strip()
    database_provider = "postgres" if DATABASE_URL.startswith(("postgresql://", "postgres://")) else "sqlite"
    checks = [
        _readiness_check(
            "database_provider",
            "Production database",
            not IS_PRODUCTION or database_provider == "postgres",
            "Postgres is configured for deployed data.",
            "Production must use Postgres instead of SQLite.",
            action="Set DATABASE_URL to the managed Postgres connection and redeploy the API.",
        ),
        _readiness_check(
            "cors_origins",
            "Allowed frontend origins",
            bool(CORS_ALLOWED_ORIGINS),
            "CORS allowlist is configured.",
            "No frontend origin allowlist is configured.",
            action="Set CORS_ALLOWED_ORIGINS to the production frontend URL without wildcards.",
        ),
        _readiness_check(
            "app_base_url",
            "Application base URL",
            bool(app_base_url) and "localhost" not in app_base_url,
            "APP_BASE_URL points at a deployed frontend.",
            "APP_BASE_URL is missing or still points at localhost.",
            action="Set APP_BASE_URL to the production frontend URL so email links and redirects are correct.",
            warn=not IS_PRODUCTION,
        ),
        _readiness_check(
            "demo_workspace",
            "Demo workspace",
            DEMO_LOGIN_ENABLED and bool(DEMO_LOGIN_EMAIL) and bool(DEMO_LOGIN_PASSWORD),
            "Demo login is enabled with backend-only seeded credentials.",
            "Demo login is disabled or missing seeded backend credentials.",
            action=(
                "Set BUILD_SIGNALS_EXPOSE_DEMO_CREDENTIALS=true, BUILD_SIGNALS_DEMO_EMAIL, "
                "and BUILD_SIGNALS_DEMO_PASSWORD on the API service, then redeploy."
            ),
            warn=True,
        ),
        _readiness_check(
            "shared_rate_limit",
            "Shared rate limiter",
            bool(redis_url),
            "Redis/Valkey is configured for shared rate limits.",
            "Rate limiting may be process-local because REDIS_URL is missing.",
            action="Link the Render key-value service or set REDIS_URL before serious prospect traffic.",
            warn=True,
        ),
        _readiness_check(
            "metrics_token",
            "Metrics protection",
            bool(metrics_token),
            "Metrics scraping requires a bearer token.",
            "Metrics token is missing; avoid exposing metrics publicly.",
            action="Set METRICS_TOKEN on the API service.",
            warn=True,
        ),
        _readiness_check(
            "sentry",
            "Error tracking",
            bool(sentry_dsn),
            "Backend Sentry DSN is configured.",
            "Backend Sentry DSN is not configured.",
            action="Set SENTRY_DSN to capture production backend errors.",
            warn=True,
        ),
    ]
    severity = {"pass": 0, "warning": 1, "fail": 2}
    overall = max((check.status for check in checks), key=lambda status: severity[status])
    return DeploymentReadiness(
        environment=ENVIRONMENT,
        database_provider=database_provider,
        overall_status=overall,
        checks=checks,
    )


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
        ), ingestion=ingestion, deployment=get_deployment_readiness(), attention=attention,
    )
