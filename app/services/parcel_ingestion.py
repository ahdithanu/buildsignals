from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.ingestion import IngestionSource, RawSourceRecord
from app.models.parcel import ParcelFact, ParcelRecord
from app.services.graph_service import normalize_address
from app.utils.org_scope import active_query, get_org_id

PARCEL_FIELDS = {
    "parcel_group_id", "jurisdiction", "county", "state", "address", "city", "postal_code",
    "latitude", "longitude", "land_area_sq_ft", "improvement_area_sq_ft",
    "land_value", "improvement_value", "total_assessed_value", "land_use",
    "zoning_code",
}


@dataclass(frozen=True)
class ParcelFactInput:
    fact_type: str
    value: dict[str, Any]
    source_url: str | None = None
    field_path: str | None = None
    excerpt: str | None = None
    confidence: float = 1.0
    observed_at: datetime | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def upsert_parcel_snapshot(
    db: Session,
    *,
    source: IngestionSource,
    raw_record: RawSourceRecord,
    external_parcel_id: str,
    values: dict[str, Any],
    facts: list[ParcelFactInput],
    verified_at: datetime | None = None,
    normalization_hash: str = "",
    snapshot_id: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> tuple[ParcelRecord, str]:
    if not external_parcel_id.strip():
        raise ValueError("external_parcel_id is required")
    if source.organization_id != get_org_id() or raw_record.organization_id != get_org_id():
        raise ValueError("Parcel source evidence belongs to another organization")
    if raw_record.source_id != source.id:
        raise ValueError("Parcel raw evidence must belong to the parcel source")
    latitude = values.get("latitude")
    longitude = values.get("longitude")
    if (latitude is None) != (longitude is None):
        raise ValueError("Parcel centroid latitude and longitude must be supplied together")
    if latitude is not None and longitude is not None:
        if not -90 <= float(latitude) <= 90 or not -180 <= float(longitude) <= 180:
            raise ValueError("Parcel centroid coordinates are invalid")
    now = verified_at or utcnow()
    parcel = active_query(db.query(ParcelRecord), ParcelRecord).filter(
        ParcelRecord.source_id == source.id,
        ParcelRecord.external_parcel_id == external_parcel_id,
    ).first()
    filtered = {key: value for key, value in values.items() if key in PARCEL_FIELDS}
    filtered["normalized_address"] = normalize_address(
        filtered.get("address"), filtered.get("city"), filtered.get("state"),
        filtered.get("postal_code"),
    )
    if parcel is None:
        parcel = ParcelRecord(
            organization_id=get_org_id(),
            source_id=source.id,
            latest_raw_record_id=raw_record.id,
            external_parcel_id=external_parcel_id,
            normalization_hash=normalization_hash,
            last_seen_snapshot_id=snapshot_id,
            attributes=attributes,
            first_seen_at=now,
            last_seen_at=now,
            last_verified_at=now,
            is_active=True,
            **filtered,
        )
        db.add(parcel)
        action = "created"
    else:
        for field in PARCEL_FIELDS | {"normalized_address"}:
            setattr(parcel, field, filtered.get(field))
        parcel.latest_raw_record_id = raw_record.id
        parcel.normalization_hash = normalization_hash
        parcel.last_seen_snapshot_id = snapshot_id
        parcel.attributes = attributes
        parcel.last_seen_at = now
        parcel.last_verified_at = now
        parcel.is_active = True
        parcel.retired_at = None
        action = "updated"
    db.flush()

    for incoming in facts:
        if not incoming.fact_type.strip():
            raise ValueError("Parcel fact_type is required")
        if not 0 <= incoming.confidence <= 1:
            raise ValueError("Parcel fact confidence must be between 0 and 1")
        current = active_query(db.query(ParcelFact), ParcelFact).filter(
            ParcelFact.parcel_id == parcel.id,
            ParcelFact.fact_type == incoming.fact_type,
            ParcelFact.is_current.is_(True),
        ).all()
        unchanged = next(
            (
                fact for fact in current
                if fact.raw_source_record_id == raw_record.id
                and fact.value == incoming.value
            ),
            None,
        )
        if unchanged is not None:
            unchanged.last_verified_at = now
            continue
        for fact in current:
            fact.is_current = False
            fact.valid_to = now
        observed_at = incoming.observed_at or raw_record.received_at or now
        db.add(ParcelFact(
            organization_id=get_org_id(),
            parcel_id=parcel.id,
            raw_source_record_id=raw_record.id,
            fact_type=incoming.fact_type,
            value=incoming.value,
            source_system=source.key,
            source_url=incoming.source_url or source.base_url,
            field_path=incoming.field_path,
            excerpt=incoming.excerpt,
            confidence=incoming.confidence,
            observed_at=observed_at,
            last_verified_at=now,
            valid_from=now,
            is_current=True,
        ))
    db.flush()
    return parcel, action
