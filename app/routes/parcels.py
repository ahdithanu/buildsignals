from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.graph import GraphEntity, GraphEntityLink
from app.models.organization_membership import MemberRole
from app.schemas.acquisition import (
    ParcelAcquisitionActivityCreate,
    ParcelAcquisitionActivityResponse,
    ParcelAcquisitionCaseResponse,
    ParcelAcquisitionCaseUpdate,
)
from app.schemas.graph import (
    GraphEntityResponse,
    GraphRelatedEntityResponse,
    GraphRelationshipResponse,
)
from app.schemas.parcel import (
    AcquisitionRadarResponse,
    NearbyParcelCandidateAssignment,
    NearbyParcelCandidateResponse,
    NearbyParcelCandidateReview,
    NearbyParcelOpportunityCreate,
    NearbyParcelOpportunityResponse,
    NearbyParcelSearchCreate,
    NearbyParcelSearchResponse,
    NearbyParcelSearchSummary,
    ParcelDetailResponse,
    ParcelLineageEventResponse,
    ParcelSearchHitResponse,
)
from app.services.acquisition_service import (
    get_acquisition_case,
    record_acquisition_activity,
    update_acquisition_case,
)
from app.services.deal_service import deal_to_detail_response
from app.services.graph_service import relationships_for_entity
from app.services.map_readiness import map_readiness
from app.services.map_signals import list_map_signals
from app.services.parcel_export import ParcelExportDenied, export_nearby_parcel_search
from app.services.parcel_lineage import get_lineage_event, lineage_events_for_parcel
from app.services.parcel_service import (
    assign_nearby_parcel_candidate,
    create_nearby_parcel_search,
    get_nearby_parcel_search,
    get_parcel_detail,
    list_acquisition_radar,
    list_nearby_parcel_searches,
    promote_nearby_parcel_candidate_to_deal,
    review_nearby_parcel_candidate,
)
from app.utils.auth_deps import get_current_user, require_role
from app.utils.org_scope import active_query

router = APIRouter(tags=["nearby parcels"])


@router.get("/acquisition-map/signals", dependencies=[Depends(get_current_user)])
def get_map_signals(
    response: Response,
    limit: int = Query(default=100, ge=1, le=100),
    state: str | None = Query(default=None, pattern="^[A-Za-z]{2}$"),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return list_map_signals(db, limit=limit, state=state)


@router.get("/acquisition-map/readiness", dependencies=[Depends(get_current_user)])
def get_map_readiness(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return map_readiness(db)


def _lineage_response(event) -> dict:
    return {
        "id": event.id,
        "source_key": event.source.key,
        "external_event_id": event.external_event_id,
        "event_type": event.event_type,
        "confidence": event.confidence,
        "observed_at": event.observed_at,
        "last_verified_at": event.last_verified_at,
        "attributes": event.attributes,
        "participants": event.participants,
        "evidence": event.evidence,
    }


@router.get(
    "/parcel-lineage-events/{event_id}",
    response_model=ParcelLineageEventResponse,
)
def get_parcel_lineage_event(event_id: str, db: Session = Depends(get_db)):
    event = get_lineage_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Parcel lineage event not found")
    return _lineage_response(event)


@router.get(
    "/parcel-acquisition-cases/{case_id}",
    response_model=ParcelAcquisitionCaseResponse,
)
def get_case(case_id: str, db: Session = Depends(get_db)):
    case = get_acquisition_case(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Parcel acquisition case not found")
    return case


@router.patch(
    "/parcel-acquisition-cases/{case_id}",
    response_model=ParcelAcquisitionCaseResponse,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def patch_case(
    case_id: str,
    payload: ParcelAcquisitionCaseUpdate,
    principal: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        case = update_acquisition_case(
            db,
            case_id=case_id,
            actor_user_id=principal["user_id"],
            status=payload.status,
            assigned_to_user_id=payload.assigned_to_user_id,
            assignment_supplied="assigned_to_user_id" in payload.model_fields_set,
            follow_up_at=payload.follow_up_at,
        )
        if case is None:
            raise HTTPException(status_code=404, detail="Parcel acquisition case not found")
        db.commit()
        return get_acquisition_case(db, case.id)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/parcel-acquisition-cases/{case_id}/activities",
    response_model=ParcelAcquisitionActivityResponse,
    status_code=201,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def create_case_activity(
    case_id: str,
    payload: ParcelAcquisitionActivityCreate,
    principal: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        activity = record_acquisition_activity(
            db,
            case_id=case_id,
            actor_user_id=principal["user_id"],
            activity_type=payload.activity_type,
            notes=payload.notes,
            occurred_at=payload.occurred_at,
            follow_up_at=payload.follow_up_at,
        )
        db.commit()
        db.refresh(activity)
        return activity
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/acquisition-radar", response_model=AcquisitionRadarResponse)
def get_acquisition_radar(
    q: str | None = Query(default=None, min_length=1, max_length=200),
    state: str | None = Query(default=None, min_length=2, max_length=2),
    persona: str | None = Query(
        default=None, pattern="^(developer|investor|broker|realtor)$"
    ),
    review_status: str | None = Query(
        default=None,
        pattern="^(candidate|shortlisted|contacted|dismissed|promoted)$",
    ),
    assignment: str | None = Query(default=None, pattern="^(assigned|unassigned)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return list_acquisition_radar(
        db,
        query=q,
        state=state,
        persona=persona,
        review_status=review_status,
        assignment=assignment,
        limit=limit,
        offset=offset,
    )


@router.get("/parcels/{parcel_id}", response_model=ParcelDetailResponse)
def get_parcel(parcel_id: str, db: Session = Depends(get_db)):
    parcel = get_parcel_detail(db, parcel_id)
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcel not found")

    search_hits = []
    seen_searches = set()
    for candidate in sorted(parcel.candidates, key=lambda item: (item.search.created_at, item.rank), reverse=True):
        search = candidate.search
        if search.id not in seen_searches:
            seen_searches.add(search.id)
        search_hits.append(
            ParcelSearchHitResponse(
                search_id=search.id,
                deal_id=search.deal_id,
                deal_name=search.deal.name if search.deal else None,
                persona=search.persona,
                radius_miles=search.radius_miles,
                created_at=search.created_at,
                rank=candidate.rank,
                distance_miles=candidate.distance_miles,
                score=candidate.score,
                score_confidence=candidate.score_confidence,
                review_status=candidate.review_status,
            )
        )
        if len(search_hits) >= 10:
            break

    graph_entity = active_query(db.query(GraphEntity), GraphEntity).join(GraphEntityLink).filter(
        GraphEntityLink.record_type == "parcel",
        GraphEntityLink.record_id == parcel.id,
    ).first()
    return ParcelDetailResponse(
        parcel=parcel,
        facts=list(parcel.facts),
        search_count=len(seen_searches),
        search_hits=search_hits,
        graph_entity=GraphEntityResponse.model_validate(graph_entity).model_dump() if graph_entity else None,
        graph_related=[
            GraphRelatedEntityResponse(
                entity=GraphEntityResponse.model_validate(entity),
                relationship=GraphRelationshipResponse.model_validate(relationship),
                direction=direction,
            ).model_dump()
            for relationship, entity, direction in relationships_for_entity(db, graph_entity.id)
        ] if graph_entity else [],
        lineage_events=[
            _lineage_response(event)
            for event in lineage_events_for_parcel(db, parcel.id)
        ],
    )


@router.post(
    "/deals/{deal_id}/nearby-parcel-searches",
    response_model=NearbyParcelSearchResponse,
    status_code=201,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def create_search(
    deal_id: str,
    payload: NearbyParcelSearchCreate,
    db: Session = Depends(get_db),
):
    try:
        search = create_nearby_parcel_search(
            db,
            deal_id=deal_id,
            anchor_brand_match_id=payload.anchor_brand_match_id,
            radius_miles=payload.radius_miles,
            persona=payload.persona,
            minimum_land_area_sq_ft=payload.minimum_land_area_sq_ft,
            zoning_codes=payload.zoning_codes,
            land_uses=payload.land_uses,
            limit=payload.limit,
        )
        db.commit()
        return get_nearby_parcel_search(db, search.id)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/deals/{deal_id}/nearby-parcel-searches",
    response_model=list[NearbyParcelSearchSummary],
)
def get_search_history(
    deal_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    try:
        return list_nearby_parcel_searches(db, deal_id, limit=limit)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/nearby-parcel-searches/{search_id}",
    response_model=NearbyParcelSearchResponse,
)
def get_search(search_id: str, db: Session = Depends(get_db)):
    search = get_nearby_parcel_search(db, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="Nearby parcel search not found")
    return search


@router.post(
    "/nearby-parcel-searches/{search_id}/export",
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def export_search(
    search_id: str,
    principal: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        exported = export_nearby_parcel_search(
            db,
            search_id=search_id,
            actor_user_id=principal["user_id"],
        )
        db.commit()
        return Response(
            content=exported.content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{exported.filename}"',
                "X-Exported-Count": str(exported.exported_count),
                "X-Omitted-Count": str(exported.omitted_count),
            },
        )
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ParcelExportDenied as exc:
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch(
    "/parcel-candidates/{candidate_id}",
    response_model=NearbyParcelCandidateResponse,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def patch_candidate(
    candidate_id: str,
    payload: NearbyParcelCandidateReview,
    db: Session = Depends(get_db),
):
    candidate = review_nearby_parcel_candidate(
        db, candidate_id, payload.review_status
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Nearby parcel candidate not found")
    db.commit()
    return candidate


@router.patch(
    "/parcel-candidates/{candidate_id}/assignment",
    response_model=NearbyParcelCandidateResponse,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def assign_candidate(
    candidate_id: str,
    payload: NearbyParcelCandidateAssignment,
    principal: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        candidate = assign_nearby_parcel_candidate(
            db,
            candidate_id=candidate_id,
            assigned_to_user_id=payload.assigned_to_user_id,
            actor_user_id=principal["user_id"],
        )
        if candidate is None:
            raise HTTPException(status_code=404, detail="Nearby parcel candidate not found")
        db.commit()
        return candidate
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/parcel-candidates/{candidate_id}/opportunity",
    response_model=NearbyParcelOpportunityResponse,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def promote_candidate(
    candidate_id: str,
    payload: NearbyParcelOpportunityCreate,
    principal: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        deal, created = promote_nearby_parcel_candidate_to_deal(
            db,
            candidate_id=candidate_id,
            name=payload.name,
            actor_user_id=principal["user_id"],
        )
        db.commit()
        db.refresh(deal)
        return NearbyParcelOpportunityResponse(
            created=created,
            candidate_id=candidate_id,
            deal=deal_to_detail_response(deal),
        )
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
