from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from sqlalchemy import String, and_, case, cast, func
from sqlalchemy.orm import Session

from app.models.ingestion import IngestionSource, RawSourceRecord
from app.models.parcel import ParcelFact, ParcelRecord
from app.schemas.parcel_use_context import ParcelUseContextResponse, ParcelUseEvidence
from app.utils.org_scope import get_org_id

EVIDENCE_LIMIT = 50
MAX_FACT_JSON_CHARS = 16_384
BASE_GAPS = (
    "zoning_assignment_unverified",
    "use_rules_missing",
    "overlays_unverified",
    "site_constraints_unverified",
)


def _label(value: object) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 255:
        return None
    return value.strip() or None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _recorded_date(value: str | None) -> datetime:
    if not isinstance(value, str) or len(value) <= 10:
        raise ValueError("Missing or malformed evidence date")
    return _utc(datetime.fromisoformat(value))


def _evidence(row, source_key: str | None, as_of: datetime) -> ParcelUseEvidence | None:
    if (
        row.raw_id is None
        or source_key is None
        or row.source_system != source_key
        or row.valid_to is not None
        or not isinstance(row.value, str)
        or len(row.value) > MAX_FACT_JSON_CHARS
    ):
        return None
    try:
        value = json.loads(row.value)
        key = "zoning_code" if row.fact_type == "zoning" else "land_use"
        label = _label(value.get(key)) if isinstance(value, dict) else None
        confidence = float(row.confidence)
        observed_at = _recorded_date(row.observed_at)
        verified_at = _recorded_date(row.last_verified_at)
        valid_from = _recorded_date(row.valid_from)
        if (
            label is None
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
            or any(date > as_of for date in (observed_at, verified_at, valid_from))
        ):
            return None
        return ParcelUseEvidence(
            fact_id=row.id,
            kind=row.fact_type,
            recorded_value=label,
            source_url=row.source_url,
            confidence=confidence,
            observed_at=observed_at,
            last_verified_at=verified_at,
        )
    except (TypeError, ValueError, OverflowError, RecursionError):
        return None


def get_parcel_use_context(
    db: Session, parcel_id: str, *, as_of: datetime | None = None,
) -> ParcelUseContextResponse | None:
    """Return bounded reported labels, never zoning eligibility or permitted uses.

    ``as_of`` is a server-side clock seam for deterministic tests, not a client
    historical-query parameter. Only current rows are inspected; evidence must
    have no end date. Inconsistent current-but-ended rows fail closed.
    """
    now = _utc(as_of if as_of is not None else datetime.now(timezone.utc))
    org_id = get_org_id()
    # Column projections bypass cached ORM objects and never load raw/config/history.
    with db.no_autoflush:
        parcel = db.query(
            ParcelRecord.id,
            ParcelRecord.source_id,
            ParcelRecord.external_parcel_id,
            ParcelRecord.jurisdiction,
            ParcelRecord.state,
            ParcelRecord.zoning_code,
            ParcelRecord.land_use,
            IngestionSource.key.label("source_key"),
        ).outerjoin(
            IngestionSource,
            and_(
                IngestionSource.id == ParcelRecord.source_id,
                IngestionSource.organization_id == org_id,
            ),
        ).filter(
            ParcelRecord.id == parcel_id,
            ParcelRecord.organization_id == org_id,
            ParcelRecord.is_active.is_(True),
            ParcelRecord.retired_at.is_(None),
        ).first()
        if parcel is None:
            return None

        # Cast untrusted typed columns so corrupt SQLite rows cannot fail during
        # driver decoding before validation. PostgreSQL casts retain the same data.
        fact_json = cast(ParcelFact.value, String)
        rows = db.query(
            ParcelFact.id,
            ParcelFact.fact_type,
            case(
                (func.length(fact_json) <= MAX_FACT_JSON_CHARS, fact_json), else_=None,
            ).label("value"),
            ParcelFact.source_system,
            ParcelFact.source_url,
            cast(ParcelFact.confidence, String).label("confidence"),
            cast(ParcelFact.observed_at, String).label("observed_at"),
            cast(ParcelFact.last_verified_at, String).label("last_verified_at"),
            cast(ParcelFact.valid_from, String).label("valid_from"),
            cast(ParcelFact.valid_to, String).label("valid_to"),
            RawSourceRecord.id.label("raw_id"),
        ).outerjoin(
            RawSourceRecord,
            and_(
                RawSourceRecord.id == ParcelFact.raw_source_record_id,
                RawSourceRecord.organization_id == org_id,
                RawSourceRecord.source_id == parcel.source_id,
                RawSourceRecord.record_type == "parcel",
                RawSourceRecord.external_record_id == parcel.external_parcel_id,
            ),
        ).filter(
            ParcelFact.organization_id == org_id,
            ParcelFact.parcel_id == parcel.id,
            ParcelFact.fact_type.in_(("zoning", "land_use")),
            ParcelFact.is_current.is_(True),
        ).order_by(ParcelFact.id).limit(EVIDENCE_LIMIT + 1).all()

    recorded_zoning = _label(parcel.zoning_code)
    recorded_land_use = _label(parcel.land_use)
    incomplete = parcel.source_key is None or any(
        value is not None and _label(value) is None
        for value in (parcel.zoning_code, parcel.land_use)
    )
    evidence = []
    for row in rows[:EVIDENCE_LIMIT]:
        item = _evidence(row, parcel.source_key, now)
        if item is None:
            incomplete = True
        else:
            evidence.append(item)

    zoning_codes = sorted({item.recorded_value for item in evidence if item.kind == "zoning"})
    land_uses = {item.recorded_value for item in evidence if item.kind == "land_use"}
    if recorded_land_use is not None:
        land_uses.add(recorded_land_use)
    compared_codes = set(zoning_codes)
    if recorded_zoning is not None:
        compared_codes.add(recorded_zoning)
    conflicting = len(compared_codes) > 1
    overflow = len(rows) > EVIDENCE_LIMIT
    gaps = list(BASE_GAPS)
    if not zoning_codes:
        gaps.append("zoning_evidence_missing")
    if conflicting:
        gaps.append("zoning_evidence_conflicting")
    if incomplete:
        gaps.append("source_evidence_incomplete")
    if overflow:
        gaps.append("evidence_limit_reached")

    if incomplete or overflow:
        status = "incomplete"
    elif conflicting:
        status = "conflicting"
    elif zoning_codes:
        status = "reported"
    elif recorded_zoning is not None or land_uses or evidence:
        status = "incomplete"
    else:
        status = "missing"

    return ParcelUseContextResponse(
        parcel_id=parcel.id,
        as_of=now,
        jurisdiction=parcel.jurisdiction,
        state=parcel.state,
        status=status,
        recorded_zoning_code=recorded_zoning,
        reported_zoning_codes=zoning_codes,
        recorded_land_uses=sorted(land_uses),
        evidence=evidence,
        gaps=gaps,
    )
