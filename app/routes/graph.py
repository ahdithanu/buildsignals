from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.deal import Deal
from app.models.graph import GraphEntity, GraphEntityType
from app.models.organization_membership import MemberRole
from app.schemas.graph import (
    GraphBuyerLensSummary,
    GraphEntityCreate,
    GraphEntityDetailResponse,
    GraphEntityResponse,
    GraphEntitySearchResponse,
    GraphPathResponse,
    GraphRelatedEntityResponse,
    GraphRelationshipCreate,
    GraphRelationshipResponse,
    GraphSharedParcelSummary,
    OpportunityGraphContextResponse,
)
from app.services.brand_intelligence import list_deal_brand_matches
from app.services.graph_service import (
    create_relationship,
    find_relationship_paths,
    get_entity_or_none,
    opportunity_context,
    relationships_for_entity,
    resolve_entity,
    search_entities,
    sync_deal_contacts_to_graph,
    upsert_deal_graph_context,
)
from app.services.parcel_service import (
    count_nearby_parcel_searches_for_deal,
    summarize_nearby_parcel_searches_for_deal,
    summarize_shared_parcels_for_deal,
)
from app.utils.auth_deps import require_role
from app.utils.org_scope import active_query

router = APIRouter(prefix="/graph", tags=["graph"])
opportunity_router = APIRouter(tags=["graph"])


def _relationship_item(row) -> GraphRelatedEntityResponse:
    relationship, entity, direction = row
    return GraphRelatedEntityResponse(
        entity=GraphEntityResponse.model_validate(entity),
        relationship=GraphRelationshipResponse.model_validate(relationship),
        direction=direction,
    )


def _context_response(opportunity_id: str, db: Session) -> OpportunityGraphContextResponse:
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == opportunity_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Opportunity {opportunity_id} not found")

    roots = active_query(db.query(GraphEntity), GraphEntity).join(GraphEntity.links).filter(
        GraphEntity.links.any(record_type="deal", record_id=opportunity_id)
    ).all()
    if not roots:
        upsert_deal_graph_context(db, deal)
        db.commit()
    sync_deal_contacts_to_graph(db, deal)
    db.commit()

    context = opportunity_context(db, opportunity_id)
    return OpportunityGraphContextResponse(
        opportunity_id=opportunity_id,
        root_entities=[GraphEntityResponse.model_validate(entity) for entity in context["root_entities"]],
        nearby_parcel_searches=count_nearby_parcel_searches_for_deal(db, opportunity_id),
        buyer_lenses=[
            GraphBuyerLensSummary.model_validate(row)
            for row in summarize_nearby_parcel_searches_for_deal(db, opportunity_id)
        ],
        shared_parcels=[
            GraphSharedParcelSummary.model_validate(row)
            for row in summarize_shared_parcels_for_deal(db, opportunity_id)
        ],
        permit_brand_matches=list_deal_brand_matches(db, opportunity_id, limit=6),
        companies=[_relationship_item(item) for item in context["companies"]],
        developers=[_relationship_item(item) for item in context["developers"]],
        parcels=[_relationship_item(item) for item in context["parcels"]],
        owners=[_relationship_item(item) for item in context["owners"]],
        contractors=[_relationship_item(item) for item in context["contractors"]],
        architects=[_relationship_item(item) for item in context["architects"]],
        engineers=[_relationship_item(item) for item in context["engineers"]],
        permits=[_relationship_item(item) for item in context["permits"]],
        cities=[_relationship_item(item) for item in context["cities"]],
        lenders=[_relationship_item(item) for item in context["lenders"]],
        brokers=[_relationship_item(item) for item in context["brokers"]],
        other=[_relationship_item(item) for item in context["other"]],
    )


@router.post(
    "/entities",
    response_model=GraphEntityResponse,
    status_code=201,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def create_entity(payload: GraphEntityCreate, db: Session = Depends(get_db)):
    entity, _created = resolve_entity(db, payload)
    db.commit()
    db.refresh(entity)
    return entity


@router.get("/entities/{entity_id}", response_model=GraphEntityDetailResponse)
def get_entity(entity_id: str, db: Session = Depends(get_db)):
    entity = get_entity_or_none(db, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    related = [_relationship_item(row) for row in relationships_for_entity(db, entity_id)]
    return GraphEntityDetailResponse(
        **GraphEntityResponse.model_validate(entity).model_dump(),
        aliases=[alias.alias for alias in entity.aliases],
        links=[
            {"record_type": link.record_type, "record_id": link.record_id}
            for link in entity.links
        ],
        related=related,
    )


@router.get("/entities", response_model=list[GraphEntitySearchResponse])
def search_graph_entities(
    q: str = Query(..., min_length=1),
    entity_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    entity_type_enum = GraphEntityType(entity_type) if entity_type else None
    return [
        GraphEntitySearchResponse(
            **GraphEntityResponse.model_validate(entity).model_dump(),
            aliases=[alias.alias for alias in entity.aliases],
        )
        for entity in search_entities(db, q, entity_type=entity_type_enum, limit=limit)
    ]


@router.get("/entities/{entity_id}/related", response_model=list[GraphRelatedEntityResponse])
def related_entities(entity_id: str, db: Session = Depends(get_db)):
    entity = get_entity_or_none(db, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    return [_relationship_item(row) for row in relationships_for_entity(db, entity_id)]


@router.post(
    "/relationships",
    response_model=GraphRelationshipResponse,
    status_code=201,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def add_relationship(payload: GraphRelationshipCreate, db: Session = Depends(get_db)):
    try:
        relationship = create_relationship(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    db.refresh(relationship)
    return relationship


@router.get("/paths", response_model=list[GraphPathResponse])
def relationship_paths(
    source_entity_id: str = Query(...),
    target_entity_id: str = Query(...),
    max_depth: int = Query(4, ge=1, le=6),
    db: Session = Depends(get_db),
):
    if get_entity_or_none(db, source_entity_id) is None:
        raise HTTPException(status_code=404, detail=f"Entity {source_entity_id} not found")
    if get_entity_or_none(db, target_entity_id) is None:
        raise HTTPException(status_code=404, detail=f"Entity {target_entity_id} not found")
    paths = find_relationship_paths(db, source_entity_id, target_entity_id, max_depth)
    return [
        GraphPathResponse(
            entities=[GraphEntityResponse.model_validate(entity) for entity in entities],
            relationships=[GraphRelationshipResponse.model_validate(relationship) for relationship in relationships],
        )
        for entities, relationships in paths
    ]


@opportunity_router.get("/opportunities/{opportunity_id}/graph-context", response_model=OpportunityGraphContextResponse)
def get_opportunity_graph_context(opportunity_id: str, db: Session = Depends(get_db)):
    return _context_response(opportunity_id, db)


@opportunity_router.get("/deals/{deal_id}/graph-context", response_model=OpportunityGraphContextResponse)
def get_deal_graph_context(deal_id: str, db: Session = Depends(get_db)):
    return _context_response(deal_id, db)
