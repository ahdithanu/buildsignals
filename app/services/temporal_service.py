"""Append-only, tenant-scoped observations; no domain-specific event inference."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.graph import GraphEntity
from app.models.ingestion import IngestionSource, RawSourceRecord
from app.models.temporal import TemporalEvent, TemporalObservation
from app.schemas.temporal import EventCreate, ObservationCreate
from app.utils.org_scope import active_query, get_org_id


def utc(value: datetime) -> datetime:
    # SQLite returns naive values even for timezone-aware columns.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def observation_series_key(
    entity_id: str, source_id: str, external_record_id: str, attribute: str, methodology_version: str,
) -> str:
    return fingerprint([entity_id, source_id, external_record_id, attribute, methodology_version])


def record_observation(db: Session, payload: ObservationCreate) -> tuple[TemporalObservation, bool]:
    if payload.effective_at is not None:
        payload = payload.model_copy(update={"effective_at": utc(payload.effective_at)})
    values = payload.model_dump(mode="json", exclude={"observation_key"})
    content_hash = fingerprint(values)
    existing = active_query(db.query(TemporalObservation), TemporalObservation).filter(
        TemporalObservation.observation_key == payload.observation_key,
    ).first()
    if existing is not None:
        if existing.content_hash != content_hash:
            raise ValueError("Observation key already refers to different evidence or content")
        return existing, False
    entity = active_query(db.query(GraphEntity), GraphEntity).filter(GraphEntity.id == payload.entity_id).first()
    raw = active_query(db.query(RawSourceRecord), RawSourceRecord).filter(
        RawSourceRecord.id == payload.raw_source_record_id,
    ).first()
    if entity is None or raw is None:
        raise LookupError("Entity or source evidence not found")
    source = active_query(db.query(IngestionSource), IngestionSource).filter(
        IngestionSource.id == raw.source_id,
    ).first()
    if source is None:
        raise LookupError("Source evidence not found")

    row = TemporalObservation(
        **payload.model_dump(),
        organization_id=get_org_id(),
        source_id=source.id,
        source_system=source.key,
        source_type=raw.record_type,
        source_updated_at=utc(raw.source_updated_at) if raw.source_updated_at else None,
        first_observed_at=utc(raw.received_at),
        recorded_at=_utcnow(),
        content_hash=content_hash,
        series_key=observation_series_key(
            entity.id, source.id, raw.external_record_id, payload.attribute, payload.methodology_version,
        ),
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        existing = active_query(db.query(TemporalObservation), TemporalObservation).filter(
            TemporalObservation.observation_key == payload.observation_key,
        ).first()
        if existing is None:
            raise
        if existing.content_hash != content_hash:
            raise ValueError("Observation key already refers to different evidence or content") from None
        return existing, False
    return row, True


def record_event(db: Session, payload: EventCreate) -> tuple[TemporalEvent, bool]:
    if payload.occurred_at is not None:
        payload = payload.model_copy(update={"occurred_at": utc(payload.occurred_at)})
    observation = active_query(db.query(TemporalObservation), TemporalObservation).filter(
        TemporalObservation.id == payload.observation_id,
    ).first()
    if observation is None:
        raise LookupError("Observation not found")
    query = active_query(db.query(TemporalEvent), TemporalEvent).filter(
        TemporalEvent.observation_id == payload.observation_id,
        TemporalEvent.event_type == payload.event_type,
    )
    existing = query.first()
    if existing is not None:
        if (utc(existing.occurred_at) if existing.occurred_at else None) != payload.occurred_at:
            raise ValueError("Event already exists with a different occurrence time")
        return existing, False
    row = TemporalEvent(**payload.model_dump(), organization_id=get_org_id(), recorded_at=_utcnow())
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        existing = query.first()
        if existing is None:
            raise
        if (utc(existing.occurred_at) if existing.occurred_at else None) != payload.occurred_at:
            raise ValueError("Event already exists with a different occurrence time") from None
        return existing, False
    return row, True


def observations_as_of(
    db: Session, *, as_of: datetime, entity_id: str | None = None,
    attribute: str | None = None, series_key: str | None = None,
    observation_id: str | None = None,
    limit: int = 100, offset: int = 0,
) -> list[TemporalObservation]:
    if as_of.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    as_of = utc(as_of)
    if not 1 <= limit <= 500 or not 0 <= offset <= 10000:
        raise ValueError("Query bounds exceeded")
    query = active_query(db.query(TemporalObservation), TemporalObservation).filter(
        TemporalObservation.first_observed_at <= as_of,
        TemporalObservation.recorded_at <= as_of,
    )
    if entity_id is not None:
        query = query.filter(TemporalObservation.entity_id == entity_id)
    if observation_id is not None:
        query = query.filter(TemporalObservation.id == observation_id)
    if attribute is not None:
        query = query.filter(TemporalObservation.attribute == attribute)
    if series_key is not None:
        query = query.filter(TemporalObservation.series_key == series_key)
    return query.order_by(
        TemporalObservation.recorded_at.desc(), TemporalObservation.id.desc(),
    ).offset(offset).limit(limit).all()


def events_as_of(
    db: Session, *, as_of: datetime, entity_id: str | None = None,
    event_type: str | None = None, limit: int = 100, offset: int = 0,
) -> list[TemporalEvent]:
    if as_of.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    as_of = utc(as_of)
    if not 1 <= limit <= 500 or not 0 <= offset <= 10000:
        raise ValueError("Query bounds exceeded")
    query = active_query(db.query(TemporalEvent), TemporalEvent).join(
        TemporalObservation, TemporalObservation.id == TemporalEvent.observation_id,
    ).filter(
        TemporalObservation.organization_id == get_org_id(),
        TemporalObservation.first_observed_at <= as_of,
        TemporalObservation.recorded_at <= as_of,
        TemporalEvent.recorded_at <= as_of,
    )
    if entity_id is not None:
        query = query.filter(TemporalObservation.entity_id == entity_id)
    if event_type is not None:
        query = query.filter(TemporalEvent.event_type == event_type)
    return query.order_by(TemporalEvent.recorded_at.desc(), TemporalEvent.id.desc()).offset(offset).limit(limit).all()


def numeric_change(db: Session, *, series_key: str, as_of: datetime) -> dict:
    rows = observations_as_of(db, series_key=series_key, as_of=as_of, limit=2)
    result = {
        "series_key": series_key, "as_of": as_of, "methodology_version": "numeric-change-v1",
        "status": "insufficient_history", "current_observation_id": rows[0].id if rows else None,
        "previous_observation_id": rows[1].id if len(rows) == 2 else None,
        "current_value": None, "previous_value": None, "absolute_change": None,
        "percent_change": None, "direction": None,
    }
    if len(rows) < 2:
        return result
    current, previous = rows
    values = [current.value, previous.value]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values):
        result["status"] = "non_numeric"
        return result
    if current.unit != previous.unit:
        result["status"] = "incompatible_units"
        return result
    try:
        delta = current.value - previous.value
        percent = 100 * delta / abs(previous.value) if previous.value != 0 else None
        finite = all(math.isfinite(v) for v in [*values, delta]) and (percent is None or math.isfinite(percent))
    except OverflowError:
        finite = False
    if not finite:
        result["status"] = "numeric_overflow"
        return result
    result.update(
        status="calculated" if percent is not None else "zero_baseline",
        current_value=current.value, previous_value=previous.value,
        absolute_change=delta, percent_change=percent,
        direction="up" if delta > 0 else "down" if delta < 0 else "unchanged",
    )
    return result
