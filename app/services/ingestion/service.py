from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.brand import PermitBrandMatch
from app.models.graph import (
    GraphEntityLink,
    GraphEntityType,
    GraphRelationship,
    GraphRelationshipType,
)
from app.models.ingestion import (
    IngestionRun,
    IngestionSource,
    PermitEvent,
    PermitRecord,
    RawSourceRecord,
    SourceFieldMapping,
)
from app.models.parcel import ParcelRecord
from app.schemas.graph import GraphEntityCreate, GraphEvidenceCreate, GraphRelationshipCreate
from app.schemas.ingestion import IngestionSourceCreate, IngestionSourceUpdate
from app.schemas.ingestion_candidate import IngestionSourceCandidate
from app.services.brand_intelligence import detect_permit_brands
from app.services.graph_service import create_relationship, link_entity_to_record, resolve_entity
from app.services.ingestion.connector_config import resolve_connector_config_dates
from app.services.ingestion.connectors import ConnectorResponseError, build_connector
from app.services.ingestion.normalization import (
    NormalizedParcel,
    NormalizedPermit,
    missing_required_source_fields,
    normalize_parcel,
    normalize_permit,
    parse_source_datetime,
    prepare_mapped_record,
)
from app.services.parcel_ingestion import ParcelFactInput, upsert_parcel_snapshot
from app.utils.org_scope import active_query, get_org_id

PERMIT_COLUMNS = {
    "application_number",
    "permit_number",
    "approval_stage",
    "permit_type",
    "permit_subtype",
    "work_class",
    "review_type",
    "proposed_use",
    "occupancy_type",
    "status",
    "description",
    "project_name",
    "address",
    "city",
    "state",
    "postal_code",
    "parcel_id",
    "jurisdiction",
    "applicant_name",
    "owner_name",
    "developer_name",
    "contractor_name",
    "contractor_license",
    "architect_name",
    "engineer_name",
    "valuation",
    "square_feet",
    "units",
    "latitude",
    "longitude",
    "filed_at",
    "status_updated_at",
    "approved_at",
    "issued_at",
    "expires_at",
    "completed_at",
    "source_url",
}
HEARTBEAT_INTERVAL_SECONDS = 30.0
STALE_RUN_AFTER = timedelta(minutes=5)
SNAPSHOT_CHECKPOINT_KEY = "_build_signals_snapshot"
SNAPSHOT_CHECKPOINT_VERSION = 1


class ActiveRunConflict(ValueError):
    """Raised when a source already has a live ingestion lease."""


class RunLeaseLost(RuntimeError):
    """Raised when a reclaimed worker attempts to commit more work."""


class SnapshotReconciliationGuard(RuntimeError):
    """Raised when a completed snapshot would retire an unsafe amount of data."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _record_matches_filters(record: dict[str, Any], filters: Any) -> bool:
    if not filters:
        return True
    if not isinstance(filters, list):
        raise ValueError("record_filters must be a list")
    for filter_spec in filters:
        if not isinstance(filter_spec, dict):
            raise ValueError("record_filters entries must be objects")
        field = filter_spec.get("field")
        if not isinstance(field, str) or not field:
            raise ValueError("record_filters entries require a field")
        if "values" in filter_spec:
            values = filter_spec["values"]
            if not isinstance(values, list):
                raise ValueError("record_filters values must be a list")
            allowed = {str(value).casefold() for value in values}
            if str(record.get(field, "")).casefold() not in allowed:
                return False
        elif "value" in filter_spec:
            if str(record.get(field, "")).casefold() != str(filter_spec["value"]).casefold():
                return False
        else:
            raise ValueError("record_filters entries require value or values")
    return True


def list_sources(db: Session) -> list[IngestionSource]:
    return active_query(db.query(IngestionSource), IngestionSource).options(
        joinedload(IngestionSource.field_mappings)
    ).order_by(IngestionSource.name).all()


def get_source(db: Session, source_id: str) -> Optional[IngestionSource]:
    return active_query(db.query(IngestionSource), IngestionSource).options(
        joinedload(IngestionSource.field_mappings)
    ).filter(IngestionSource.id == source_id).first()


def get_permit_detail(db: Session, permit_id: str) -> Optional[PermitRecord]:
    return active_query(db.query(PermitRecord), PermitRecord).options(
        joinedload(PermitRecord.source),
        joinedload(PermitRecord.latest_raw_record),
        joinedload(PermitRecord.events),
    ).filter(PermitRecord.id == permit_id).first()


def create_source(db: Session, payload: IngestionSourceCreate) -> IngestionSource:
    existing = active_query(db.query(IngestionSource), IngestionSource).filter(
        IngestionSource.key == payload.key
    ).first()
    if existing:
        raise ValueError(f"Ingestion source key already exists: {payload.key}")
    source = IngestionSource(
        organization_id=get_org_id(),
        key=payload.key,
        name=payload.name,
        adapter=payload.adapter.lower(),
        record_type=payload.record_type,
        jurisdiction=payload.jurisdiction,
        base_url=payload.base_url,
        settings=payload.settings or None,
        is_active=payload.is_active,
    )
    db.add(source)
    db.flush()
    _replace_field_mappings(db, source, payload.field_mappings)
    return source


def update_source(db: Session, source: IngestionSource, payload: IngestionSourceUpdate) -> IngestionSource:
    changes = payload.model_dump(exclude_unset=True, exclude={"field_mappings"})
    for field, value in changes.items():
        setattr(source, field, value)
    if payload.field_mappings is not None:
        _replace_field_mappings(db, source, payload.field_mappings)
    source.updated_at = utcnow()
    db.flush()
    return source


def _candidate_to_source_payload(candidate: IngestionSourceCandidate) -> IngestionSourceCreate:
    settings = dict(candidate.probe_settings or {})
    if candidate.production_page_size is not None:
        connector = dict(settings.get("connector") or {})
        connector["page_size"] = candidate.production_page_size
        settings["connector"] = connector
    settings.setdefault("official_landing_page", candidate.official_landing_page)
    settings.setdefault("license", candidate.license)
    if candidate.probe_settings and candidate.probe_settings.get("signal_stage"):
        settings.setdefault("signal_stage", candidate.probe_settings["signal_stage"])
    settings.setdefault("reconciliation_mode", settings.get("reconciliation_mode") or "candidate_promoted")
    settings.setdefault("candidate_key", candidate.key)
    settings.setdefault("candidate_status", candidate.status)
    unique_field_mappings: list[dict[str, Any]] = []
    seen_source_fields: set[str] = set()
    for mapping in candidate.probe_field_mappings:
        if mapping.source_field in seen_source_fields:
          continue
        seen_source_fields.add(mapping.source_field)
        unique_field_mappings.append(mapping.model_dump())
    return IngestionSourceCreate(
        key=candidate.key,
        name=candidate.name,
        adapter=candidate.adapter,
        record_type=candidate.record_type,
        jurisdiction=candidate.jurisdiction,
        base_url=candidate.base_url,
        settings=settings,
        is_active=True,
        field_mappings=unique_field_mappings,
    )


def promote_candidate_to_source(db: Session, candidate: IngestionSourceCandidate) -> IngestionSource:
    existing = active_query(db.query(IngestionSource), IngestionSource).filter(
        IngestionSource.key == candidate.key
    ).first()
    if existing:
        return existing
    source = create_source(db, _candidate_to_source_payload(candidate))
    db.flush()
    return source


def _replace_field_mappings(db: Session, source: IngestionSource, mappings: Iterable[Any]) -> None:
    for row in list(source.field_mappings):
        db.delete(row)
    db.flush()
    for mapping in mappings:
        db.add(SourceFieldMapping(
            organization_id=get_org_id(),
            source_id=source.id,
            **mapping.model_dump(),
        ))
    db.flush()
    db.expire(source, ["field_mappings"])


def execute_source_run(
    db: Session,
    source: IngestionSource,
    *,
    max_pages: int = 1,
    checkpoint: Optional[dict[str, Any]] = None,
    trigger: str = "manual",
) -> IngestionRun:
    if max_pages < 1 or max_pages > 100:
        raise ValueError("max_pages must be between 1 and 100")
    source = get_source(db, source.id)
    if source is None:
        raise ValueError("Ingestion source not found")
    if not source.is_active:
        raise ValueError("Ingestion source is inactive")
    if source.record_type not in {"permit", "parcel"}:
        raise ValueError(f"No normalizer registered for record type: {source.record_type}")

    settings = dict(source.settings or {})
    connector_checkpoint, snapshot_id = _snapshot_context(settings, checkpoint)
    connector_config = resolve_connector_config_dates(dict(settings.get("connector") or {}))
    if source.base_url:
        connector_config.setdefault("source" if source.adapter == "csv" else "endpoint", source.base_url)
    connector = build_connector(source.adapter, connector_config)
    active_mappings = [row for row in source.field_mappings if row.is_active]
    if "source_record_id" not in {row.canonical_field for row in active_mappings}:
        raise ValueError("Source requires an active mapping to source_record_id")
    normalization_hash = _normalization_hash(source)
    stale_run_after_seconds = settings.get(
        "stale_run_after_seconds", STALE_RUN_AFTER.total_seconds()
    )
    if isinstance(stale_run_after_seconds, bool) or float(stale_run_after_seconds) <= 0:
        raise ValueError("stale_run_after_seconds must be positive")

    run = _claim_source_run(
        db,
        source.id,
        checkpoint=checkpoint,
        trigger=trigger,
        parameters={
            "max_pages": max_pages,
            **({"snapshot_id": snapshot_id} if snapshot_id else {}),
        },
        stale_after=timedelta(seconds=float(stale_run_after_seconds)),
    )
    run_id = run.id

    current_checkpoint = connector_checkpoint
    records_seen = 0
    records_inserted = 0
    records_updated = 0
    records_failed = 0
    error_message: str | None = None
    last_heartbeat = time.monotonic()
    try:
        terminal_status: str | None = None
        for _page_number in range(max_pages):
            page_checkpoint = current_checkpoint
            failures_before_page = records_failed
            envelope = _fetch_with_heartbeats(db, run_id, connector, current_checkpoint)
            last_heartbeat = time.monotonic()
            if envelope.has_more and envelope.checkpoint == current_checkpoint:
                raise ConnectorResponseError(
                    "connector returned a repeated checkpoint while more pages remain"
            )
            for record in envelope.records:
                records_seen += 1
                if not _record_matches_filters(record, settings.get("record_filters")):
                    continue
                try:
                    with db.begin_nested():
                        missing = missing_required_source_fields(record, active_mappings)
                        if missing:
                            raise ValueError(f"Missing required source fields: {missing}")
                        prepared_record, field_mapping = prepare_mapped_record(
                            record, active_mappings
                        )
                        defaults = {
                            **dict(settings.get("defaults") or {}),
                            **({"jurisdiction": source.jurisdiction} if source.jurisdiction else {}),
                        }
                        if source.record_type == "parcel":
                            normalized_parcel = normalize_parcel(
                                prepared_record, field_mapping, defaults=defaults
                            )
                            _parcel, action = _persist_parcel(
                                db, source, run_id, normalized_parcel, record,
                                envelope.fetched_at, normalization_hash, snapshot_id,
                            )
                        else:
                            normalized_permit = normalize_permit(
                                prepared_record, field_mapping, defaults=defaults
                            )
                            _permit, action = _persist_permit(
                                db, source, run_id, normalized_permit, record,
                                envelope.fetched_at, normalization_hash, snapshot_id,
                            )
                    if action == "created":
                        records_inserted += 1
                    elif action in {"updated", "reprocessed"}:
                        records_updated += 1
                except Exception as record_exc:
                    records_failed += 1
                    if not error_message:
                        error_message = (
                            f"Record {records_seen}: {type(record_exc).__name__}: {record_exc}"
                        )[:4000]
                    if settings.get("fail_fast", False):
                        raise
                if time.monotonic() - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                    _commit_run_progress(
                        db,
                        run_id,
                        checkpoint=_stored_checkpoint(page_checkpoint, snapshot_id),
                        records_seen=records_seen,
                        records_inserted=records_inserted,
                        records_updated=records_updated,
                        records_failed=records_failed,
                        error_message=error_message,
                    )
                    last_heartbeat = time.monotonic()

            if records_failed > failures_before_page:
                terminal_status = "partial_with_errors"
                current_checkpoint = page_checkpoint
                break
            current_checkpoint = dict(envelope.checkpoint) if envelope.checkpoint else None
            if not envelope.has_more:
                terminal_status = "completed"
                break
            _commit_run_progress(
                db,
                run_id,
                checkpoint=_stored_checkpoint(current_checkpoint, snapshot_id),
                records_seen=records_seen,
                records_inserted=records_inserted,
                records_updated=records_updated,
                records_failed=records_failed,
                error_message=error_message,
            )
            last_heartbeat = time.monotonic()
        else:
            terminal_status = "partial" if current_checkpoint else "completed"

        if terminal_status == "completed" and snapshot_id:
            _retire_missing_snapshot_records(db, source, snapshot_id, settings)
        final_checkpoint = (
            None if terminal_status == "completed" and snapshot_id
            else _stored_checkpoint(current_checkpoint, snapshot_id)
        )
        _finish_run(
            db,
            run_id,
            status=terminal_status or "completed",
            checkpoint=final_checkpoint,
            records_seen=records_seen,
            records_inserted=records_inserted,
            records_updated=records_updated,
            records_failed=records_failed,
            error_message=error_message,
        )
    except KeyboardInterrupt:
        db.rollback()
        _fail_run(
            db,
            run_id,
            "Interrupted by operator",
            records_seen=records_seen,
            records_inserted=records_inserted,
            records_updated=records_updated,
            records_failed=records_failed,
        )
        raise
    except Exception as exc:
        db.rollback()
        _fail_run(
            db,
            run_id,
            str(exc)[:4000],
            records_seen=records_seen,
            records_inserted=records_inserted,
            records_updated=records_updated,
            records_failed=records_failed,
        )
    return _load_run(db, run_id)


def _claim_source_run(
    db: Session,
    source_id: str,
    *,
    checkpoint: dict[str, Any] | None,
    trigger: str,
    parameters: dict[str, Any],
    stale_after: timedelta = STALE_RUN_AFTER,
) -> IngestionRun:
    if stale_after.total_seconds() <= 0:
        raise ValueError("stale_after must be positive")
    db.commit()
    now = utcnow()
    running = active_query(db.query(IngestionRun), IngestionRun).filter(
        IngestionRun.source_id == source_id,
        IngestionRun.status == "running",
    ).order_by(IngestionRun.started_at.desc()).first()
    if running is not None:
        heartbeat = _as_utc(running.heartbeat_at)
        if now - heartbeat <= stale_after:
            db.rollback()
            raise ActiveRunConflict(
                f"Ingestion source already has a running job: {running.id}"
            )
        reclaimed = db.execute(
            update(IngestionRun).where(
                IngestionRun.id == running.id,
                IngestionRun.status == "running",
                IngestionRun.heartbeat_at == running.heartbeat_at,
            ).values(
                status="failed",
                completed_at=now,
                heartbeat_at=now,
                error_message="Run lease expired and was reclaimed",
            )
        )
        if reclaimed.rowcount != 1:
            db.rollback()
            raise ActiveRunConflict("Ingestion source lease changed while claiming")
        db.commit()

    run = IngestionRun(
        organization_id=get_org_id(),
        source_id=source_id,
        status="running",
        trigger=trigger,
        checkpoint=checkpoint,
        parameters=parameters,
        heartbeat_at=now,
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ActiveRunConflict("Ingestion source already has a running job") from exc
    return _load_run(db, run.id)


def _fetch_with_heartbeats(db: Session, run_id: str, connector, checkpoint):
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingestion-fetch")
    future = executor.submit(connector.fetch_page, checkpoint)
    try:
        while True:
            try:
                return future.result(timeout=HEARTBEAT_INTERVAL_SECONDS)
            except FutureTimeoutError:
                _renew_run_lease(db, run_id)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _renew_run_lease(db: Session, run_id: str) -> None:
    result = db.execute(
        update(IngestionRun).where(
            IngestionRun.id == run_id,
            IngestionRun.status == "running",
        ).values(heartbeat_at=utcnow())
    )
    if result.rowcount != 1:
        db.rollback()
        raise RunLeaseLost(f"Ingestion run lease was lost: {run_id}")
    db.commit()


def _commit_run_progress(
    db: Session,
    run_id: str,
    *,
    checkpoint: dict[str, Any] | None,
    records_seen: int,
    records_inserted: int,
    records_updated: int,
    records_failed: int,
    error_message: str | None,
) -> None:
    result = db.execute(
        update(IngestionRun).where(
            IngestionRun.id == run_id,
            IngestionRun.status == "running",
        ).values(
            heartbeat_at=utcnow(),
            checkpoint=checkpoint,
            records_seen=records_seen,
            records_inserted=records_inserted,
            records_updated=records_updated,
            records_failed=records_failed,
            error_message=error_message,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise RunLeaseLost(f"Ingestion run lease was lost: {run_id}")
    db.commit()


def _finish_run(
    db: Session,
    run_id: str,
    *,
    status: str,
    checkpoint: dict[str, Any] | None,
    records_seen: int,
    records_inserted: int,
    records_updated: int,
    records_failed: int,
    error_message: str | None,
) -> None:
    now = utcnow()
    result = db.execute(
        update(IngestionRun).where(
            IngestionRun.id == run_id,
            IngestionRun.status == "running",
        ).values(
            status=status,
            heartbeat_at=now,
            completed_at=now,
            checkpoint=checkpoint,
            records_seen=records_seen,
            records_inserted=records_inserted,
            records_updated=records_updated,
            records_failed=records_failed,
            error_message=error_message,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise RunLeaseLost(f"Ingestion run lease was lost: {run_id}")
    db.commit()


def _fail_run(
    db: Session,
    run_id: str,
    error_message: str,
    *,
    records_seen: int | None = None,
    records_inserted: int | None = None,
    records_updated: int | None = None,
    records_failed: int | None = None,
) -> None:
    now = utcnow()
    values: dict[str, Any] = {
        "status": "failed",
        "heartbeat_at": now,
        "completed_at": now,
        "error_message": error_message,
    }
    if records_seen is not None:
        values["records_seen"] = records_seen
    if records_inserted is not None:
        values["records_inserted"] = records_inserted
    if records_updated is not None:
        values["records_updated"] = records_updated
    if records_failed is not None:
        values["records_failed"] = records_failed
    result = db.execute(
        update(IngestionRun).where(
            IngestionRun.id == run_id,
            IngestionRun.status == "running",
        ).values(**values)
    )
    if result.rowcount == 1:
        db.commit()
    else:
        db.rollback()


def _load_run(db: Session, run_id: str) -> IngestionRun:
    return active_query(db.query(IngestionRun), IngestionRun).filter(
        IngestionRun.id == run_id
    ).one()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _persist_permit(
    db: Session,
    source: IngestionSource,
    run_id: str,
    normalized: NormalizedPermit,
    source_record: Any,
    fetched_at: datetime,
    normalization_hash: str,
    snapshot_id: str | None = None,
) -> tuple[PermitRecord, str]:
    raw = active_query(db.query(RawSourceRecord), RawSourceRecord).filter(
        RawSourceRecord.source_id == source.id,
        RawSourceRecord.external_record_id == normalized.source_record_id,
        RawSourceRecord.content_hash == normalized.fingerprint,
    ).first()
    permit = active_query(db.query(PermitRecord), PermitRecord).filter(
        PermitRecord.source_id == source.id,
        PermitRecord.external_record_id == normalized.source_record_id,
    ).first()

    raw_was_existing = raw is not None
    if raw is not None and permit is not None and permit.normalization_hash == normalization_hash:
        was_inactive = not permit.is_active
        permit.last_seen_at = fetched_at
        permit.last_seen_snapshot_id = snapshot_id
        permit.is_active = True
        permit.retired_at = None
        if was_inactive:
            db.add(PermitEvent(
                organization_id=get_org_id(),
                permit_id=permit.id,
                raw_source_record_id=raw.id,
                source_event_id=f"reactivated:{snapshot_id or fetched_at.isoformat()}",
                event_type="reactivated",
                status=permit.status,
                approval_stage=permit.approval_stage,
                occurred_at=fetched_at,
                description=permit.description,
                attributes={"snapshot_id": snapshot_id},
            ))
            detect_permit_brands(db, permit, raw)
            _project_permit_to_graph(db, source, permit, raw)
            return permit, "reprocessed"
        return permit, "unchanged"

    if raw is None:
        raw = RawSourceRecord(
            organization_id=get_org_id(),
            source_id=source.id,
            run_id=run_id,
            external_record_id=normalized.source_record_id,
            record_type=source.record_type,
            content_hash=normalized.fingerprint,
            payload=_json_safe(source_record),
            source_updated_at=_source_updated_at(source, source_record),
            received_at=fetched_at,
        )
        db.add(raw)
        db.flush()

    values = {key: value for key, value in normalized.values.items() if key in PERMIT_COLUMNS}
    values["attributes"] = normalized.unmapped or None
    if permit is None:
        permit = PermitRecord(
            organization_id=get_org_id(),
            source_id=source.id,
            latest_raw_record_id=raw.id,
            external_record_id=normalized.source_record_id,
            normalization_hash=normalization_hash,
            first_seen_at=fetched_at,
            last_seen_at=fetched_at,
            last_seen_snapshot_id=snapshot_id,
            is_active=True,
            **values,
        )
        db.add(permit)
        event_type = "created"
    else:
        for field in PERMIT_COLUMNS:
            setattr(permit, field, values.get(field))
        permit.attributes = values.get("attributes")
        permit.latest_raw_record_id = raw.id
        permit.normalization_hash = normalization_hash
        permit.last_seen_at = fetched_at
        permit.last_seen_snapshot_id = snapshot_id
        was_inactive = not permit.is_active
        permit.is_active = True
        permit.retired_at = None
        event_type = "reactivated" if was_inactive else (
            "reprocessed" if raw_was_existing else "updated"
        )
    db.flush()

    occurred_at = (
        permit.completed_at
        or permit.issued_at
        or permit.approved_at
        or permit.status_updated_at
        or permit.filed_at
        or fetched_at
    )
    db.add(PermitEvent(
        organization_id=get_org_id(),
        permit_id=permit.id,
        raw_source_record_id=raw.id,
        source_event_id=f"{normalized.fingerprint}:{normalization_hash}",
        event_type=event_type,
        status=permit.status,
        approval_stage=permit.approval_stage,
        occurred_at=occurred_at,
        description=permit.description,
        attributes={"content_hash": normalized.fingerprint},
    ))
    db.flush()
    detect_permit_brands(db, permit, raw)
    _project_permit_to_graph(db, source, permit, raw)
    return permit, event_type


def _persist_parcel(
    db: Session,
    source: IngestionSource,
    run_id: str,
    normalized: NormalizedParcel,
    source_record: Any,
    fetched_at: datetime,
    normalization_hash: str,
    snapshot_id: str | None = None,
) -> tuple[ParcelRecord, str]:
    raw = active_query(db.query(RawSourceRecord), RawSourceRecord).filter(
        RawSourceRecord.source_id == source.id,
        RawSourceRecord.external_record_id == normalized.source_record_id,
        RawSourceRecord.content_hash == normalized.fingerprint,
    ).first()
    parcel = active_query(db.query(ParcelRecord), ParcelRecord).filter(
        ParcelRecord.source_id == source.id,
        ParcelRecord.external_parcel_id == normalized.source_record_id,
    ).first()
    if raw is not None and parcel is not None and parcel.normalization_hash == normalization_hash:
        was_inactive = not parcel.is_active
        parcel.last_seen_at = fetched_at
        parcel.last_verified_at = fetched_at
        parcel.last_seen_snapshot_id = snapshot_id
        parcel.is_active = True
        parcel.retired_at = None
        _project_parcel_to_graph(db, source, parcel, raw)
        return parcel, "reprocessed" if was_inactive else "unchanged"

    if raw is None:
        raw = RawSourceRecord(
            organization_id=get_org_id(),
            source_id=source.id,
            run_id=run_id,
            external_record_id=normalized.source_record_id,
            record_type=source.record_type,
            content_hash=normalized.fingerprint,
            payload=_json_safe(source_record),
            source_updated_at=_source_updated_at(source, source_record),
            received_at=fetched_at,
        )
        db.add(raw)
        db.flush()

    values = normalized.values
    facts = _parcel_facts(values, source, fetched_at)
    parcel, action = upsert_parcel_snapshot(
        db,
        source=source,
        raw_record=raw,
        external_parcel_id=normalized.source_record_id,
        values=values,
        facts=facts,
        verified_at=fetched_at,
        normalization_hash=normalization_hash,
        snapshot_id=snapshot_id,
        attributes=normalized.unmapped or None,
    )
    _project_parcel_to_graph(db, source, parcel, raw)
    return parcel, action


def _parcel_facts(
    values: dict[str, Any], source: IngestionSource, observed_at: datetime
) -> list[ParcelFactInput]:
    source_url = values.get("source_url") or source.base_url
    groups = {
        "ownership": ("owner_name", "owner_mailing_address"),
        "last_sale": ("last_sale_date", "last_sale_price"),
        "tax_status": ("tax_delinquent",),
        "vacancy": ("vacancy_indicator",),
    }
    facts: list[ParcelFactInput] = []
    for fact_type, fields in groups.items():
        value = {field: values[field] for field in fields if values.get(field) is not None}
        if not value:
            continue
        facts.append(ParcelFactInput(
            fact_type=fact_type,
            value=_json_safe(value),
            source_url=source_url,
            field_path=",".join(value),
            excerpt="; ".join(f"{field}={value[field]}" for field in value),
            confidence=1.0,
            observed_at=values.get("observed_at") or observed_at,
        ))
    return facts


def _snapshot_context(
    settings: dict[str, Any],
    checkpoint: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    mode = str(settings.get("reconciliation_mode") or "")
    if "full" not in mode:
        return checkpoint, None
    if checkpoint and isinstance(checkpoint.get(SNAPSHOT_CHECKPOINT_KEY), dict):
        state = checkpoint[SNAPSHOT_CHECKPOINT_KEY]
        if state.get("version") != SNAPSHOT_CHECKPOINT_VERSION:
            raise ValueError("Unsupported snapshot checkpoint version")
        snapshot_id = state.get("snapshot_id")
        connector_checkpoint = state.get("connector_checkpoint")
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise ValueError("Snapshot checkpoint is missing snapshot_id")
        if connector_checkpoint is not None and not isinstance(connector_checkpoint, dict):
            raise ValueError("Snapshot connector checkpoint must be an object")
        return connector_checkpoint, snapshot_id
    if checkpoint is not None:
        # Legacy checkpoints have no generation provenance and must never retire data.
        return checkpoint, None
    return None, str(uuid4())


def _stored_checkpoint(
    connector_checkpoint: dict[str, Any] | None,
    snapshot_id: str | None,
) -> dict[str, Any] | None:
    if connector_checkpoint is None:
        return None
    if snapshot_id is None:
        return connector_checkpoint
    return {
        SNAPSHOT_CHECKPOINT_KEY: {
            "version": SNAPSHOT_CHECKPOINT_VERSION,
            "snapshot_id": snapshot_id,
            "connector_checkpoint": connector_checkpoint,
        }
    }


def _retire_missing_snapshot_records(
    db: Session,
    source: IngestionSource,
    snapshot_id: str,
    settings: dict[str, Any],
) -> int:
    if source.record_type == "parcel":
        return _retire_missing_parcels(db, source, snapshot_id, settings)
    now = utcnow()
    permits = active_query(db.query(PermitRecord), PermitRecord).filter(
        PermitRecord.source_id == source.id,
        PermitRecord.is_active.is_(True),
        PermitRecord.last_seen_snapshot_id != snapshot_id,
    ).all()
    # SQL NULL does not compare unequal, so include records predating snapshot tracking.
    permits.extend(active_query(db.query(PermitRecord), PermitRecord).filter(
        PermitRecord.source_id == source.id,
        PermitRecord.is_active.is_(True),
        PermitRecord.last_seen_snapshot_id.is_(None),
    ).all())
    unique_permits = list({permit.id: permit for permit in permits}.values())
    active_count = active_query(db.query(PermitRecord), PermitRecord).filter(
        PermitRecord.source_id == source.id,
        PermitRecord.is_active.is_(True),
    ).count()
    seen_count = active_query(db.query(PermitRecord), PermitRecord).filter(
        PermitRecord.source_id == source.id,
        PermitRecord.last_seen_snapshot_id == snapshot_id,
    ).count()
    allow_empty = bool(settings.get("allow_empty_snapshot", False))
    if active_count and seen_count == 0 and not allow_empty:
        raise SnapshotReconciliationGuard(
            "Completed snapshot was empty; set allow_empty_snapshot only after verification"
        )
    max_fraction = float(settings.get("max_snapshot_retirement_fraction", 0.25))
    if not 0 <= max_fraction <= 1:
        raise ValueError("max_snapshot_retirement_fraction must be between 0 and 1")
    retirement_fraction = len(unique_permits) / active_count if active_count else 0
    if retirement_fraction > max_fraction:
        raise SnapshotReconciliationGuard(
            "Completed snapshot would retire "
            f"{retirement_fraction:.1%} of active records; configured maximum is "
            f"{max_fraction:.1%}"
        )
    for permit in unique_permits:
        permit.is_active = False
        permit.retired_at = now
        db.add(PermitEvent(
            organization_id=get_org_id(),
            permit_id=permit.id,
            raw_source_record_id=permit.latest_raw_record_id,
            source_event_id=f"retired:{snapshot_id}",
            event_type="retired_from_source_snapshot",
            status=permit.status,
            approval_stage=permit.approval_stage,
            occurred_at=now,
            description=permit.description,
            attributes={"snapshot_id": snapshot_id},
        ))
        matches = active_query(db.query(PermitBrandMatch), PermitBrandMatch).filter(
            PermitBrandMatch.permit_id == permit.id,
            PermitBrandMatch.review_status.in_(("candidate", "confirmed")),
        ).all()
        for match in matches:
            match.review_status = "retracted"
            match.last_seen_at = now
        _expire_permit_relationships(db, source, permit)
    db.flush()
    return len(unique_permits)


def _retire_missing_parcels(
    db: Session,
    source: IngestionSource,
    snapshot_id: str,
    settings: dict[str, Any],
) -> int:
    parcels = active_query(db.query(ParcelRecord), ParcelRecord).filter(
        ParcelRecord.source_id == source.id,
        ParcelRecord.is_active.is_(True),
        ParcelRecord.last_seen_snapshot_id != snapshot_id,
    ).all()
    parcels.extend(active_query(db.query(ParcelRecord), ParcelRecord).filter(
        ParcelRecord.source_id == source.id,
        ParcelRecord.is_active.is_(True),
        ParcelRecord.last_seen_snapshot_id.is_(None),
    ).all())
    missing = list({parcel.id: parcel for parcel in parcels}.values())
    active_count = active_query(db.query(ParcelRecord), ParcelRecord).filter(
        ParcelRecord.source_id == source.id,
        ParcelRecord.is_active.is_(True),
    ).count()
    seen_count = active_query(db.query(ParcelRecord), ParcelRecord).filter(
        ParcelRecord.source_id == source.id,
        ParcelRecord.last_seen_snapshot_id == snapshot_id,
    ).count()
    if active_count and seen_count == 0 and not bool(settings.get("allow_empty_snapshot", False)):
        raise SnapshotReconciliationGuard(
            "Completed parcel snapshot was empty; set allow_empty_snapshot only after verification"
        )
    max_fraction = float(settings.get("max_snapshot_retirement_fraction", 0.25))
    if not 0 <= max_fraction <= 1:
        raise ValueError("max_snapshot_retirement_fraction must be between 0 and 1")
    retirement_fraction = len(missing) / active_count if active_count else 0
    if retirement_fraction > max_fraction:
        raise SnapshotReconciliationGuard(
            "Completed parcel snapshot would retire "
            f"{retirement_fraction:.1%} of active records; configured maximum is "
            f"{max_fraction:.1%}"
        )
    now = utcnow()
    for parcel in missing:
        parcel.is_active = False
        parcel.retired_at = now
        _expire_parcel_relationships(db, source, parcel)
    db.flush()
    return len(missing)


def _source_updated_at(
    source: IngestionSource,
    source_record: Any,
) -> datetime | None:
    freshness_field = (source.settings or {}).get("freshness_field")
    if not freshness_field:
        return None
    if not isinstance(freshness_field, str):
        raise ValueError("source freshness_field must be a string")
    value = source_record.get(freshness_field)
    if value is None or value == "":
        raise ValueError(f"Source record is missing freshness field: {freshness_field}")
    return parse_source_datetime(value)


def _project_parcel_to_graph(
    db: Session,
    source: IngestionSource,
    parcel: ParcelRecord,
    raw: RawSourceRecord,
) -> None:
    stable_id = _bounded_source_id(source.key, parcel.external_parcel_id)
    parcel_entity, _ = resolve_entity(db, GraphEntityCreate(
        entity_type=GraphEntityType.parcel,
        display_name=parcel.external_parcel_id,
        source_system=source.key,
        source_id=stable_id,
        address=parcel.address,
        city=parcel.city,
        state=parcel.state,
        zip_code=parcel.postal_code,
        attributes=_json_safe({
            "parcel_record_id": parcel.id,
            "parcel_group_id": parcel.parcel_group_id,
            "county": parcel.county,
            "jurisdiction": parcel.jurisdiction,
            "land_use": parcel.land_use,
            "zoning_code": parcel.zoning_code,
            "latitude": parcel.latitude,
            "longitude": parcel.longitude,
        }),
    ))
    link_entity_to_record(db, parcel_entity.id, "parcel", parcel.id, source.key)

    ownership = next(
        (
            fact for fact in parcel.facts
            if fact.is_current
            and fact.fact_type == "ownership"
            and isinstance(fact.value, dict)
            and fact.value.get("owner_name")
        ),
        None,
    )
    if ownership is None:
        return
    owner_name = str(ownership.value["owner_name"]).strip()
    if not owner_name:
        return
    owner, _ = resolve_entity(db, GraphEntityCreate(
        entity_type=GraphEntityType.owner,
        display_name=owner_name,
        attributes={"mailing_address": ownership.value.get("owner_mailing_address")},
    ))
    relationship_source_id = _bounded_source_id(source.key, parcel.external_parcel_id, "owner")
    _expire_parcel_relationships(
        db,
        source,
        parcel,
        keep_current={(relationship_source_id, owner.id)},
    )
    create_relationship(db, GraphRelationshipCreate(
        source_entity_id=parcel_entity.id,
        target_entity_id=owner.id,
        relationship_type=GraphRelationshipType.owned_by,
        confidence=ownership.confidence,
        source_system=source.key,
        source_id=relationship_source_id,
        attributes={
            "parcel_record_id": parcel.id,
            "parcel_fact_id": ownership.id,
            "role": "owner",
        },
        evidence=[GraphEvidenceCreate(
            source_system=source.key,
            source_id=raw.id,
            source_url=ownership.source_url or source.base_url,
            evidence_type="parcel_ownership",
            excerpt=ownership.excerpt,
            observed_at=ownership.observed_at,
            confidence=ownership.confidence,
            payload={
                "raw_record_id": raw.id,
                "content_hash": raw.content_hash,
                "parcel_fact_id": ownership.id,
            },
        )],
    ), validate_entities=False)


def _expire_parcel_relationships(
    db: Session,
    source: IngestionSource,
    parcel: ParcelRecord,
    keep_current: set[tuple[str | None, str]] | None = None,
) -> None:
    link = active_query(db.query(GraphEntityLink), GraphEntityLink).filter(
        GraphEntityLink.record_type == "parcel",
        GraphEntityLink.record_id == parcel.id,
    ).first()
    if link is None:
        return
    relationships = active_query(db.query(GraphRelationship), GraphRelationship).filter(
        GraphRelationship.source_entity_id == link.entity_id,
        GraphRelationship.source_system == source.key,
        GraphRelationship.is_current.is_(True),
    ).all()
    now = utcnow()
    for relationship in relationships:
        if keep_current and (relationship.source_id, relationship.target_entity_id) in keep_current:
            continue
        relationship.is_current = False
        relationship.valid_to = now


def _project_permit_to_graph(
    db: Session,
    source: IngestionSource,
    permit: PermitRecord,
    raw: RawSourceRecord,
) -> None:
    stable_id = _bounded_source_id(source.key, permit.external_record_id)
    permit_entity, _ = resolve_entity(db, GraphEntityCreate(
        entity_type=GraphEntityType.permit,
        display_name=permit.permit_number or permit.application_number or stable_id,
        source_system=source.key,
        source_id=stable_id,
        address=permit.address,
        city=permit.city,
        state=permit.state,
        zip_code=permit.postal_code,
        attributes={
            "permit_record_id": permit.id,
            "status": permit.status,
            "approval_stage": permit.approval_stage,
            "permit_type": permit.permit_type,
            "work_class": permit.work_class,
            "review_type": permit.review_type,
            "proposed_use": permit.proposed_use,
            "occupancy_type": permit.occupancy_type,
        },
    ))
    link_entity_to_record(db, permit_entity.id, "permit", permit.id, source.key)
    _expire_permit_relationships(db, source, permit)

    if not (permit.address or permit.project_name):
        return
    property_entity, _ = resolve_entity(db, GraphEntityCreate(
        entity_type=GraphEntityType.property,
        display_name=permit.project_name or permit.address or stable_id,
        address=permit.address,
        city=permit.city,
        state=permit.state,
        zip_code=permit.postal_code,
        attributes={"jurisdiction": permit.jurisdiction},
    ))
    _relate(db, source, permit, raw, permit_entity.id, property_entity.id, GraphRelationshipType.permit_for, "property")

    if permit.parcel_id:
        parcel, _ = resolve_entity(db, GraphEntityCreate(
            entity_type=GraphEntityType.parcel,
            display_name=permit.parcel_id,
            address=permit.address,
            city=permit.city,
            state=permit.state,
            zip_code=permit.postal_code,
        ))
        _relate(db, source, permit, raw, property_entity.id, parcel.id, GraphRelationshipType.located_on, "parcel")

    party_specs = (
        (permit.owner_name, GraphEntityType.owner, GraphRelationshipType.owned_by, "owner", None),
        (permit.developer_name, GraphEntityType.developer, GraphRelationshipType.developed_by, "developer", None),
        (permit.contractor_name, GraphEntityType.general_contractor, GraphRelationshipType.contracted_by, "contractor", {"license": permit.contractor_license}),
        (permit.architect_name, GraphEntityType.architect, GraphRelationshipType.designed_by, "architect", None),
        (permit.engineer_name, GraphEntityType.engineer, GraphRelationshipType.engineer_for, "engineer", None),
    )
    for name, entity_type, relationship_type, role, attributes in party_specs:
        if not name:
            continue
        entity, _ = resolve_entity(db, GraphEntityCreate(
            entity_type=entity_type,
            display_name=name,
            attributes=attributes,
        ))
        _relate(db, source, permit, raw, property_entity.id, entity.id, relationship_type, role)

    if permit.jurisdiction:
        city, _ = resolve_entity(db, GraphEntityCreate(
            entity_type=GraphEntityType.city,
            display_name=permit.jurisdiction,
            state=permit.state,
        ))
        _relate(db, source, permit, raw, property_entity.id, city.id, GraphRelationshipType.permitted_by, "jurisdiction")

    brand_matches = active_query(db.query(PermitBrandMatch), PermitBrandMatch).filter(
        PermitBrandMatch.permit_id == permit.id,
        PermitBrandMatch.review_status.in_(("candidate", "confirmed")),
    ).all()
    for match in brand_matches:
        brand = match.brand
        company, _ = resolve_entity(db, GraphEntityCreate(
            entity_type=GraphEntityType.company,
            display_name=brand.name,
            source_system="brand_catalog",
            source_id=brand.key,
            confidence=match.confidence,
            aliases=[alias.alias for alias in brand.aliases if alias.is_active],
            attributes={"category": brand.category, "scale": brand.scale},
        ))
        _relate(
            db,
            source,
            permit,
            raw,
            property_entity.id,
            company.id,
            GraphRelationshipType.related_to,
            f"prospective_retailer:{brand.key}",
            confidence=match.confidence,
            excerpt=match.excerpt,
            attributes={
                "brand_match_id": match.id,
                "review_status": match.review_status,
            },
        )


def _relate(
    db: Session,
    source: IngestionSource,
    permit: PermitRecord,
    raw: RawSourceRecord,
    source_entity_id: str,
    target_entity_id: str,
    relationship_type: GraphRelationshipType,
    role: str,
    *,
    confidence: float = 1.0,
    excerpt: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> None:
    create_relationship(db, GraphRelationshipCreate(
        source_entity_id=source_entity_id,
        target_entity_id=target_entity_id,
        relationship_type=relationship_type,
        confidence=confidence,
        source_system=source.key,
        source_id=_bounded_source_id(source.key, permit.external_record_id, role),
        attributes={
            "permit_record_id": permit.id,
            "role": role,
            **(attributes or {}),
        },
        evidence=[GraphEvidenceCreate(
            source_system=source.key,
            source_id=raw.id,
            source_url=permit.source_url or source.base_url,
            evidence_type="permit_record",
            excerpt=excerpt or (permit.description or "")[:1000] or None,
            observed_at=raw.received_at,
            payload={"raw_record_id": raw.id, "content_hash": raw.content_hash},
        )],
    ), validate_entities=False)


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _bounded_source_id(*parts: str) -> str:
    value = ":".join(parts)
    if len(value) <= 255:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{value[:189]}:{digest}"


def _normalization_hash(source: IngestionSource) -> str:
    payload = {
        "record_type": source.record_type,
        "jurisdiction": source.jurisdiction,
        "defaults": dict((source.settings or {}).get("defaults") or {}),
        "mappings": sorted(
            [
                {
                    "source_field": row.source_field,
                    "canonical_field": row.canonical_field,
                    "value_semantics": row.value_semantics,
                    "transform": row.transform,
                    "transform_options": row.transform_options,
                    "default_value": row.default_value,
                    "is_required": row.is_required,
                }
                for row in source.field_mappings
                if row.is_active
            ],
            key=lambda row: (row["source_field"], row["canonical_field"]),
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _expire_permit_relationships(
    db: Session,
    source: IngestionSource,
    permit: PermitRecord,
) -> None:
    role_ids = [
        _bounded_source_id(source.key, permit.external_record_id, role)
        for role in (
            "property",
            "parcel",
            "owner",
            "developer",
            "contractor",
            "architect",
            "engineer",
            "jurisdiction",
        )
    ]
    brand_matches = active_query(db.query(PermitBrandMatch), PermitBrandMatch).filter(
        PermitBrandMatch.permit_id == permit.id
    ).all()
    role_ids.extend(
        _bounded_source_id(
            source.key,
            permit.external_record_id,
            f"prospective_retailer:{match.brand.key}",
        )
        for match in brand_matches
    )
    now = utcnow()
    relationships = active_query(db.query(GraphRelationship), GraphRelationship).filter(
        GraphRelationship.source_system == source.key,
        GraphRelationship.source_id.in_(role_ids),
        GraphRelationship.is_current.is_(True),
    ).all()
    for relationship in relationships:
        relationship.is_current = False
        relationship.valid_to = now
