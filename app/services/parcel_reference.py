"""Read-only, source-scoped parcel candidates; never silently enrich a permit."""
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
