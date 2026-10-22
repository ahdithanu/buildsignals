"""Read-only, source-scoped parcel candidates; never silently enrich a permit."""
from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import aliased

from app.models.graph import (
    GraphEntityLink,
    GraphEntityType,
    GraphRelationship,
    GraphRelationshipType,
)
from app.models.ingestion import IngestionSource, PermitRecord, RawSourceRecord
from app.models.parcel import ParcelRecord
from app.services.graph_service import entity_for_record, normalize_address
from app.utils.org_scope import active_query, get_org_id

REVIEW_SYSTEM = "reviewed_parcel_reference"


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


def _accepted_review_pairs(db, permit_ids: list[str]) -> set[tuple[str, str]]:
    """Return accepted permit/parcel record pairs without changing graph state."""
    if not permit_ids:
        return set()
    permit_link = aliased(GraphEntityLink)
    parcel_link = aliased(GraphEntityLink)
    rows = db.query(permit_link.record_id, parcel_link.record_id).select_from(GraphRelationship).join(
        permit_link, permit_link.entity_id == GraphRelationship.source_entity_id,
    ).join(
        parcel_link, parcel_link.entity_id == GraphRelationship.target_entity_id,
    ).filter(
        GraphRelationship.organization_id == get_org_id(),
        GraphRelationship.relationship_type == GraphRelationshipType.permit_for,
        GraphRelationship.source_system == REVIEW_SYSTEM,
        GraphRelationship.is_current.is_(True),
        permit_link.record_type == "permit",
        permit_link.record_id.in_(permit_ids),
        parcel_link.record_type == "parcel",
        permit_link.organization_id == get_org_id(),
        parcel_link.organization_id == get_org_id(),
    ).all()
    return {(permit_id, parcel_id) for permit_id, parcel_id in rows}


def _acceptance_prerequisites_hold(db, item: dict) -> bool:
    """Mirror acceptance's evidence/entity gates without mutating state."""
    result = item["result"]
    if len(result["candidates"]) != 1:
        return False
    permit_id = result["permit_id"]
    candidate = result["candidates"][0]
    permit = active_query(db.query(PermitRecord), PermitRecord).filter_by(
        id=permit_id, is_active=True,
    ).first()
    parcel = active_query(db.query(ParcelRecord), ParcelRecord).filter_by(
        id=candidate["parcel_id"], source_id=result["parcel_source_id"], is_active=True,
    ).first()
    if permit is None or parcel is None:
        return False
    permit_entity = entity_for_record(db, "permit", permit.id)
    parcel_entity = entity_for_record(db, "parcel", parcel.id)
    if (permit_entity is None or parcel_entity is None
            or permit_entity.entity_type != GraphEntityType.permit
            or parcel_entity.entity_type != GraphEntityType.parcel):
        return False
    permit_raw = active_query(db.query(RawSourceRecord), RawSourceRecord).filter_by(
        id=result["permit_raw_source_record_id"], source_id=permit.source_id, record_type="permit",
    ).first()
    parcel_raw = active_query(db.query(RawSourceRecord), RawSourceRecord).filter_by(
        id=candidate["raw_source_record_id"], source_id=parcel.source_id, record_type="parcel",
    ).first()
    return (
        permit_raw is not None
        and parcel_raw is not None
        and permit.latest_raw_record_id == permit_raw.id
        and parcel.latest_raw_record_id == parcel_raw.id
    )


def _reconciliation_state(db, item: dict, accepted: set[tuple[str, str]]) -> str:
    result = item["result"]
    permit_id = result["permit_id"]
    candidate_ids = {candidate["parcel_id"] for candidate in result["candidates"]}
    accepted_for_permit = {(p, parcel) for p, parcel in accepted if p == permit_id}
    if len(candidate_ids) == 1 and (permit_id, next(iter(candidate_ids))) in accepted:
        return "accepted"
    if accepted_for_permit:
        return "accepted_other"
    if item["category"] == "address_corroborated" and _acceptance_prerequisites_hold(db, item):
        return "eligible"
    if item["category"] in {"missing_reference", "no_match"}:
        return "unreviewed"
    return "needs_review"


def reconcile_parcel_references(
    db, permit_source_id: str, parcel_source_id: str, *, limit: int = 50,
    after_id: str | None = None, review_state: str = "all",
):
    """Build a bounded review queue; never accepts or writes parcel references."""
    if review_state not in {"all", "eligible", "needs_review", "accepted"}:
        raise ValueError("Invalid parcel reconciliation review state")
    cursor = after_id
    next_cursor = after_id
    first_page = None
    items = []
    while len(items) < limit:
        audit = audit_parcel_references(
            db, permit_source_id, parcel_source_id, limit=limit, after_id=cursor,
        )
        first_page = first_page or audit
        next_cursor = audit["next_after_id"]
        permit_ids = [item["result"]["permit_id"] for item in audit["items"]]
        accepted = _accepted_review_pairs(db, permit_ids)
        for item in audit["items"]:
            state = _reconciliation_state(db, item, accepted)
            matches_filter = (
                review_state == "all"
                or state == review_state
                or review_state == "needs_review" and state in {"unreviewed", "needs_review", "accepted_other"}
                or review_state == "accepted" and state in {"accepted", "accepted_other"}
            )
            if matches_filter:
                items.append({
                    **item,
                    "review_state": state,
                    "eligible_for_acceptance": state == "eligible",
                })
                if len(items) >= limit:
                    break
        if review_state == "all" or not audit["has_more"] or len(items) >= limit:
            break
        cursor = audit["next_after_id"]
        if not cursor:
            break
    assert first_page is not None
    return {
        **first_page,
        "items": items,
        "has_more": bool(first_page["has_more"] and len(items) >= limit),
        "next_after_id": next_cursor if first_page["has_more"] and len(items) >= limit else None,
    }
