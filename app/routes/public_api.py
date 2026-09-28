from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models.api_key import OrganizationApiKey
from app.models.deal import Deal
from app.models.graph import GraphEntity, GraphEntityLink, GraphRelationship
from app.models.signal import Signal
from app.routes.deals import _deal_to_detail
from app.schemas.deal import DealDetailResponse, DealResponse, DealStatus
from app.schemas.graph import (
    GraphEntityResponse,
    GraphRelatedEntityResponse,
    GraphRelationshipResponse,
    OpportunityGraphContextResponse,
)
from app.schemas.signal import SignalResponse
from app.services.api_usage_service import record_api_key_usage, start_usage_timer
from app.services.graph_service import CONTEXT_BUCKETS
from app.utils.api_key_deps import require_api_key_scope
from app.utils.org_scope import active_query, scope_query

router = APIRouter(prefix="/public", tags=["public-api"])
read_api_key = require_api_key_scope("read")

GRAPH_BUCKET_KEYS = (
    "companies",
    "developers",
    "parcels",
    "owners",
    "contractors",
    "architects",
    "engineers",
    "permits",
    "cities",
    "lenders",
    "brokers",
    "other",
)


def _set_pagination_headers(
    response: Response,
    *,
    total_count: int,
    skip: int,
    limit: int,
    returned: int,
) -> None:
    next_skip = skip + returned
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Page-Skip"] = str(skip)
    response.headers["X-Page-Limit"] = str(limit)
    response.headers["X-Next-Skip"] = str(next_skip if next_skip < total_count else "")


def _graph_relationship_item(
    relationship: GraphRelationship,
    entity: GraphEntity,
    direction: str,
) -> GraphRelatedEntityResponse:
    return GraphRelatedEntityResponse(
        entity=GraphEntityResponse.model_validate(entity),
        relationship=GraphRelationshipResponse.model_validate(relationship),
        direction=direction,
    )


def _public_opportunity_graph_context(
    db: Session,
    *,
    organization_id: str,
    deal_id: str,
) -> OpportunityGraphContextResponse:
    root_links = (
        db.query(GraphEntityLink)
        .options(joinedload(GraphEntityLink.entity))
        .filter(
            GraphEntityLink.organization_id == organization_id,
            GraphEntityLink.record_type == "deal",
            GraphEntityLink.record_id == deal_id,
        )
        .all()
    )
    root_entities = [link.entity for link in root_links if link.entity is not None]
    grouped: dict[str, list[GraphRelatedEntityResponse]] = {bucket: [] for bucket in GRAPH_BUCKET_KEYS}
    seen: set[tuple[str, str]] = set()

    for root in root_entities:
        outgoing = (
            db.query(GraphRelationship)
            .options(joinedload(GraphRelationship.evidence), joinedload(GraphRelationship.target_entity))
            .filter(
                GraphRelationship.organization_id == organization_id,
                GraphRelationship.source_entity_id == root.id,
                GraphRelationship.is_current.is_(True),
            )
            .order_by(GraphRelationship.confidence.desc(), GraphRelationship.last_verified_at.desc())
            .all()
        )
        for relationship in outgoing:
            related = relationship.target_entity
            key = (relationship.id, related.id)
            if key in seen:
                continue
            seen.add(key)
            bucket = CONTEXT_BUCKETS.get(related.entity_type, "other")
            grouped[bucket].append(_graph_relationship_item(relationship, related, "outgoing"))

        incoming = (
            db.query(GraphRelationship)
            .options(joinedload(GraphRelationship.evidence), joinedload(GraphRelationship.source_entity))
            .filter(
                GraphRelationship.organization_id == organization_id,
                GraphRelationship.target_entity_id == root.id,
                GraphRelationship.is_current.is_(True),
            )
            .order_by(GraphRelationship.confidence.desc(), GraphRelationship.last_verified_at.desc())
            .all()
        )
        for relationship in incoming:
            related = relationship.source_entity
            key = (relationship.id, related.id)
            if key in seen:
                continue
            seen.add(key)
            bucket = CONTEXT_BUCKETS.get(related.entity_type, "other")
            grouped[bucket].append(_graph_relationship_item(relationship, related, "incoming"))

    return OpportunityGraphContextResponse(
        opportunity_id=deal_id,
        root_entities=[GraphEntityResponse.model_validate(entity) for entity in root_entities],
        **grouped,
    )


@router.get("/deals", response_model=list[DealResponse])
def list_public_deals(
    response: Response,
    status: DealStatus | None = Query(None),
    city: str | None = Query(None, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    api_key: OrganizationApiKey = Depends(read_api_key),
    db: Session = Depends(get_db),
):
    started_at = start_usage_timer()
    query = active_query(db.query(Deal), Deal, org_id=api_key.organization_id)
    if status is not None:
        query = query.filter(Deal.status == status.value)
    if city:
        query = query.filter(Deal.city == city)
    total_count = query.count()
    rows = query.order_by(Deal.created_at.desc()).offset(skip).limit(limit).all()
    _set_pagination_headers(
        response,
        total_count=total_count,
        skip=skip,
        limit=limit,
        returned=len(rows),
    )
    record_api_key_usage(
        db,
        api_key=api_key,
        method="GET",
        path="/public/deals",
        status_code=200,
        started_at=started_at,
        response_items=len(rows),
    )
    return rows


@router.get("/deals/{deal_id}", response_model=DealDetailResponse)
def get_public_deal(
    deal_id: str,
    api_key: OrganizationApiKey = Depends(read_api_key),
    db: Session = Depends(get_db),
):
    started_at = start_usage_timer()
    deal = active_query(db.query(Deal), Deal, org_id=api_key.organization_id).filter(
        Deal.id == deal_id
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    detail = _deal_to_detail(deal)
    record_api_key_usage(
        db,
        api_key=api_key,
        method="GET",
        path="/public/deals/{deal_id}",
        status_code=200,
        started_at=started_at,
        response_items=1,
    )
    return detail


@router.get("/deals/{deal_id}/graph-context", response_model=OpportunityGraphContextResponse)
def get_public_deal_graph_context(
    deal_id: str,
    api_key: OrganizationApiKey = Depends(read_api_key),
    db: Session = Depends(get_db),
):
    started_at = start_usage_timer()
    deal = active_query(db.query(Deal), Deal, org_id=api_key.organization_id).filter(
        Deal.id == deal_id
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    context = _public_opportunity_graph_context(
        db,
        organization_id=api_key.organization_id,
        deal_id=deal_id,
    )
    relationship_count = sum(len(getattr(context, bucket)) for bucket in GRAPH_BUCKET_KEYS)
    record_api_key_usage(
        db,
        api_key=api_key,
        method="GET",
        path="/public/deals/{deal_id}/graph-context",
        status_code=200,
        started_at=started_at,
        response_items=len(context.root_entities) + relationship_count,
    )
    return context


@router.get("/signals", response_model=list[SignalResponse])
def list_public_signals(
    response: Response,
    deal_id: str | None = None,
    signal_type: str | None = Query(None, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    api_key: OrganizationApiKey = Depends(read_api_key),
    db: Session = Depends(get_db),
):
    started_at = start_usage_timer()
    query = scope_query(db.query(Signal), Signal, org_id=api_key.organization_id)
    if deal_id:
        query = query.filter(Signal.deal_id == deal_id)
    if signal_type:
        query = query.filter(Signal.signal_type == signal_type)
    total_count = query.count()
    rows = query.order_by(Signal.created_at.desc()).offset(skip).limit(limit).all()
    _set_pagination_headers(
        response,
        total_count=total_count,
        skip=skip,
        limit=limit,
        returned=len(rows),
    )
    record_api_key_usage(
        db,
        api_key=api_key,
        method="GET",
        path="/public/signals",
        status_code=200,
        started_at=started_at,
        response_items=len(rows),
    )
    return rows
