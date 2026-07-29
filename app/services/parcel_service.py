from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models.brand import PermitBrandMatch
from app.models.deal import Deal
from app.models.graph import GraphEntityType, GraphRelationshipType
from app.models.organization_membership import OrganizationMembership
from app.models.parcel import NearbyParcelCandidate, NearbyParcelSearch, ParcelRecord
from app.models.user import User
from app.schemas.deal import DealCreate
from app.schemas.graph import GraphEntityCreate, GraphEvidenceCreate, GraphRelationshipCreate
from app.services.audit_service import log_change
from app.services.brand_intelligence import list_deal_brand_matches
from app.services.deal_service import create_deal_with_defaults
from app.services.graph_service import (
    create_relationship,
    entity_for_record,
    link_entity_to_record,
    resolve_entity,
    upsert_deal_graph_context,
)
from app.services.parcel_proximity import find_nearby_parcels
from app.services.parcel_ranking import rank_parcel_candidate, ranker_version
from app.utils.org_scope import active_query, get_org_id


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_nearby_parcel_search(
    db: Session,
    *,
    deal_id: str,
    anchor_brand_match_id: str,
    radius_miles: float,
    persona: str,
    minimum_land_area_sq_ft: float | None,
    zoning_codes: list[str],
    land_uses: list[str],
    limit: int,
) -> NearbyParcelSearch:
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if deal is None:
        raise LookupError("Deal not found")
    matches = list_deal_brand_matches(db, deal_id, limit=100)
    match = next((row for row in matches if row.id == anchor_brand_match_id), None)
    if match is None:
        raise LookupError("Permit brand match is not connected to this deal")
    permit = match.permit
    if match.review_status != "confirmed":
        if not (
            match.review_status == "candidate"
            and permit.approval_stage == "pre_approval"
        ):
            raise ValueError("A confirmed or pre-approval retailer signal is required")
    if not permit.is_active:
        raise ValueError("The anchor permit is no longer active at its source")
    if permit.latitude is None or permit.longitude is None:
        raise ValueError("The confirmed retailer signal does not have verified coordinates")
    if not -90 <= permit.latitude <= 90 or not -180 <= permit.longitude <= 180:
        raise ValueError("The confirmed retailer signal has invalid coordinates")

    filters = {
        "minimum_land_area_sq_ft": minimum_land_area_sq_ft,
        "zoning_codes": zoning_codes,
        "land_uses": land_uses,
    }
    search = NearbyParcelSearch(
        organization_id=get_org_id(),
        deal_id=deal.id,
        anchor_brand_match_id=match.id,
        anchor_permit_id=permit.id,
        anchor_latitude=permit.latitude,
        anchor_longitude=permit.longitude,
        radius_miles=radius_miles,
        persona=persona,
        filters=filters,
        result_limit=limit,
        as_of=utcnow(),
        ranker_version=ranker_version(persona),
    )
    db.add(search)
    db.flush()

    nearby = find_nearby_parcels(
        db,
        latitude=permit.latitude,
        longitude=permit.longitude,
        radius_miles=radius_miles,
        minimum_land_area_sq_ft=minimum_land_area_sq_ft,
        zoning_codes=zoning_codes,
        land_uses=land_uses,
        limit=limit,
    )
    ranked = []
    for parcel, distance in nearby:
        score = rank_parcel_candidate(
            parcel,
            parcel.facts,
            persona=persona,
            distance_miles=distance,
            radius_miles=radius_miles,
        )
        ranked.append((parcel, distance, score))
    ranked.sort(key=lambda row: (-row[2].score, row[1], row[0].external_parcel_id))

    for rank, (parcel, distance, score) in enumerate(ranked, start=1):
        db.add(NearbyParcelCandidate(
            organization_id=get_org_id(),
            search_id=search.id,
            parcel_id=parcel.id,
            rank=rank,
            distance_miles=round(distance, 4),
            score=score.score,
            score_confidence=score.confidence,
            explanation={
                **score.explanation,
                "anchor_brand_match_id": match.id,
                "anchor_permit_id": permit.id,
            },
            review_status="candidate",
            ranker_version=ranker_version(persona),
        ))
    log_change(
        db,
        "nearby_parcel_search",
        search.id,
        "create",
        organization_id=get_org_id(),
        new_values={
            "deal_id": deal.id,
            "anchor_brand_match_id": match.id,
            "radius_miles": radius_miles,
            "persona": persona,
            "candidate_count": len(ranked),
        },
    )
    db.flush()
    return get_nearby_parcel_search(db, search.id) or search


def list_nearby_parcel_searches(
    db: Session, deal_id: str, *, limit: int = 10
) -> list[NearbyParcelSearch]:
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if deal is None:
        raise LookupError("Deal not found")
    return active_query(db.query(NearbyParcelSearch), NearbyParcelSearch).filter(
        NearbyParcelSearch.deal_id == deal_id
    ).order_by(NearbyParcelSearch.created_at.desc()).limit(limit).all()


def get_nearby_parcel_search(
    db: Session, search_id: str
) -> NearbyParcelSearch | None:
    return active_query(db.query(NearbyParcelSearch), NearbyParcelSearch).options(
        joinedload(NearbyParcelSearch.candidates)
        .joinedload(NearbyParcelCandidate.parcel)
        .joinedload(ParcelRecord.source),
        joinedload(NearbyParcelSearch.candidates)
        .joinedload(NearbyParcelCandidate.parcel)
        .joinedload(ParcelRecord.facts),
    ).filter(NearbyParcelSearch.id == search_id).first()


def get_parcel_detail(db: Session, parcel_id: str) -> ParcelRecord | None:
    return active_query(db.query(ParcelRecord), ParcelRecord).options(
        joinedload(ParcelRecord.source),
        joinedload(ParcelRecord.facts),
        joinedload(ParcelRecord.candidates)
        .joinedload(NearbyParcelCandidate.search)
        .joinedload(NearbyParcelSearch.deal),
    ).filter(ParcelRecord.id == parcel_id).first()


def count_nearby_parcel_searches_for_deal(db: Session, deal_id: str) -> int:
    return active_query(db.query(NearbyParcelSearch), NearbyParcelSearch).filter(
        NearbyParcelSearch.deal_id == deal_id
    ).count()


def summarize_nearby_parcel_searches_for_deal(db: Session, deal_id: str) -> list[dict]:
    rows = active_query(db.query(NearbyParcelSearch), NearbyParcelSearch).options(
        joinedload(NearbyParcelSearch.candidates).joinedload(NearbyParcelCandidate.parcel)
    ).filter(
        NearbyParcelSearch.deal_id == deal_id
    ).order_by(
        NearbyParcelSearch.persona.asc(),
        NearbyParcelSearch.created_at.desc(),
    ).all()
    grouped: dict[str, dict] = {}
    for row in rows:
        bucket = grouped.get(row.persona)
        if bucket is None:
            grouped[row.persona] = {
                "persona": row.persona,
                "search_count": 1,
                "latest_radius_miles": row.radius_miles,
                "latest_created_at": row.created_at,
                "top_parcels": _preview_parcels(row),
            }
            continue
        bucket["search_count"] += 1
        if row.created_at > bucket["latest_created_at"]:
            bucket["latest_radius_miles"] = row.radius_miles
            bucket["latest_created_at"] = row.created_at
            bucket["top_parcels"] = _preview_parcels(row)
    return list(grouped.values())


def summarize_shared_parcels_for_deal(db: Session, deal_id: str) -> list[dict]:
    lenses = summarize_nearby_parcel_searches_for_deal(db, deal_id)
    grouped: dict[str, dict] = {}
    for lens in lenses:
        persona = lens["persona"]
        for parcel in lens["top_parcels"]:
            bucket = grouped.get(parcel["parcel_id"])
            if bucket is None:
                grouped[parcel["parcel_id"]] = {
                    "parcel_id": parcel["parcel_id"],
                    "external_parcel_id": parcel["external_parcel_id"],
                    "address": parcel.get("address"),
                    "city": parcel.get("city"),
                    "state": parcel.get("state"),
                    "best_distance_miles": parcel["distance_miles"],
                    "best_score": parcel["score"],
                    "best_persona": persona,
                    "personas": [persona],
                    "lens_count": 1,
                }
                continue
            if persona not in bucket["personas"]:
                bucket["personas"].append(persona)
                bucket["lens_count"] += 1
            if parcel["score"] > bucket["best_score"]:
                bucket["best_score"] = parcel["score"]
                bucket["best_distance_miles"] = parcel["distance_miles"]
                bucket["best_persona"] = persona
                bucket["external_parcel_id"] = parcel["external_parcel_id"]
                bucket["address"] = parcel.get("address")
                bucket["city"] = parcel.get("city")
                bucket["state"] = parcel.get("state")
    shared = list(grouped.values())
    shared.sort(key=lambda item: (-item["lens_count"], -item["best_score"], item["external_parcel_id"]))
    return shared[:5]


def _preview_parcels(search: NearbyParcelSearch) -> list[dict]:
    previews: list[dict] = []
    for candidate in search.candidates[:3]:
        previews.append({
            "parcel_id": candidate.parcel_id,
            "external_parcel_id": candidate.parcel.external_parcel_id,
            "address": candidate.parcel.address,
            "city": candidate.parcel.city,
            "state": candidate.parcel.state,
            "distance_miles": candidate.distance_miles,
            "score": candidate.score,
            "rank": candidate.rank,
        })
    return previews


def review_nearby_parcel_candidate(
    db: Session, candidate_id: str, review_status: str
) -> NearbyParcelCandidate | None:
    candidate = active_query(
        db.query(NearbyParcelCandidate), NearbyParcelCandidate
    ).options(
        joinedload(NearbyParcelCandidate.parcel).joinedload(ParcelRecord.source),
        joinedload(NearbyParcelCandidate.parcel).joinedload(ParcelRecord.facts),
    ).filter(NearbyParcelCandidate.id == candidate_id).first()
    if candidate is None:
        return None
    old_status = candidate.review_status
    candidate.review_status = review_status
    log_change(
        db,
        "nearby_parcel_candidate",
        candidate.id,
        "review",
        organization_id=get_org_id(),
        old_values={"review_status": old_status},
        new_values={"review_status": review_status},
    )
    db.flush()
    return candidate


def assign_nearby_parcel_candidate(
    db: Session,
    *,
    candidate_id: str,
    assigned_to_user_id: str,
    actor_user_id: str,
) -> NearbyParcelCandidate | None:
    candidate = active_query(
        db.query(NearbyParcelCandidate), NearbyParcelCandidate
    ).options(
        joinedload(NearbyParcelCandidate.parcel).joinedload(ParcelRecord.source),
        joinedload(NearbyParcelCandidate.parcel).joinedload(ParcelRecord.facts),
    ).filter(NearbyParcelCandidate.id == candidate_id).first()
    if candidate is None:
        return None

    assignee_membership = (
        active_query(db.query(OrganizationMembership), OrganizationMembership)
        .join(User, User.id == OrganizationMembership.user_id)
        .filter(
            OrganizationMembership.organization_id == candidate.organization_id,
            OrganizationMembership.user_id == assigned_to_user_id,
        )
        .first()
    )
    if assignee_membership is None:
        raise LookupError("Assignee is not a member of this organization")

    actor = (
        active_query(db.query(User), User)
        .filter(User.id == actor_user_id)
        .first()
    )
    if actor is None:
        raise LookupError("Actor not found")

    old_values = {
        "assigned_to_user_id": candidate.assigned_to_user_id,
        "assigned_to_name": candidate.assigned_to_name,
        "assigned_by_user_id": candidate.assigned_by_user_id,
        "assigned_at": candidate.assigned_at.isoformat() if candidate.assigned_at else None,
    }
    candidate.assigned_to_user_id = assignee_membership.user_id
    candidate.assigned_to_name = assignee_membership.user.full_name
    candidate.assigned_by_user_id = actor.id
    candidate.assigned_at = utcnow()
    log_change(
        db,
        "nearby_parcel_candidate",
        candidate.id,
        "assign",
        organization_id=candidate.organization_id,
        actor_id=actor.id,
        old_values=old_values,
        new_values={
            "assigned_to_user_id": candidate.assigned_to_user_id,
            "assigned_to_name": candidate.assigned_to_name,
            "assigned_by_user_id": candidate.assigned_by_user_id,
            "assigned_at": candidate.assigned_at.isoformat() if candidate.assigned_at else None,
        },
    )
    db.flush()
    return candidate


def promote_nearby_parcel_candidate_to_deal(
    db: Session,
    *,
    candidate_id: str,
    name: str | None = None,
    actor_user_id: str | None = None,
) -> tuple[Deal, bool]:
    candidate = active_query(
        db.query(NearbyParcelCandidate), NearbyParcelCandidate
    ).options(
        joinedload(NearbyParcelCandidate.search).joinedload(NearbyParcelSearch.deal),
        joinedload(NearbyParcelCandidate.parcel).joinedload(ParcelRecord.source),
        joinedload(NearbyParcelCandidate.parcel).joinedload(ParcelRecord.facts),
    ).filter(NearbyParcelCandidate.id == candidate_id).first()
    if candidate is None:
        raise LookupError("Nearby parcel candidate not found")
    if candidate.review_status != "shortlisted":
        raise ValueError("Only shortlisted parcels can be promoted")

    parcel = candidate.parcel
    deal_name = name or parcel.address or parcel.external_parcel_id
    deal = create_deal_with_defaults(db, DealCreate(
        name=deal_name,
        address=parcel.address,
        city=parcel.city,
        state=parcel.state,
        zip_code=parcel.postal_code,
        property_type=parcel.land_use or parcel.zoning_code,
        source="nearby_parcel_promotion",
        notes=(
            f"Promoted from nearby parcel candidate {candidate.id} "
            f"(search {candidate.search_id}, rank {candidate.rank}, score {candidate.score:.1f})"
        ),
    ))
    deal_entity = upsert_deal_graph_context(db, deal)

    parcel_entity = entity_for_record(db, "parcel", parcel.id)
    if parcel_entity is None:
        parcel_entity, _ = resolve_entity(db, GraphEntityCreate(
            entity_type=GraphEntityType.parcel,
            display_name=parcel.external_parcel_id,
            source_system="dealsignal",
            source_id=f"parcel:{parcel.id}",
            address=parcel.address,
            city=parcel.city,
            state=parcel.state,
            zip_code=parcel.postal_code,
            confidence=parcel.candidates[0].score_confidence if parcel.candidates else 0.9,
            attributes={
                "parcel_record_id": parcel.id,
                "promoted_from_candidate_id": candidate.id,
            },
        ))
        link_entity_to_record(db, parcel_entity.id, "parcel", parcel.id, "dealsignal")

    create_relationship(
        db,
        GraphRelationshipCreate(
            source_entity_id=deal_entity.id,
            target_entity_id=parcel_entity.id,
            relationship_type=GraphRelationshipType.located_on,
            confidence=0.95,
            source_system="dealsignal",
            source_id=f"nearby-parcel-promotion:{candidate.id}",
            attributes={
                "candidate_id": candidate.id,
                "search_id": candidate.search_id,
                "parcel_id": parcel.id,
                "deal_id": deal.id,
            },
            evidence=[
                GraphEvidenceCreate(
                    source_system="dealsignal",
                    source_id=candidate.id,
                    evidence_type="nearby_parcel_promotion",
                    excerpt=(
                        f"Promoted from {parcel.address or parcel.external_parcel_id} "
                        f"with score {candidate.score:.1f}"
                    ),
                    confidence=0.95,
                    payload={
                        "candidate_id": candidate.id,
                        "search_id": candidate.search_id,
                        "parcel_id": parcel.id,
                        "rank": candidate.rank,
                        "score": candidate.score,
                        "score_confidence": candidate.score_confidence,
                        "review_status": candidate.review_status,
                    },
                )
            ],
        ),
    )
    log_change(
        db,
        "nearby_parcel_candidate",
        candidate.id,
        "promote_to_opportunity",
        actor_id=actor_user_id,
        organization_id=get_org_id(),
        new_values={
            "deal_id": deal.id,
            "parcel_id": parcel.id,
            "candidate_id": candidate.id,
        },
    )
    db.flush()
    return deal, True


def maybe_create_default_nearby_parcel_search(
    db: Session,
    *,
    deal_id: str,
    anchor_brand_match_id: str,
    persona: str = "developer",
    radius_miles: float = 2.0,
    limit: int = 25,
    minimum_confidence: float = 0.9,
) -> NearbyParcelSearch | None:
    match = active_query(db.query(PermitBrandMatch), PermitBrandMatch).options(
        joinedload(PermitBrandMatch.permit)
    ).filter(PermitBrandMatch.id == anchor_brand_match_id).first()
    if match is None:
        return None
    permit = match.permit
    if match.review_status != "confirmed" and not (
        match.review_status == "candidate"
        and permit.approval_stage == "pre_approval"
    ):
        return None
    if match.confidence < minimum_confidence:
        return None
    if permit.approval_stage not in {"pre_approval", "approved"}:
        return None
    if permit.latitude is None or permit.longitude is None:
        return None
    existing = active_query(db.query(NearbyParcelSearch), NearbyParcelSearch).filter(
        NearbyParcelSearch.deal_id == deal_id,
        NearbyParcelSearch.anchor_brand_match_id == anchor_brand_match_id,
        NearbyParcelSearch.persona == persona,
    ).order_by(NearbyParcelSearch.created_at.desc()).first()
    if existing is not None:
        return existing
    try:
        return create_nearby_parcel_search(
            db,
            deal_id=deal_id,
            anchor_brand_match_id=anchor_brand_match_id,
            radius_miles=radius_miles,
            persona=persona,
            minimum_land_area_sq_ft=None,
            zoning_codes=[],
            land_uses=[],
            limit=limit,
        )
    except (LookupError, ValueError):
        return None


def maybe_create_default_nearby_parcel_searches(
    db: Session,
    *,
    deal_id: str,
    anchor_brand_match_id: str,
    minimum_confidence: float = 0.9,
) -> list[NearbyParcelSearch]:
    searches: list[NearbyParcelSearch] = []
    for persona in ("developer", "broker", "realtor"):
        search = maybe_create_default_nearby_parcel_search(
            db,
            deal_id=deal_id,
            anchor_brand_match_id=anchor_brand_match_id,
            persona=persona,
            radius_miles=2.0,
            limit=25,
            minimum_confidence=minimum_confidence,
        )
        if search is not None:
            searches.append(search)
    return searches
