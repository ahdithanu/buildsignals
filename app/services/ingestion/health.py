from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ingestion import (
    IngestionCandidateCanaryAttempt,
    IngestionRun,
    IngestionSource,
    RawSourceRecord,
)
from app.schemas.ingestion_candidate import IngestionSourceCandidate
from app.services.ingestion.connector_config import resolve_connector_config_dates
from app.services.ingestion.connectors import build_connector
from app.services.ingestion.normalization import (
    missing_required_source_fields,
    normalize_parcel,
    normalize_permit,
    parse_source_datetime,
    prepare_mapped_record,
)
from app.services.ingestion.service import _record_matches_filters
from app.utils.org_scope import active_query, get_org_id


@dataclass(frozen=True)
class SourceCanaryResult:
    source_id: str
    source_key: str
    ok: bool
    records_fetched: int
    records_valid: int
    records_failed: int
    approval_stages: dict[str, int]
    sample_record_ids: list[str]
    next_checkpoint: dict[str, Any] | None
    errors: list[str]


@dataclass(frozen=True)
class SourceHealthResult:
    source_id: str
    source_key: str
    source_name: str
    jurisdiction: str | None
    license: str | None
    signal_stage: str | None
    official_landing_page: str | None
    attribution_required: bool
    share_alike_review_required: bool
    status: str
    active_run_id: str | None
    active_heartbeat_at: datetime | None
    heartbeat_age_seconds: float | None
    active_run_stale: bool
    last_run_at: datetime | None
    last_success_at: datetime | None
    ingestion_age_hours: float | None
    source_watermark_at: datetime | None
    source_lag_hours: float | None
    terminal_runs: int
    unhealthy_runs: int
    run_failure_rate: float | None
    records_seen: int
    records_failed: int
    record_failure_rate: float | None
    cursor: dict[str, Any] | None
    cursor_updated_at: datetime | None
    cursor_stalled: bool
    reasons: list[str]


@dataclass(frozen=True)
class CandidateCanaryResult:
    candidate_key: str
    candidate_name: str
    ok: bool
    records_fetched: int
    records_valid: int
    records_failed: int
    approval_stages: dict[str, int]
    sample_record_ids: list[str]
    next_checkpoint: dict[str, Any] | None
    errors: list[str]


@dataclass(frozen=True)
class ReliabilityWatchlistItem:
    source_id: str
    source_name: str
    jurisdiction: str | None
    status: str
    active_run_stale: bool
    cursor_stalled: bool
    reasons: list[str]


@dataclass(frozen=True)
class IngestionReliabilitySummary:
    healthy_sources: int
    attention_sources: int
    critical_sources: int
    stale_runs: int
    stalled_cursors: int
    failed_retry_canaries: int
    watchlist_sources: list[ReliabilityWatchlistItem]


def resolve_resume_checkpoint(db: Session, source_id: str) -> dict[str, Any] | None:
    run = active_query(db.query(IngestionRun), IngestionRun).filter(
        IngestionRun.source_id == source_id,
        IngestionRun.status.in_(("completed", "partial")),
        IngestionRun.trigger != "canary",
    ).order_by(IngestionRun.started_at.desc()).first()
    return dict(run.checkpoint) if run and run.checkpoint else None


def evaluate_source_health(
    db: Session,
    source: IngestionSource,
    *,
    now: datetime | None = None,
    window_hours: int = 168,
) -> SourceHealthResult:
    now = _as_utc(now or datetime.now(timezone.utc))
    window_start = now - timedelta(hours=window_hours)
    operational = active_query(db.query(IngestionRun), IngestionRun).filter(
        IngestionRun.source_id == source.id,
        IngestionRun.trigger != "canary",
    )
    latest_run = operational.order_by(IngestionRun.started_at.desc()).first()
    active_run = operational.filter(IngestionRun.status == "running").order_by(
        IngestionRun.started_at.desc()
    ).first()
    heartbeat_age_seconds = (
        round((now - _as_utc(active_run.heartbeat_at)).total_seconds(), 2)
        if active_run else None
    )
    stale_after_seconds = float(
        (source.settings or {}).get("stale_run_after_seconds", 300)
    )
    active_run_stale = bool(
        heartbeat_age_seconds is not None
        and heartbeat_age_seconds > stale_after_seconds
    )
    healthy_query = operational.filter(
        IngestionRun.status.in_(("completed", "partial")),
        IngestionRun.records_failed == 0,
    )
    last_success = healthy_query.order_by(IngestionRun.started_at.desc()).first()
    terminal = operational.filter(
        IngestionRun.started_at >= window_start,
        IngestionRun.status.in_(("completed", "partial", "failed", "partial_with_errors")),
    ).order_by(IngestionRun.started_at.desc()).all()
    unhealthy = [run for run in terminal if run.status in {"failed", "partial_with_errors"}]
    records_seen = sum(run.records_seen for run in terminal)
    records_failed = sum(run.records_failed for run in terminal)
    failure_rate = len(unhealthy) / len(terminal) if terminal else None
    record_failure_rate = records_failed / records_seen if records_seen else None
    latest_terminal = terminal[0] if terminal else None
    latest_terminal_recovered = bool(
        latest_terminal is not None
        and latest_terminal.status in {"completed", "partial"}
        and latest_terminal.records_failed == 0
    )
    ingestion_age = (
        _hours_between(now, last_success.completed_at or last_success.started_at)
        if last_success else None
    )
    watermark = active_query(db.query(func.max(RawSourceRecord.source_updated_at)), RawSourceRecord).filter(
        RawSourceRecord.source_id == source.id
    ).scalar()
    source_lag = _hours_between(now, watermark) if watermark else None
    cursor_run = healthy_query.filter(IngestionRun.checkpoint.is_not(None)).order_by(
        IngestionRun.started_at.desc()
    ).first()
    partials = healthy_query.filter(IngestionRun.status == "partial").order_by(
        IngestionRun.started_at.desc()
    ).limit(3).all()
    cursor_stalled = (
        len(partials) == 3
        and partials[0].checkpoint is not None
        and all(run.checkpoint == partials[0].checkpoint for run in partials[1:])
    )

    sla_hours = float((source.settings or {}).get("freshness_sla_hours", 36))
    critical_hours = max(48.0, sla_hours * 4 / 3)
    reasons: list[str] = []
    status = "healthy"
    if last_success is None:
        status = "unknown"
        reasons.append("No successful operational run has completed")
    elif ingestion_age is not None and ingestion_age > critical_hours:
        status = "critical"
        reasons.append(f"Latest successful ingestion is {ingestion_age:.1f} hours old")
    elif ingestion_age is not None and ingestion_age > sla_hours:
        status = "degraded"
        reasons.append(f"Latest successful ingestion exceeds the {sla_hours:g}-hour SLA")
    if source_lag is not None and source_lag > critical_hours:
        status = "critical"
        reasons.append(f"Latest source watermark is {source_lag:.1f} hours old")
    elif source_lag is not None and source_lag > sla_hours and status == "healthy":
        status = "degraded"
        reasons.append(f"Latest source watermark exceeds the {sla_hours:g}-hour SLA")
    if cursor_stalled:
        status = "critical"
        reasons.append("Checkpoint did not advance across three partial runs")
    if active_run_stale:
        status = "critical"
        reasons.append(
            f"Active run heartbeat is {heartbeat_age_seconds:.0f} seconds old"
        )
    if failure_rate is not None and failure_rate >= 0.5:
        if latest_terminal_recovered and status == "healthy":
            status = "degraded"
            reasons.append(
                f"Latest run recovered, but failure rate is {failure_rate:.0%} in the health window"
            )
        else:
            status = "critical"
            reasons.append(f"Run failure rate is {failure_rate:.0%} in the health window")
    elif failure_rate is not None and failure_rate > 0.1 and status == "healthy":
        status = "degraded"
        reasons.append(f"Run failure rate is {failure_rate:.0%} in the health window")

    return SourceHealthResult(
        source_id=source.id,
        source_key=source.key,
        source_name=source.name,
        jurisdiction=source.jurisdiction,
        license=(source.settings or {}).get("license"),
        signal_stage=(source.settings or {}).get("signal_stage"),
        official_landing_page=(source.settings or {}).get("official_landing_page") or (source.settings or {}).get("source_url") or source.base_url,
        attribution_required=bool((source.settings or {}).get("attribution_required", False)),
        share_alike_review_required=bool(
            (source.settings or {}).get("share_alike_review_required", False)
        ),
        status=status,
        active_run_id=active_run.id if active_run else None,
        active_heartbeat_at=active_run.heartbeat_at if active_run else None,
        heartbeat_age_seconds=heartbeat_age_seconds,
        active_run_stale=active_run_stale,
        last_run_at=latest_run.started_at if latest_run else None,
        last_success_at=(last_success.completed_at or last_success.started_at) if last_success else None,
        ingestion_age_hours=ingestion_age,
        source_watermark_at=watermark,
        source_lag_hours=source_lag,
        terminal_runs=len(terminal),
        unhealthy_runs=len(unhealthy),
        run_failure_rate=round(failure_rate, 4) if failure_rate is not None else None,
        records_seen=records_seen,
        records_failed=records_failed,
        record_failure_rate=(
            round(record_failure_rate, 4) if record_failure_rate is not None else None
        ),
        cursor=dict(cursor_run.checkpoint) if cursor_run and cursor_run.checkpoint else None,
        cursor_updated_at=cursor_run.completed_at if cursor_run else None,
        cursor_stalled=cursor_stalled,
        reasons=reasons,
    )


def summarize_ingestion_reliability(
    db: Session,
    *,
    now: datetime | None = None,
) -> IngestionReliabilitySummary:
    now = _as_utc(now or datetime.now(timezone.utc))
    sources = [evaluate_source_health(db, source, now=now) for source in active_query(db.query(IngestionSource), IngestionSource).all()]
    candidates = active_query(db.query(IngestionCandidateCanaryAttempt), IngestionCandidateCanaryAttempt).order_by(
        IngestionCandidateCanaryAttempt.candidate_key.asc(),
        IngestionCandidateCanaryAttempt.created_at.desc(),
    ).all()
    latest_candidate_attempts: dict[str, IngestionCandidateCanaryAttempt] = {}
    for attempt in candidates:
        if attempt.candidate_key not in latest_candidate_attempts:
            latest_candidate_attempts[attempt.candidate_key] = attempt
    healthy_sources = sum(1 for source in sources if source.status == "healthy")
    attention_sources = sum(1 for source in sources if source.status == "degraded")
    critical_sources = sum(1 for source in sources if source.status in {"critical", "unknown"})
    stale_runs = sum(1 for source in sources if source.active_run_stale)
    stalled_cursors = sum(1 for source in sources if source.cursor_stalled)
    failed_retry_canaries = sum(1 for attempt in latest_candidate_attempts.values() if attempt.ok is False)
    watchlist_sources = [
        ReliabilityWatchlistItem(
            source_id=source.source_id,
            source_name=source.source_name,
            jurisdiction=source.jurisdiction,
            status=source.status,
            active_run_stale=source.active_run_stale,
            cursor_stalled=source.cursor_stalled,
            reasons=source.reasons,
        )
        for source in sources
        if source.active_run_stale or source.cursor_stalled or source.status == "critical"
    ][:4]
    return IngestionReliabilitySummary(
        healthy_sources=healthy_sources,
        attention_sources=attention_sources,
        critical_sources=critical_sources,
        stale_runs=stale_runs,
        stalled_cursors=stalled_cursors,
        failed_retry_canaries=failed_retry_canaries,
        watchlist_sources=watchlist_sources,
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _hours_between(later: datetime, earlier: datetime) -> float:
    return round((_as_utc(later) - _as_utc(earlier)).total_seconds() / 3600, 2)


def validate_source_canary(
    source: IngestionSource,
    *,
    sample_size: int = 10,
    now: datetime | None = None,
) -> SourceCanaryResult:
    if sample_size < 1 or sample_size > 100:
        raise ValueError("sample_size must be between 1 and 100")
    now = _as_utc(now or datetime.now(timezone.utc))
    settings = dict(source.settings or {})
    connector_config = resolve_connector_config_dates(
        dict(settings.get("connector") or {}),
        now=now,
    )
    connector_config["page_size"] = sample_size
    if source.base_url:
        connector_config.setdefault(
            "source" if source.adapter == "csv" else "endpoint", source.base_url
        )
    connector = build_connector(source.adapter, connector_config)
    mappings = [mapping for mapping in source.field_mappings if mapping.is_active]
    extra_required_fields: set[str] = set()
    freshness_field = settings.get("freshness_field")
    if isinstance(freshness_field, str) and freshness_field:
        extra_required_fields.add(freshness_field)
    envelope = connector.fetch_page()

    fetched = len(envelope.records)
    valid = 0
    skipped = 0
    stages: dict[str, int] = {}
    sample_record_ids: list[str] = []
    errors: list[str] = []
    canary_fields = settings.get("canary_required_fields", [])
    if not isinstance(canary_fields, list) or any(
        not isinstance(field, str) or not field for field in canary_fields
    ):
        raise ValueError("canary_required_fields must be a list of field names")
    observed_fields = {field for record in envelope.records for field in record}
    missing_canary_fields = sorted(set(canary_fields) - observed_fields)
    if missing_canary_fields:
        errors.append(f"Canary page is missing expected fields: {missing_canary_fields}")
    page_result = _validate_canary_records(
        source,
        envelope.records,
        mappings=mappings,
        settings=settings,
        extra_required_fields=extra_required_fields,
        record_filters=settings.get("record_filters"),
    )
    valid += page_result["valid"]
    skipped += page_result["skipped"]
    _merge_stage_counts(stages, page_result["stages"])
    sample_record_ids.extend(page_result["sample_record_ids"])
    errors.extend(page_result["errors"])
    freshness_probe = settings.get("canary_freshness_probe")
    if freshness_probe is not None and not isinstance(freshness_probe, dict):
        raise ValueError("canary_freshness_probe must be an object")
    if freshness_probe is None:
        errors.extend(_freshness_errors(envelope.records, settings, now=now))

    probes = settings.get("canary_stage_probes", [])
    if probes is None:
        probes = []
    if not isinstance(probes, list):
        raise ValueError("canary_stage_probes must be a list")
    for probe_index, probe in enumerate(probes, start=1):
        if not isinstance(probe, dict):
            raise ValueError("canary_stage_probes entries must be objects")
        probe_name = str(probe.get("name") or f"probe_{probe_index}")
        expected_stage = probe.get("expected_stage")
        if not isinstance(expected_stage, str) or not expected_stage:
            raise ValueError("canary_stage_probes entries require expected_stage")
        probe_sample_size = int(probe.get("sample_size") or sample_size)
        if probe_sample_size < 1 or probe_sample_size > 100:
            raise ValueError("canary_stage_probes sample_size must be between 1 and 100")
        probe_config = resolve_connector_config_dates(
            _merge_connector_config(
                connector_config,
                probe.get("connector") or {},
                page_size=probe_sample_size,
            ),
            now=now,
        )
        probe_connector = build_connector(source.adapter, probe_config)
        probe_envelope = probe_connector.fetch_page()
        fetched += len(probe_envelope.records)
        probe_result = _validate_canary_records(
            source,
            probe_envelope.records,
            mappings=mappings,
            settings=settings,
            extra_required_fields=extra_required_fields,
            record_filters=probe.get("record_filters", settings.get("record_filters")),
            error_prefix=f"{probe_name}: ",
        )
        valid += probe_result["valid"]
        skipped += probe_result["skipped"]
        _merge_stage_counts(stages, probe_result["stages"])
        sample_record_ids.extend(probe_result["sample_record_ids"])
        errors.extend(probe_result["errors"])
        if freshness_probe is None:
            errors.extend(
                _freshness_errors(
                    probe_envelope.records,
                    settings,
                    now=now,
                    error_prefix=f"{probe_name}: ",
                )
            )
        if probe_result["fetched"] == 0:
            errors.append(f"{probe_name}: Source returned no records for stage probe")
        if probe_result["valid"] == 0:
            errors.append(f"{probe_name}: No valid records for stage probe")
        if probe_result["stages"].get(expected_stage, 0) == 0:
            errors.append(
                f"{probe_name}: Expected normalized stage {expected_stage!r} was not observed"
            )

    if freshness_probe is not None:
        freshness_field = settings.get("freshness_field")
        if not isinstance(freshness_field, str) or not freshness_field:
            raise ValueError("canary_freshness_probe requires freshness_field")
        freshness_sample_size = int(freshness_probe.get("sample_size") or sample_size)
        if freshness_sample_size < 1 or freshness_sample_size > 100:
            raise ValueError("canary_freshness_probe sample_size must be between 1 and 100")
        freshness_config = resolve_connector_config_dates(
            _merge_connector_config(
                connector_config,
                freshness_probe.get("connector") or {},
                page_size=freshness_sample_size,
                error_context="canary_freshness_probe connector override",
            ),
            now=now,
        )
        freshness_connector = build_connector(source.adapter, freshness_config)
        freshness_envelope = freshness_connector.fetch_page()
        fetched += len(freshness_envelope.records)
        freshness_result = _validate_canary_records(
            source,
            freshness_envelope.records,
            mappings=mappings,
            settings=settings,
            extra_required_fields=extra_required_fields,
            record_filters=freshness_probe.get(
                "record_filters",
                settings.get("record_filters"),
            ),
            error_prefix="freshness_probe: ",
        )
        valid += freshness_result["valid"]
        skipped += freshness_result["skipped"]
        _merge_stage_counts(stages, freshness_result["stages"])
        sample_record_ids.extend(freshness_result["sample_record_ids"])
        errors.extend(freshness_result["errors"])
        errors.extend(
            _freshness_errors(
                freshness_envelope.records,
                settings,
                now=now,
                error_prefix="freshness_probe: ",
            )
        )
        if freshness_result["fetched"] == 0:
            errors.append("freshness_probe: Source returned no records")
        if freshness_result["valid"] == 0:
            errors.append("freshness_probe: No valid records")

    if len(envelope.records) == 0:
        errors.append("Source returned no records for the canary page")
    if len(envelope.records) > 0 and valid == 0 and settings.get("record_filters"):
        errors.append("Source returned no records matching record_filters")
    failed = fetched - valid - skipped
    return SourceCanaryResult(
        source_id=source.id,
        source_key=source.key,
        ok=valid > 0 and failed == 0 and not errors,
        records_fetched=fetched,
        records_valid=valid,
        records_failed=failed,
        approval_stages=stages,
        sample_record_ids=sample_record_ids[:10],
        next_checkpoint=dict(envelope.checkpoint) if envelope.checkpoint else None,
        errors=errors,
    )


def validate_candidate_source_canary(
    candidate: IngestionSourceCandidate,
    *,
    sample_size: int = 10,
    now: datetime | None = None,
) -> CandidateCanaryResult:
    if candidate.status != "operational_retry":
        raise ValueError("Only operational_retry candidates can run canaries")
    if not candidate.can_run_canary:
        raise ValueError("Candidate does not declare runnable canary probe settings")
    runtime_source = _candidate_runtime_source(candidate)
    result = validate_source_canary(runtime_source, sample_size=sample_size, now=now)
    return CandidateCanaryResult(
        candidate_key=candidate.key,
        candidate_name=candidate.name,
        ok=result.ok,
        records_fetched=result.records_fetched,
        records_valid=result.records_valid,
        records_failed=result.records_failed,
        approval_stages=result.approval_stages,
        sample_record_ids=result.sample_record_ids,
        next_checkpoint=result.next_checkpoint,
        errors=result.errors,
    )


def record_candidate_canary_attempt(
    db: Session,
    candidate: IngestionSourceCandidate,
    result: CandidateCanaryResult,
    *,
    sample_size: int,
) -> IngestionCandidateCanaryAttempt:
    attempt = IngestionCandidateCanaryAttempt(
        organization_id=get_org_id(),
        candidate_key=candidate.key,
        candidate_name=candidate.name,
        sample_size=sample_size,
        ok=result.ok,
        records_fetched=result.records_fetched,
        records_valid=result.records_valid,
        records_failed=result.records_failed,
        approval_stages=dict(result.approval_stages),
        sample_record_ids=list(result.sample_record_ids),
        next_checkpoint=dict(result.next_checkpoint) if result.next_checkpoint else None,
        errors=list(result.errors),
    )
    db.add(attempt)
    db.flush()
    return attempt


def list_candidate_canary_attempts(
    db: Session,
    candidate_key: str,
    *,
    limit: int = 20,
) -> list[IngestionCandidateCanaryAttempt]:
    return (
        active_query(db.query(IngestionCandidateCanaryAttempt), IngestionCandidateCanaryAttempt)
        .filter(IngestionCandidateCanaryAttempt.candidate_key == candidate_key)
        .order_by(IngestionCandidateCanaryAttempt.created_at.desc())
        .limit(limit)
        .all()
    )


def _candidate_runtime_source(candidate: IngestionSourceCandidate) -> Any:
    mappings = [
        SimpleNamespace(
            source_field=mapping.source_field,
            canonical_field=mapping.canonical_field,
            transform=mapping.transform,
            transform_options=mapping.transform_options,
            default_value=mapping.default_value,
            is_required=mapping.is_required,
            is_active=mapping.is_active,
        )
        for mapping in candidate.probe_field_mappings
    ]
    return SimpleNamespace(
        id=f"candidate:{candidate.key}",
        key=candidate.key,
        name=candidate.name,
        adapter=candidate.adapter,
        record_type=candidate.record_type,
        jurisdiction=candidate.jurisdiction,
        base_url=candidate.base_url,
        settings=dict(candidate.probe_settings or {}),
        field_mappings=mappings,
    )


def _validate_canary_records(
    source: IngestionSource,
    records: tuple[dict[str, Any], ...],
    *,
    mappings: list[Any],
    settings: dict[str, Any],
    extra_required_fields: set[str],
    record_filters: Any,
    error_prefix: str = "",
) -> dict[str, Any]:
    valid = 0
    skipped = 0
    stages: dict[str, int] = {}
    sample_record_ids: list[str] = []
    observed_record_ids: set[str] = set()
    duplicate_record_ids: set[str] = set()
    errors: list[str] = []
    for index, record in enumerate(records, start=1):
        if not _record_matches_filters(record, record_filters):
            skipped += 1
            continue
        try:
            missing = missing_required_source_fields(
                record,
                mappings,
                extra_required_fields=extra_required_fields,
            )
            if missing:
                raise ValueError(f"Missing required source fields: {missing}")
            prepared, field_mapping = prepare_mapped_record(record, mappings)
            defaults = {
                **dict(settings.get("defaults") or {}),
                **({"jurisdiction": source.jurisdiction} if source.jurisdiction else {}),
            }
            normalized = (
                normalize_parcel(prepared, field_mapping, defaults=defaults)
                if source.record_type == "parcel"
                else normalize_permit(prepared, field_mapping, defaults=defaults)
            )
            valid += 1
            source_record_id = normalized.source_record_id
            if source_record_id in observed_record_ids:
                duplicate_record_ids.add(source_record_id)
            observed_record_ids.add(source_record_id)
            sample_record_ids.append(source_record_id)
            stage = (
                "parcel_snapshot"
                if source.record_type == "parcel"
                else normalized.values.get("approval_stage") or "unclassified"
            )
            stages[stage] = stages.get(stage, 0) + 1
        except Exception as exc:
            if len(errors) < 10:
                errors.append(f"{error_prefix}Record {index}: {type(exc).__name__}: {exc}")
    if duplicate_record_ids and len(errors) < 10:
        errors.append(
            f"{error_prefix}Duplicate normalized source_record_id values in canary sample: "
            f"{sorted(duplicate_record_ids)[:10]}"
        )
    return {
        "fetched": len(records),
        "valid": valid,
        "skipped": skipped,
        "stages": stages,
        "sample_record_ids": sample_record_ids,
        "errors": errors,
    }


def _merge_stage_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for stage, count in source.items():
        target[stage] = target.get(stage, 0) + count


def _freshness_errors(
    records: tuple[dict[str, Any], ...],
    settings: dict[str, Any],
    *,
    now: datetime,
    error_prefix: str = "",
) -> list[str]:
    freshness_field = settings.get("freshness_field")
    if not isinstance(freshness_field, str) or not freshness_field:
        return []
    watermarks: list[datetime] = []
    errors: list[str] = []
    for index, record in enumerate(records, start=1):
        value = record.get(freshness_field)
        if value is None or value == "":
            continue
        try:
            watermarks.append(parse_source_datetime(value))
        except Exception as exc:
            if len(errors) < 3:
                errors.append(
                    f"{error_prefix}Record {index}: invalid freshness field "
                    f"{freshness_field!r}: {type(exc).__name__}: {exc}"
                )
    if errors or not watermarks:
        return errors
    newest = max(_as_utc(value) for value in watermarks)
    lag_hours = _hours_between(now, newest)
    sla_hours = float(settings.get("freshness_sla_hours", 36))
    if lag_hours > sla_hours:
        return [
            f"{error_prefix}Latest canary source watermark is {lag_hours:.1f} "
            f"hours old; exceeds the {sla_hours:g}-hour SLA"
        ]
    return []


def _merge_connector_config(
    base: dict[str, Any],
    override: Any,
    *,
    page_size: int,
    error_context: str = "canary_stage_probes connector overrides",
) -> dict[str, Any]:
    if not isinstance(override, dict):
        raise ValueError(f"{error_context} must be an object")
    merged = dict(base)
    for key, value in override.items():
        if key == "query" and isinstance(value, dict) and isinstance(merged.get("query"), dict):
            merged[key] = {**merged["query"], **value}
        else:
            merged[key] = value
    merged["page_size"] = page_size
    return merged
