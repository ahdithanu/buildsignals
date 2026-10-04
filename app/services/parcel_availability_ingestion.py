"""Manual intake for source-backed parcel availability evidence."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.ingestion import IngestionRun, IngestionSource, RawSourceRecord
from app.models.parcel import ParcelFact, ParcelRecord
from app.services.audit_service import log_change
from app.services.parcel_availability import AVAILABILITY_FACT_TYPES, VERIFIED_AVAILABILITY_STATUSES
from app.utils.org_scope import active_query, get_org_id

MANUAL_AVAILABILITY_SOURCE_KEY = "manual_availability_evidence"
ALLOWED_EVIDENCE_TYPES = {"listing", "broker", "owner", "auction"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _content_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _manual_source(db: Session) -> IngestionSource:
    source = active_query(db.query(IngestionSource), IngestionSource).filter(
        IngestionSource.key == MANUAL_AVAILABILITY_SOURCE_KEY,
    ).first()
    if source is not None:
        return source
    source = IngestionSource(
        organization_id=get_org_id(),
        key=MANUAL_AVAILABILITY_SOURCE_KEY,
        name="Manual availability evidence",
        adapter="manual",
        record_type="parcel_availability",
        jurisdiction="customer_supplied",
        settings={
            "schedule_mode": "manual",
            "evidence_contract": "availability_fact_requires_source_url_or_excerpt",
        },
        is_active=True,
    )
    db.add(source)
    db.flush()
    return source


def create_availability_evidence(
    db: Session,
    *,
    parcel_id: str,
    status: str,
    evidence_type: str,
    source_url: str | None,
    excerpt: str | None,
    confidence: float,
    observed_at: datetime | None,
    asking_price: float | None,
    contact_name: str | None,
    contact_company: str | None,
    actor_user_id: str | None,
) -> ParcelFact:
    normalized_status = status.strip().lower()
    normalized_evidence_type = evidence_type.strip().lower()
    if normalized_status not in VERIFIED_AVAILABILITY_STATUSES:
        raise ValueError("Availability status must be an explicit available/listed status")
    if normalized_evidence_type not in ALLOWED_EVIDENCE_TYPES:
        raise ValueError("Availability evidence type must be listing, broker, owner, or auction")
    if not 0.7 <= confidence <= 1:
        raise ValueError("Availability confidence must be between 0.7 and 1.0")
    if not (source_url and source_url.strip()) and not (excerpt and excerpt.strip()):
        raise ValueError("Availability evidence requires a source URL or excerpt")

    parcel = active_query(db.query(ParcelRecord), ParcelRecord).filter(ParcelRecord.id == parcel_id).first()
    if parcel is None:
        raise LookupError("Parcel not found")

    now = _utcnow()
    source = _manual_source(db)
    payload = {
        "parcel_id": parcel.id,
        "external_parcel_id": parcel.external_parcel_id,
        "status": normalized_status,
        "evidence_type": normalized_evidence_type,
        "source_url": source_url,
        "excerpt": excerpt,
        "confidence": confidence,
        "observed_at": (observed_at or now).isoformat(),
        "asking_price": asking_price,
        "contact_name": contact_name,
        "contact_company": contact_company,
    }
    run = IngestionRun(
        organization_id=get_org_id(),
        source_id=source.id,
        status="completed",
        trigger="manual",
        completed_at=now,
        records_seen=1,
        records_inserted=1,
        parameters={"intake": "parcel_availability_evidence"},
    )
    db.add(run)
    db.flush()
    raw = RawSourceRecord(
        organization_id=get_org_id(),
        source_id=source.id,
        run_id=run.id,
        external_record_id=f"availability:{parcel.id}:{uuid4()}",
        record_type="parcel_availability",
        content_hash=_content_hash(payload),
        payload=payload,
        source_updated_at=observed_at,
        received_at=now,
    )
    db.add(raw)
    db.flush()

    current = active_query(db.query(ParcelFact), ParcelFact).filter(
        ParcelFact.parcel_id == parcel.id,
        ParcelFact.fact_type.in_(AVAILABILITY_FACT_TYPES),
        ParcelFact.is_current.is_(True),
    ).all()
    for fact in current:
        fact.is_current = False
        fact.valid_to = now

    value = {
        "status": normalized_status,
        "evidence_type": normalized_evidence_type,
        "asking_price": asking_price,
        "contact_name": contact_name,
        "contact_company": contact_company,
    }
    fact = ParcelFact(
        organization_id=get_org_id(),
        parcel_id=parcel.id,
        raw_source_record_id=raw.id,
        fact_type="availability",
        value={key: val for key, val in value.items() if val is not None},
        source_system=source.key,
        source_url=source_url,
        field_path="manual_availability_evidence",
        excerpt=excerpt,
        confidence=confidence,
        observed_at=observed_at or now,
        last_verified_at=now,
        valid_from=now,
        is_current=True,
    )
    db.add(fact)
    log_change(
        db,
        "parcel",
        parcel.id,
        "availability_evidence_created",
        actor_id=actor_user_id,
        new_values={
            "fact_type": fact.fact_type,
            "status": normalized_status,
            "evidence_type": normalized_evidence_type,
            "source_url": source_url,
            "confidence": confidence,
        },
    )
    db.flush()
    return fact
