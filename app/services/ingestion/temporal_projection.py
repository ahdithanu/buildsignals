"""Permit/planning adapters for the domain-neutral temporal observation store."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.ingestion import PermitRecord, RawSourceRecord
from app.models.planning import PlanningRecord
from app.models.temporal import TemporalEvent, TemporalObservation
from app.schemas.temporal import EventCreate, ObservationCreate
from app.services.temporal_service import (
    fingerprint,
    observation_series_key,
    record_event,
    record_observation,
    utc,
)
from app.utils.org_scope import active_query, get_org_id

PROJECTION_VERSION = "canonical-observation-v1"


def project_record_observations(
    db: Session, *, record: PermitRecord | PlanningRecord, raw: RawSourceRecord,
    entity_id: str, run_id: str,
) -> None:
    if isinstance(record, PermitRecord):
        prefix = "permit"
        fields = ["status", "approval_stage", "valuation", "square_feet", "units", "project_name"]
        lifecycle = {
            "filed_at": "permit.filed", "approved_at": "permit.approved",
            "issued_at": "permit.issued", "completed_at": "permit.completed",
        }
        status_field, status_date = "status", record.status_updated_at
        confidence = 1.0  # Exact canonical-field projection, not a predictive probability.
    else:
        prefix = "planning"
        fields = ["stage", "title", "project_name", "event_type"]
        lifecycle = {
            "published_at": "planning.published", "meeting_at": "planning.meeting_scheduled",
            "decision_at": "planning.decision_recorded",
        }
        status_field, status_date = "stage", None
        confidence = record.confidence
    geography = {
        field: float(getattr(record, field)) if field in {"latitude", "longitude"} else getattr(record, field)
        for field in ("city", "state", "postal_code", "jurisdiction", "latitude", "longitude")
        if getattr(record, field) is not None
    }
    method = f"{PROJECTION_VERSION}:{record.normalization_hash}"
    for field in [*fields, *lifecycle]:
        value = getattr(record, field)
        effective_at = value if isinstance(value, datetime) else status_date if field == status_field else None
        if isinstance(value, datetime):
            value = utc(value).isoformat()
        elif isinstance(value, Decimal):
            value = int(value) if field in {"square_feet", "units"} else format(value.quantize(Decimal("0.01")), "f")
        attribute = f"{prefix}.{field}"
        series_key = observation_series_key(entity_id, raw.source_id, raw.external_record_id, attribute, method)
        latest = active_query(db.query(TemporalObservation), TemporalObservation).filter(
            TemporalObservation.source_id == raw.source_id,
            TemporalObservation.attribute == attribute,
            TemporalObservation.methodology_version == method,
        ).join(RawSourceRecord, RawSourceRecord.id == TemporalObservation.raw_source_record_id).filter(
            RawSourceRecord.organization_id == get_org_id(),
            RawSourceRecord.source_id == raw.source_id,
            RawSourceRecord.external_record_id == raw.external_record_id,
        ).order_by(TemporalObservation.recorded_at.desc(), TemporalObservation.id.desc()).first()
        if value is None and latest is None:
            continue
        payload = ObservationCreate(
            entity_id=entity_id, raw_source_record_id=raw.id,
            observation_key=fingerprint([series_key, raw.id, run_id, latest.id if latest else None]),
            attribute=attribute, value=value, effective_at=utc(effective_at) if effective_at else None,
            unit={"valuation": "USD", "square_feet": "sq_ft", "units": "count"}.get(field),
            confidence=confidence, geography=geography or None,
            source_url=record.source_url, methodology_version=method,
        )
        content_hash = fingerprint(payload.model_dump(mode="json", exclude={"observation_key"}))
        if latest is not None and latest.content_hash == content_hash:
            observation = latest
        else:
            observation, _ = record_observation(db, payload)
        event_type = lifecycle.get(field)
        if field == status_field:
            event_type = f"{prefix}.{status_field}_observed"
        if event_type and value is not None and not _already_observed_event(
            db, raw=raw, event_type=event_type, value=value,
            occurred_at=utc(effective_at) if effective_at else None,
            state_observation=field == status_field,
        ):
            record_event(db, EventCreate(
                observation_id=observation.id, event_type=event_type,
                occurred_at=utc(effective_at) if effective_at else None,
            ))


def _already_observed_event(
    db: Session, *, raw: RawSourceRecord, event_type: str, value: object,
    occurred_at: datetime | None, state_observation: bool,
) -> bool:
    # Source lifecycle identity survives graph merges and unrelated mapping changes.
    query = active_query(db.query(TemporalEvent, TemporalObservation), TemporalEvent).join(
        TemporalObservation, TemporalObservation.id == TemporalEvent.observation_id,
    ).join(RawSourceRecord, RawSourceRecord.id == TemporalObservation.raw_source_record_id).filter(
        TemporalObservation.organization_id == get_org_id(), RawSourceRecord.organization_id == get_org_id(),
        RawSourceRecord.source_id == raw.source_id, RawSourceRecord.external_record_id == raw.external_record_id,
        TemporalEvent.event_type == event_type,
    )
    if occurred_at is not None and not state_observation:
        return query.filter(TemporalEvent.occurred_at == occurred_at).first() is not None
    previous = query.order_by(TemporalEvent.recorded_at.desc(), TemporalEvent.id.desc()).first()
    return previous is not None and previous[1].value == value
