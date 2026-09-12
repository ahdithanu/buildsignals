from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from uuid import uuid4

from sqlalchemy import func, or_, tuple_, update
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
    RawSourceRecordObservation,
    RecordExternalReference,
    SourceFieldMapping,
)
from app.models.parcel import ParcelRecord
from app.models.planning import PlanningCompanyMatch, PlanningRecord
from app.schemas.graph import GraphEntityCreate, GraphEvidenceCreate, GraphRelationshipCreate
from app.schemas.ingestion import IngestionSourceCreate, IngestionSourceUpdate
from app.services.brand_intelligence import detect_permit_brands, rebuild_brand_party_fingerprints
from app.services.graph_service import create_relationship, link_entity_to_record, resolve_entity
from app.services.ingestion.connector_config import resolve_connector_config_dates
from app.services.ingestion.connectors import ConnectorResponseError, build_connector
from app.services.ingestion.external_references import extract_external_references
from app.services.ingestion.normalization import (
    NormalizedParcel,
    NormalizedPermit,
    NormalizedPlanningRecord,
    missing_required_source_fields,
    normalize_parcel,
    normalize_permit,
    normalize_planning_record,
    parse_source_datetime,
    prepare_mapped_record,
)
from app.services.parcel_ingestion import ParcelFactInput, upsert_parcel_snapshot
from app.services.parcel_lineage import upsert_lineage_from_snapshot
from app.services.planning_intelligence import enrich_planning_record
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
PLANNING_COLUMNS = {
    "reference_number",
    "event_type",
    "stage",
    "title",
    "summary",
    "evidence_excerpt",
    "agenda_item_number",
    "meeting_name",
    "governing_body",
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
    "latitude",
    "longitude",
    "meeting_at",
    "published_at",
    "decision_at",
    "source_url",
    "confidence",
}


@dataclass(frozen=True)
class ExternalReferenceBackfillBatchResult:
    scanned: int
    references_created: int
    references_refreshed: int
    references_removed: int
    records_linked: int
    next_cursor: str | None
    has_more: bool


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


def resolve_stale_run_after(settings: dict | None) -> timedelta:
    value = (settings or {}).get(
        "stale_run_after_seconds", STALE_RUN_AFTER.total_seconds()
    )
    if isinstance(value, bool):
        raise ValueError("stale_run_after_seconds must be positive")
    try:
        seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("stale_run_after_seconds must be positive") from exc
    if seconds <= 0:
        raise ValueError("stale_run_after_seconds must be positive")
    return timedelta(seconds=seconds)


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
    if source.record_type not in {"permit", "parcel", "planning"}:
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
    run = _claim_source_run(
        db,
        source.id,
        checkpoint=checkpoint,
        trigger=trigger,
        parameters={
            "max_pages": max_pages,
            **({"snapshot_id": snapshot_id} if snapshot_id else {}),
        },
        stale_after=resolve_stale_run_after(settings),
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
                        elif source.record_type == "planning":
                            normalized_planning = normalize_planning_record(
                                prepared_record, field_mapping, defaults=defaults
                            )
                            _planning, action = _persist_planning_record(
                                db,
                                source,
                                run_id,
                                normalized_planning,
                                record,
                                envelope.fetched_at,
                                normalization_hash,
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
    _touch_raw_observation(db, raw, fetched_at)
    if permit is not None:
        _sync_record_external_references(db, source, "permit", permit.id, raw, fetched_at)

    if (
        raw_was_existing
        and permit is not None
        and permit.latest_raw_record_id == raw.id
        and permit.normalization_hash == normalization_hash
    ):
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
            confirmed_brand_ids = {
                brand_id
                for (brand_id,) in active_query(
                    db.query(PermitBrandMatch.brand_id), PermitBrandMatch
                ).filter(
                    PermitBrandMatch.permit_id == permit.id,
                    PermitBrandMatch.review_status == "confirmed",
                ).all()
            }
            for brand_id in confirmed_brand_ids:
                rebuild_brand_party_fingerprints(db, brand_id)
            _project_permit_to_graph(db, source, permit, raw)
            return permit, "reprocessed"
        permit_entity_id = _record_entity_id(db, "permit", permit.id)
        if permit_entity_id:
            _reconcile_planning_permit_links(
                db, permit=permit, permit_entity_id=permit_entity_id
            )
        return permit, "unchanged"

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
    _sync_record_external_references(db, source, "permit", permit.id, raw, fetched_at)

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
        source_event_id=(
            f"{normalized.fingerprint}:{normalization_hash}:reobserved:{fetched_at.isoformat()}"
            if raw_was_existing
            else f"{normalized.fingerprint}:{normalization_hash}"
        ),
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
    raw_was_existing = raw is not None
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
    _touch_raw_observation(db, raw, fetched_at)

    if (
        raw_was_existing
        and parcel is not None
        and parcel.latest_raw_record_id == raw.id
        and parcel.normalization_hash == normalization_hash
    ):
        was_inactive = not parcel.is_active
        parcel.last_seen_at = fetched_at
        parcel.last_verified_at = fetched_at
        parcel.last_seen_snapshot_id = snapshot_id
        parcel.is_active = True
        parcel.retired_at = None
        for fact in parcel.facts:
            if fact.is_current:
                fact.last_verified_at = fetched_at
        _project_parcel_to_graph(db, source, parcel, raw)
        upsert_lineage_from_snapshot(
            db,
            source=source,
            raw_record=raw,
            current_parcel=parcel,
            values=normalized.values,
            verified_at=fetched_at,
        )
        return parcel, "reprocessed" if was_inactive else "unchanged"

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
    upsert_lineage_from_snapshot(
        db,
        source=source,
        raw_record=raw,
        current_parcel=parcel,
        values=values,
        verified_at=fetched_at,
    )
    return parcel, action


def _persist_planning_record(
    db: Session,
    source: IngestionSource,
    run_id: str,
    normalized: NormalizedPlanningRecord,
    source_record: Any,
    fetched_at: datetime,
    normalization_hash: str,
) -> tuple[PlanningRecord, str]:
    raw = active_query(db.query(RawSourceRecord), RawSourceRecord).filter(
        RawSourceRecord.source_id == source.id,
        RawSourceRecord.external_record_id == normalized.source_record_id,
        RawSourceRecord.content_hash == normalized.fingerprint,
    ).first()
    planning = active_query(db.query(PlanningRecord), PlanningRecord).filter(
        PlanningRecord.source_id == source.id,
        PlanningRecord.external_record_id == normalized.source_record_id,
    ).first()
    raw_was_existing = raw is not None
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
    _touch_raw_observation(db, raw, fetched_at)
    if planning is not None:
        _sync_record_external_references(
            db, source, "planning", planning.id, raw, fetched_at
        )

    if raw_was_existing and planning is not None and planning.normalization_hash == normalization_hash:
        planning.last_seen_at = fetched_at
        planning_entity_id = _record_entity_id(db, "planning", planning.id)
        if planning_entity_id:
            _reconcile_planning_permit_links(
                db, planning=planning, planning_entity_id=planning_entity_id
            )
        return planning, "unchanged"

    values = {key: value for key, value in normalized.values.items() if key in PLANNING_COLUMNS}
    if planning is None:
        planning = PlanningRecord(
            organization_id=get_org_id(),
            source_id=source.id,
            latest_raw_record_id=raw.id,
            external_record_id=normalized.source_record_id,
            normalization_hash=normalization_hash,
            attributes=normalized.unmapped or None,
            first_seen_at=fetched_at,
            last_seen_at=fetched_at,
            **values,
        )
        db.add(planning)
        action = "created"
    else:
        for field in PLANNING_COLUMNS:
            setattr(planning, field, values.get(field))
        planning.latest_raw_record_id = raw.id
        planning.normalization_hash = normalization_hash
        planning.attributes = normalized.unmapped or None
        planning.last_seen_at = fetched_at
        action = "updated"
    db.flush()
    _sync_record_external_references(db, source, "planning", planning.id, raw, fetched_at)
    matches = enrich_planning_record(db, planning, raw)
    _project_planning_to_graph(db, source, planning, raw, matches)
    return planning, action


def _touch_raw_observation(
    db: Session,
    raw: RawSourceRecord,
    observed_at: datetime,
) -> RawSourceRecordObservation:
    values = {
        "organization_id": get_org_id(),
        "raw_source_record_id": raw.id,
        "last_observed_at": observed_at,
    }
    dialect_name = db.get_bind().dialect.name
    table = RawSourceRecordObservation.__table__
    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert

        statement = insert(table).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[table.c.raw_source_record_id],
            set_={
                "last_observed_at": func.greatest(
                    table.c.last_observed_at,
                    statement.excluded.last_observed_at,
                )
            },
        )
        db.execute(statement)
    elif dialect_name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert

        statement = insert(table).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[table.c.raw_source_record_id],
            set_={
                "last_observed_at": func.max(
                    table.c.last_observed_at,
                    statement.excluded.last_observed_at,
                )
            },
        )
        db.execute(statement)
    else:
        return _touch_raw_observation_fallback(db, raw, observed_at)

    return active_query(
        db.query(RawSourceRecordObservation), RawSourceRecordObservation
    ).populate_existing().filter(
        RawSourceRecordObservation.raw_source_record_id == raw.id
    ).one()


def _touch_raw_observation_fallback(
    db: Session,
    raw: RawSourceRecord,
    observed_at: datetime,
) -> RawSourceRecordObservation:
    observation = active_query(
        db.query(RawSourceRecordObservation), RawSourceRecordObservation
    ).filter(
        RawSourceRecordObservation.raw_source_record_id == raw.id
    ).first()
    if observation is None:
        observation = RawSourceRecordObservation(
            organization_id=get_org_id(),
            raw_source_record_id=raw.id,
            last_observed_at=observed_at,
        )
        db.add(observation)
    elif _as_utc(observed_at) > _as_utc(observation.last_observed_at):
        observation.last_observed_at = observed_at
    return observation


def _sync_record_external_references(
    db: Session,
    source: IngestionSource,
    record_type: str,
    record_id: str,
    raw: RawSourceRecord,
    verified_at: datetime,
) -> None:
    extracted = extract_external_references(raw.payload, source.settings or {})
    current = active_query(
        db.query(RecordExternalReference), RecordExternalReference
    ).filter(
        RecordExternalReference.record_type == record_type,
        RecordExternalReference.record_id == record_id,
    ).all()
    by_identity = {(row.namespace, row.normalized_value): row for row in current}
    keep: set[tuple[str, str]] = set()
    for reference in extracted:
        identity = (reference.namespace, reference.normalized_value)
        keep.add(identity)
        row = by_identity.get(identity)
        if row is None:
            db.add(
                RecordExternalReference(
                    organization_id=get_org_id(),
                    record_type=record_type,
                    record_id=record_id,
                    raw_source_record_id=raw.id,
                    namespace=reference.namespace,
                    normalized_value=reference.normalized_value,
                    source_field=reference.source_field,
                    source_url=reference.source_url,
                    last_verified_at=verified_at,
                )
            )
            continue
        row.raw_source_record_id = raw.id
        row.source_field = reference.source_field
        row.source_url = reference.source_url
        row.last_verified_at = verified_at
    for identity, row in by_identity.items():
        if identity not in keep:
            db.delete(row)
    db.flush()


def backfill_external_references_batch(
    db: Session,
    *,
    record_type: str,
    source_key: str | None = None,
    after_id: str | None = None,
    batch_size: int = 500,
) -> ExternalReferenceBackfillBatchResult:
    """Index configured official references without refetching source records."""
    if record_type not in {"permit", "planning"}:
        raise ValueError("record_type must be permit or planning")
    if batch_size < 1 or batch_size > 5_000:
        raise ValueError("batch_size must be between 1 and 5000")

    source_query = active_query(db.query(IngestionSource), IngestionSource).filter(
        IngestionSource.is_active.is_(True),
        IngestionSource.record_type == record_type,
    )
    if source_key:
        source_query = source_query.filter(IngestionSource.key == source_key)
    sources = source_query.all()
    if source_key and not sources:
        raise ValueError(f"active {record_type} source not found: {source_key}")
    eligible_source_ids = {
        source.id
        for source in sources
        if (source.settings or {}).get("external_reference_extractors")
    }
    if source_key and not eligible_source_ids:
        raise ValueError(f"source has no external reference extractors: {source_key}")
    if not eligible_source_ids:
        return ExternalReferenceBackfillBatchResult(0, 0, 0, 0, 0, after_id, False)

    model = PermitRecord if record_type == "permit" else PlanningRecord
    query = active_query(db.query(model), model).options(
        joinedload(model.source),
        joinedload(model.latest_raw_record),
    ).filter(model.source_id.in_(eligible_source_ids))
    if record_type == "permit":
        query = query.filter(PermitRecord.is_active.is_(True))
    if after_id:
        query = query.filter(model.id > after_id)
    rows = query.order_by(model.id).limit(batch_size + 1).all()
    records = rows[:batch_size]
    if not records:
        return ExternalReferenceBackfillBatchResult(0, 0, 0, 0, 0, after_id, False)

    created = refreshed = removed = linked = 0
    for record in records:
        before = {
            (reference.namespace, reference.normalized_value)
            for reference in _record_external_references(db, record_type, record.id)
        }
        _sync_record_external_references(
            db,
            record.source,
            record_type,
            record.id,
            record.latest_raw_record,
            utcnow(),
        )
        after = {
            (reference.namespace, reference.normalized_value)
            for reference in _record_external_references(db, record_type, record.id)
        }
        created += len(after - before)
        refreshed += len(after & before)
        removed += len(before - after)

        entity_id = _record_entity_id(db, record_type, record.id)
        if entity_id is None:
            if record_type == "permit":
                _project_permit_to_graph(
                    db, record.source, record, record.latest_raw_record
                )
            else:
                _project_planning_to_graph(
                    db,
                    record.source,
                    record,
                    record.latest_raw_record,
                    list(record.company_matches),
                )
            entity_id = _record_entity_id(db, record_type, record.id)
        elif record_type == "permit":
            _reconcile_planning_permit_links(
                db, permit=record, permit_entity_id=entity_id
            )
        else:
            _reconcile_planning_permit_links(
                db, planning=record, planning_entity_id=entity_id
            )
        if entity_id and _has_current_external_reference_link(
            db, record_type=record_type, entity_id=entity_id
        ):
            linked += 1

    db.flush()
    return ExternalReferenceBackfillBatchResult(
        scanned=len(records),
        references_created=created,
        references_refreshed=refreshed,
        references_removed=removed,
        records_linked=linked,
        next_cursor=records[-1].id,
        has_more=len(rows) > batch_size,
    )


def _has_current_external_reference_link(
    db: Session, *, record_type: str, entity_id: str
) -> bool:
    query = active_query(db.query(GraphRelationship), GraphRelationship).filter(
        GraphRelationship.relationship_type == GraphRelationshipType.related_to,
        GraphRelationship.is_current.is_(True),
    )
    if record_type == "planning":
        query = query.filter(GraphRelationship.source_entity_id == entity_id)
    else:
        query = query.filter(GraphRelationship.target_entity_id == entity_id)
    return any(
        (relationship.attributes or {}).get("role")
        == "official_external_reference_match"
        for relationship in query.all()
    )


def _parcel_facts(
    values: dict[str, Any], source: IngestionSource, observed_at: datetime
) -> list[ParcelFactInput]:
    source_url = values.get("source_url") or source.base_url
    groups = {
        "ownership": ("owner_name", "owner_mailing_address"),
        "last_sale": ("last_sale_date", "last_sale_price"),
        "tax_status": ("tax_delinquent",),
        "vacancy": ("vacancy_indicator",),
        "zoning": ("zoning_code",),
        "land_use": ("land_use",),
        "improvements": ("improvement_area_sq_ft", "improvement_value"),
        "valuation": ("land_value", "total_assessed_value"),
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
    if source.record_type == "planning":
        # Rolling agenda feeds omit old items without rescinding the public record.
        return 0
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
        confirmed_brand_ids = {
            match.brand_id for match in matches if match.review_status == "confirmed"
        }
        for match in matches:
            if match.review_status == "candidate":
                match.review_status = "retracted"
        _expire_permit_relationships(db, source, permit)
        for brand_id in confirmed_brand_ids:
            rebuild_brand_party_fingerprints(db, brand_id)
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
        _expire_parcel_relationships(db, source, parcel)
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


def _project_planning_to_graph(
    db: Session,
    source: IngestionSource,
    planning: PlanningRecord,
    raw: RawSourceRecord,
    company_matches: list[PlanningCompanyMatch],
) -> None:
    stable_id = _bounded_source_id(source.key, planning.external_record_id)
    event_entity, _ = resolve_entity(
        db,
        GraphEntityCreate(
            entity_type=GraphEntityType.source_record,
            # Graph labels are shorter than planning titles; retain the full title on the record.
            display_name=planning.title[:255],
            source_system=source.key,
            source_id=stable_id,
            address=planning.address,
            city=planning.city,
            state=planning.state,
            zip_code=planning.postal_code,
            confidence=planning.confidence,
            attributes={
                "planning_record_id": planning.id,
                "reference_number": planning.reference_number,
                "event_type": planning.event_type,
                "stage": planning.stage,
                "meeting_at": planning.meeting_at.isoformat() if planning.meeting_at else None,
                "signal_categories": planning.signal_categories,
                "priority_score": planning.priority_score,
            },
        ),
    )
    link_entity_to_record(db, event_entity.id, "planning", planning.id, source.key)
    evidence = GraphEvidenceCreate(
        source_system=source.key,
        source_id=raw.id,
        source_url=planning.source_url or source.base_url,
        evidence_type="public_planning_record",
        excerpt=planning.evidence_excerpt or planning.summary or planning.title,
        observed_at=planning.published_at or planning.meeting_at or raw.received_at,
        confidence=planning.confidence,
        payload={
            "raw_record_id": raw.id,
            "content_hash": raw.content_hash,
            "source_url": planning.source_url or source.base_url,
            "source_updated_at": raw.source_updated_at.isoformat()
            if raw.source_updated_at
            else None,
            "received_at": raw.received_at.isoformat(),
        },
    )
    _reconcile_planning_permit_links(db, planning=planning, planning_entity_id=event_entity.id)

    if planning.address or planning.project_name or planning.parcel_id:
        property_entity, _ = resolve_entity(
            db,
            GraphEntityCreate(
                entity_type=GraphEntityType.property,
                display_name=planning.project_name
                or planning.address
                or planning.parcel_id
                or stable_id,
                source_system=source.key if planning.parcel_id else None,
                source_id=_bounded_source_id(source.key, planning.parcel_id)
                if planning.parcel_id
                else None,
                address=planning.address,
                city=planning.city,
                state=planning.state,
                zip_code=planning.postal_code,
                attributes={
                    "parcel_id": planning.parcel_id,
                    "latitude": planning.latitude,
                    "longitude": planning.longitude,
                },
            ),
        )
        create_relationship(
            db,
            GraphRelationshipCreate(
                source_entity_id=event_entity.id,
                target_entity_id=property_entity.id,
                relationship_type=GraphRelationshipType.related_to,
                confidence=planning.confidence,
                source_system=source.key,
                source_id=_bounded_source_id(stable_id, "property"),
                attributes={"role": "planning_subject", "planning_record_id": planning.id},
                evidence=[evidence],
            ),
            validate_entities=False,
        )

    named_companies = [
        (match.brand.name, match.confidence, "tracked_company") for match in company_matches
    ]
    named_companies.extend(
        (name, planning.confidence, role)
        for role, name in (
            ("applicant", planning.applicant_name),
            ("owner", planning.owner_name),
            ("developer", planning.developer_name),
        )
        if name
    )
    for index, (name, confidence, role) in enumerate(named_companies):
        company_entity, _ = resolve_entity(
            db,
            GraphEntityCreate(
                entity_type=GraphEntityType.company,
                display_name=name,
                confidence=confidence,
            ),
        )
        create_relationship(
            db,
            GraphRelationshipCreate(
                source_entity_id=event_entity.id,
                target_entity_id=company_entity.id,
                relationship_type=GraphRelationshipType.related_to,
                confidence=confidence,
                source_system=source.key,
                source_id=_bounded_source_id(stable_id, role, str(index)),
                attributes={"role": role, "planning_record_id": planning.id},
                evidence=[evidence],
            ),
            validate_entities=False,
        )


def _reconcile_planning_permit_links(
    db: Session,
    *,
    planning: PlanningRecord | None = None,
    planning_entity_id: str | None = None,
    permit: PermitRecord | None = None,
    permit_entity_id: str | None = None,
) -> None:
    """Link exact official references in either ingestion order using bounded lookups."""
    if planning is not None:
        reference = planning.reference_number
        if not planning_entity_id or not planning.city or not planning.state:
            return
        matched_permit_ids: set[str] = set()
        keep_links: set[tuple[str, str, str]] = set()
        if reference:
            permits = (
                active_query(db.query(PermitRecord), PermitRecord)
                .filter(
                    PermitRecord.is_active.is_(True),
                    func.lower(func.trim(PermitRecord.city)) == planning.city.strip().casefold(),
                    func.lower(func.trim(PermitRecord.state)) == planning.state.strip().casefold(),
                    or_(
                        PermitRecord.application_number == reference,
                        PermitRecord.permit_number == reference,
                    ),
                )
                .all()
            )
        else:
            permits = []
        for candidate in permits:
            if not _same_planning_scope(planning, candidate):
                continue
            candidate_entity_id = _record_entity_id(db, "permit", candidate.id)
            if candidate_entity_id:
                matched_permit_ids.add(candidate.id)
                keep_links.add(
                    (
                        planning_entity_id,
                        candidate_entity_id,
                        "canonical_permit_reference_match",
                    )
                )
                _create_planning_permit_link(
                    db,
                    planning,
                    planning_entity_id,
                    candidate,
                    candidate_entity_id,
                )
        for candidate, planning_ref, permit_ref in _external_reference_matches_for_planning(
            db, planning
        ):
            if candidate.id in matched_permit_ids or not _same_planning_scope(planning, candidate):
                continue
            candidate_entity_id = _record_entity_id(db, "permit", candidate.id)
            if candidate_entity_id:
                keep_links.add(
                    (
                        planning_entity_id,
                        candidate_entity_id,
                        "official_external_reference_match",
                    )
                )
                _create_planning_permit_link(
                    db,
                    planning,
                    planning_entity_id,
                    candidate,
                    candidate_entity_id,
                    planning_reference=planning_ref,
                    permit_reference=permit_ref,
                )
        _expire_stale_planning_permit_links(
            db, source_entity_id=planning_entity_id, keep_links=keep_links
        )
        return

    if permit is None or not permit_entity_id or not permit.city or not permit.state:
        return
    references = tuple(
        dict.fromkeys(
            reference
            for reference in (permit.application_number, permit.permit_number)
            if reference
        )
    )
    matched_planning_ids: set[str] = set()
    keep_links: set[tuple[str, str, str]] = set()
    planning_records = []
    if references:
        planning_records = (
            active_query(db.query(PlanningRecord), PlanningRecord)
            .filter(
                PlanningRecord.reference_number.in_(references),
                func.lower(func.trim(PlanningRecord.city)) == permit.city.strip().casefold(),
                func.lower(func.trim(PlanningRecord.state)) == permit.state.strip().casefold(),
            )
            .all()
        )
    for candidate in planning_records:
        if not _same_planning_scope(candidate, permit):
            continue
        candidate_entity_id = _record_entity_id(db, "planning", candidate.id)
        if candidate_entity_id:
            matched_planning_ids.add(candidate.id)
            keep_links.add(
                (
                    candidate_entity_id,
                    permit_entity_id,
                    "canonical_permit_reference_match",
                )
            )
            _create_planning_permit_link(
                db,
                candidate,
                candidate_entity_id,
                permit,
                permit_entity_id,
            )
    for candidate, planning_ref, permit_ref in _external_reference_matches_for_permit(db, permit):
        if candidate.id in matched_planning_ids or not _same_planning_scope(candidate, permit):
            continue
        candidate_entity_id = _record_entity_id(db, "planning", candidate.id)
        if candidate_entity_id:
            keep_links.add(
                (
                    candidate_entity_id,
                    permit_entity_id,
                    "official_external_reference_match",
                )
            )
            _create_planning_permit_link(
                db,
                candidate,
                candidate_entity_id,
                permit,
                permit_entity_id,
                planning_reference=planning_ref,
                permit_reference=permit_ref,
            )
    _expire_stale_planning_permit_links(
        db, target_entity_id=permit_entity_id, keep_links=keep_links
    )


def _expire_stale_planning_permit_links(
    db: Session,
    *,
    keep_links: set[tuple[str, str, str]],
    source_entity_id: str | None = None,
    target_entity_id: str | None = None,
) -> None:
    query = active_query(db.query(GraphRelationship), GraphRelationship).filter(
        GraphRelationship.relationship_type == GraphRelationshipType.related_to,
        GraphRelationship.is_current.is_(True),
    )
    if source_entity_id:
        query = query.filter(GraphRelationship.source_entity_id == source_entity_id)
    if target_entity_id:
        query = query.filter(GraphRelationship.target_entity_id == target_entity_id)
    now = utcnow()
    for relationship in query.all():
        role = (relationship.attributes or {}).get("role")
        if role not in {
            "canonical_permit_reference_match",
            "official_external_reference_match",
        }:
            continue
        identity = (
            relationship.source_entity_id,
            relationship.target_entity_id,
            role,
        )
        if identity not in keep_links:
            relationship.is_current = False
            relationship.valid_to = now


def _external_reference_matches_for_planning(
    db: Session, planning: PlanningRecord
) -> list[tuple[PermitRecord, RecordExternalReference, RecordExternalReference]]:
    references = _record_external_references(db, "planning", planning.id)
    identities = {(row.namespace, row.normalized_value) for row in references}
    if not identities:
        return []
    planning_by_identity = {(row.namespace, row.normalized_value): row for row in references}
    rows = (
        active_query(db.query(PermitRecord), PermitRecord)
        .join(
            RecordExternalReference,
            (RecordExternalReference.record_type == "permit")
            & (RecordExternalReference.record_id == PermitRecord.id),
        )
        .filter(
            RecordExternalReference.organization_id == get_org_id(),
            tuple_(
                RecordExternalReference.namespace,
                RecordExternalReference.normalized_value,
            ).in_(identities),
            PermitRecord.is_active.is_(True),
            func.lower(func.trim(PermitRecord.city)) == planning.city.strip().casefold(),
            func.lower(func.trim(PermitRecord.state)) == planning.state.strip().casefold(),
        )
        .with_entities(PermitRecord, RecordExternalReference)
        .all()
    )
    return [
        (permit, planning_by_identity[(reference.namespace, reference.normalized_value)], reference)
        for permit, reference in rows
    ]


def _external_reference_matches_for_permit(
    db: Session, permit: PermitRecord
) -> list[tuple[PlanningRecord, RecordExternalReference, RecordExternalReference]]:
    references = _record_external_references(db, "permit", permit.id)
    identities = {(row.namespace, row.normalized_value) for row in references}
    if not identities:
        return []
    permit_by_identity = {(row.namespace, row.normalized_value): row for row in references}
    rows = (
        active_query(db.query(PlanningRecord), PlanningRecord)
        .join(
            RecordExternalReference,
            (RecordExternalReference.record_type == "planning")
            & (RecordExternalReference.record_id == PlanningRecord.id),
        )
        .filter(
            RecordExternalReference.organization_id == get_org_id(),
            tuple_(
                RecordExternalReference.namespace,
                RecordExternalReference.normalized_value,
            ).in_(identities),
            func.lower(func.trim(PlanningRecord.city)) == permit.city.strip().casefold(),
            func.lower(func.trim(PlanningRecord.state)) == permit.state.strip().casefold(),
        )
        .with_entities(PlanningRecord, RecordExternalReference)
        .all()
    )
    return [
        (planning, reference, permit_by_identity[(reference.namespace, reference.normalized_value)])
        for planning, reference in rows
    ]


def _record_external_references(
    db: Session, record_type: str, record_id: str
) -> list[RecordExternalReference]:
    return active_query(
        db.query(RecordExternalReference), RecordExternalReference
    ).filter(
        RecordExternalReference.record_type == record_type,
        RecordExternalReference.record_id == record_id,
    ).all()


def _same_planning_scope(planning: PlanningRecord, permit: PermitRecord) -> bool:
    return bool(
        planning.city
        and permit.city
        and planning.state
        and permit.state
        and planning.city.strip().casefold() == permit.city.strip().casefold()
        and planning.state.strip().casefold() == permit.state.strip().casefold()
    )


def _record_entity_id(db: Session, record_type: str, record_id: str) -> str | None:
    link = active_query(db.query(GraphEntityLink), GraphEntityLink).filter(
        GraphEntityLink.record_type == record_type,
        GraphEntityLink.record_id == record_id,
    ).first()
    return link.entity_id if link else None


def _create_planning_permit_link(
    db: Session,
    planning: PlanningRecord,
    planning_entity_id: str,
    permit: PermitRecord,
    permit_entity_id: str,
    *,
    planning_reference: RecordExternalReference | None = None,
    permit_reference: RecordExternalReference | None = None,
) -> None:
    is_external_match = planning_reference is not None and permit_reference is not None
    reference = (
        planning_reference.normalized_value if planning_reference else planning.reference_number
    )
    if not reference or is_external_match != (permit_reference is not None):
        return
    source = planning.source
    raw = planning.latest_raw_record
    source_url = planning.source_url or source.base_url
    role = (
        "official_external_reference_match"
        if is_external_match
        else "canonical_permit_reference_match"
    )
    namespace = planning_reference.namespace if planning_reference else None
    attributes = {
        "role": role,
        "matched_reference": reference,
        "planning_record_id": planning.id,
        "permit_record_id": permit.id,
    }
    if namespace:
        attributes["reference_namespace"] = namespace
    create_relationship(
        db,
        GraphRelationshipCreate(
            source_entity_id=planning_entity_id,
            target_entity_id=permit_entity_id,
            relationship_type=GraphRelationshipType.related_to,
            confidence=planning.confidence,
            source_system=source.key,
            source_id=_bounded_source_id(
                source.key,
                planning.external_record_id,
                role,
                namespace or "canonical",
                permit.id,
            ),
            attributes=attributes,
            evidence=[
                GraphEvidenceCreate(
                    source_system=source.key,
                    source_id=raw.id,
                    source_url=source_url,
                    evidence_type=role,
                    excerpt=planning.evidence_excerpt or planning.summary or planning.title,
                    observed_at=planning.published_at or planning.meeting_at or raw.received_at,
                    confidence=planning.confidence,
                    payload={
                        "raw_record_id": raw.id,
                        "content_hash": raw.content_hash,
                        "source_url": source_url,
                        "reference_number": reference,
                        "reference_namespace": namespace,
                        "planning_reference_id": planning_reference.id
                        if planning_reference
                        else None,
                        "planning_reference_field": planning_reference.source_field
                        if planning_reference
                        else None,
                        "permit_reference_id": permit_reference.id
                        if permit_reference
                        else None,
                        "permit_reference_field": permit_reference.source_field
                        if permit_reference
                        else None,
                        "permit_reference_raw_record_id": permit_reference.raw_source_record_id
                        if permit_reference
                        else None,
                        "source_updated_at": raw.source_updated_at.isoformat()
                        if raw.source_updated_at
                        else None,
                        "received_at": raw.received_at.isoformat(),
                    },
                )
            ],
        ),
        validate_entities=False,
    )


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
    _reconcile_planning_permit_links(
        db,
        permit=permit,
        permit_entity_id=permit_entity.id,
    )
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
        signal_cohort = brand.signal_cohort
        company, _ = resolve_entity(db, GraphEntityCreate(
            entity_type=GraphEntityType.company,
            display_name=brand.name,
            source_system="brand_catalog",
            source_id=brand.key,
            confidence=match.confidence,
            aliases=[alias.alias for alias in brand.aliases if alias.is_active],
            attributes={
                "category": brand.category,
                "scale": brand.scale,
                "signal_cohort": signal_cohort,
            },
        ))
        _relate(
            db,
            source,
            permit,
            raw,
            property_entity.id,
            company.id,
            GraphRelationshipType.related_to,
            f"prospective_company:{brand.key}",
            confidence=match.confidence,
            excerpt=match.excerpt,
            attributes={
                "brand_match_id": match.id,
                "review_status": match.review_status,
                "signal_cohort": signal_cohort,
            },
        )


def project_permit_to_graph(db: Session, permit: PermitRecord) -> None:
    """Reconcile one canonical permit and its active company matches into the graph."""
    _project_permit_to_graph(db, permit.source, permit, permit.latest_raw_record)


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
            "source_record_active": True,
            "retired_from_source_snapshot": False,
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
            role,
        )
        for match in brand_matches
        for role in (
            f"prospective_retailer:{match.brand.key}",
            f"prospective_company:{match.brand.key}",
        )
    )
    now = utcnow()
    relationships = active_query(db.query(GraphRelationship), GraphRelationship).filter(
        GraphRelationship.source_system == source.key,
        GraphRelationship.source_id.in_(role_ids),
        GraphRelationship.is_current.is_(True),
    ).all()
    for relationship in relationships:
        relationship.attributes = {
            **(relationship.attributes or {}),
            "source_record_active": False,
            "retired_from_source_snapshot": True,
        }
        relationship.is_current = False
        relationship.valid_to = now
        relationship.last_verified_at = now
