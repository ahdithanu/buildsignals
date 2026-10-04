"""Read-only, source-scoped parcel candidates; never silently enrich a permit."""
from datetime import datetime, timezone

from sqlalchemy import or_

from app.models.ingestion import IngestionSource, PermitRecord, RawSourceRecord
from app.models.parcel import ParcelRecord
from app.services.graph_service import normalize_address
from app.utils.org_scope import active_query, get_org_id


def _comparison(left, right, normalize):
    if not left or not right or not left.strip() or not right.strip():
        return "missing"
    left, right = normalize(left), normalize(right)
    if not left or not right:
        return "missing"
    return "match" if left == right else "conflict"


def permit_parcel_candidates(db, permit_id: str, parcel_source_id: str) -> dict:
    permit = active_query(db.query(PermitRecord), PermitRecord).filter_by(
        id=permit_id, is_active=True,
    ).first()
    source = active_query(db.query(IngestionSource), IngestionSource).filter_by(
        id=parcel_source_id, record_type="parcel", is_active=True,
    ).first()
    if permit is None or source is None:
        raise LookupError("Permit or parcel source not found")
    result = {
        "permit_id": permit.id, "parcel_source_id": source.id,
        "permit_raw_source_record_id": permit.latest_raw_record_id,
        "permit_parcel_reference": permit.parcel_id,
        "status": "no_match", "method": "source_scoped_exact_reference_v1",
        "candidates": [], "truncated": False,
        "limitations": [
            "Candidate matches require review; no coordinates or graph links were written.",
            "Parcel identifiers are source-specific; a matching ID alone is not identity proof.",
            "A parcel candidate does not establish ownership, availability, or a for-sale listing.",
        ],
    }
    reference = (permit.parcel_id or "").strip()
    if not reference:
        result["status"] = "missing_reference"
        return result
    # Preserve leading zeros and punctuation. Cross-source normalization requires
    # a separately qualified identifier mapping, not a fuzzy ID comparison.
    rows = active_query(db.query(ParcelRecord, RawSourceRecord), ParcelRecord).join(
        RawSourceRecord,
        (RawSourceRecord.id == ParcelRecord.latest_raw_record_id)
        & (RawSourceRecord.organization_id == get_org_id())
        & (RawSourceRecord.source_id == source.id)
        & (RawSourceRecord.record_type == "parcel"),
    ).filter(
        ParcelRecord.source_id == source.id,
        ParcelRecord.is_active.is_(True),
        or_(ParcelRecord.external_parcel_id == reference, ParcelRecord.parcel_group_id == reference),
    ).order_by(ParcelRecord.id).limit(21).all()
    result["truncated"] = len(rows) > 20
    for parcel, raw in rows[:20]:
        state_check = _comparison(permit.state, parcel.state, lambda value: value.strip().upper())
        city_check = _comparison(permit.city, parcel.city, lambda value: value.strip().casefold())
        street_check = _comparison(permit.address, parcel.address, normalize_address)
        checks = (state_check, city_check, street_check)
        address_check = (
            "conflict" if "conflict" in checks else "missing" if "missing" in checks else "match"
        )
        state_matches = state_check == "match"
        address_matches = address_check == "match"
        coords = (
            parcel.latitude is not None and parcel.longitude is not None
            and -90 <= parcel.latitude <= 90 and -180 <= parcel.longitude <= 180
        )
        result["candidates"].append({
            "parcel_id": parcel.id, "external_parcel_id": parcel.external_parcel_id,
            "reference_kind": "external_id" if parcel.external_parcel_id == reference else "parcel_group",
            "state_matches": state_matches, "address_matches": address_matches,
            "state_comparison": state_check, "city_comparison": city_check,
            "street_comparison": street_check, "address_comparison": address_check,
            "identity_assessment": "address_corroborated" if state_matches and address_matches else "needs_review",
            "has_valid_coordinates": coords,
            "raw_source_record_id": raw.id, "captured_at": raw.received_at,
            "source_updated_at": raw.source_updated_at,
            "last_verified_at": parcel.last_verified_at,
        })
    if rows:
        result["status"] = "ambiguous" if len(rows) > 1 else "candidate_requires_review"
    return result


def audit_parcel_references(db, permit_source_id, parcel_source_id, *, limit=50, after_id=None):
    """Bounded diagnostic page, not a population match-rate or coverage claim."""
    if not 1 <= limit <= 100:
        raise ValueError("Audit limit must be between 1 and 100")
    for source_id, record_type in ((permit_source_id, "permit"), (parcel_source_id, "parcel")):
        source = active_query(db.query(IngestionSource), IngestionSource).filter_by(
            id=source_id, record_type=record_type, is_active=True,
        ).first()
        if source is None:
            raise LookupError("Permit or parcel source not found")
    counts = dict.fromkeys((
        "missing_reference", "no_match", "ambiguous", "address_corroborated",
        "conflicting_address", "missing_address_evidence",
    ), 0)
    result = {
        "permit_source_id": permit_source_id, "parcel_source_id": parcel_source_id,
        "measured_at": datetime.now(timezone.utc), "status": "measured_page",
        "counts": counts, "evaluated_permits": 0, "limit": limit,
        "after_id": after_id, "next_after_id": None, "has_more": False,
        "items": [], "coverage_verified": False,
        "limitations": [
            "Counts describe this page only, not the complete source or geographic coverage.",
            "No match means no eligible local candidate, not proof that a parcel does not exist.",
            "Pagination is not a frozen snapshot; underlying records can change between requests.",
            "Corroboration is not analyst acceptance or a calibrated identity probability.",
        ],
    }
    evidence_exists = active_query(db.query(ParcelRecord.id), ParcelRecord).join(
        RawSourceRecord,
        (RawSourceRecord.id == ParcelRecord.latest_raw_record_id)
        & (RawSourceRecord.organization_id == get_org_id())
        & (RawSourceRecord.source_id == parcel_source_id)
        & (RawSourceRecord.record_type == "parcel"),
    ).filter(ParcelRecord.source_id == parcel_source_id, ParcelRecord.is_active.is_(True)).first()
    if evidence_exists is None:
        result["status"] = "parcel_evidence_unavailable"
        return result
    query = active_query(db.query(PermitRecord), PermitRecord).filter_by(
        source_id=permit_source_id, is_active=True,
    )
    if after_id:
        query = query.filter(PermitRecord.id > after_id)
    permits = query.order_by(PermitRecord.id).limit(limit + 1).all()
    result["has_more"] = len(permits) > limit
    for permit in permits[:limit]:
        match = permit_parcel_candidates(db, permit.id, parcel_source_id)
        category = match["status"]
        if category == "candidate_requires_review":
            category = {
                "match": "address_corroborated", "conflict": "conflicting_address",
                "missing": "missing_address_evidence",
            }[match["candidates"][0]["address_comparison"]]
        counts[category] += 1
        result["items"].append({"category": category, "result": match})
    result["evaluated_permits"] = len(result["items"])
    if result["has_more"]:
        result["next_after_id"] = permits[limit - 1].id
    return result
