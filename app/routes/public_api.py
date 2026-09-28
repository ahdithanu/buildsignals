from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.api_key import OrganizationApiKey
from app.models.deal import Deal
from app.models.signal import Signal
from app.routes.deals import _deal_to_detail
from app.schemas.deal import DealDetailResponse, DealResponse, DealStatus
from app.schemas.signal import SignalResponse
from app.services.api_usage_service import record_api_key_usage, start_usage_timer
from app.utils.api_key_deps import require_api_key_scope
from app.utils.org_scope import active_query, scope_query

router = APIRouter(prefix="/public", tags=["public-api"])
read_api_key = require_api_key_scope("read")


@router.get("/deals", response_model=list[DealResponse])
def list_public_deals(
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
    rows = query.order_by(Deal.created_at.desc()).offset(skip).limit(limit).all()
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


@router.get("/signals", response_model=list[SignalResponse])
def list_public_signals(
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
    rows = query.order_by(Signal.created_at.desc()).offset(skip).limit(limit).all()
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
