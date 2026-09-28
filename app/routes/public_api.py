from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.api_key import OrganizationApiKey
from app.models.deal import Deal
from app.models.signal import Signal
from app.routes.deals import _deal_to_detail
from app.schemas.deal import DealDetailResponse, DealResponse, DealStatus
from app.schemas.signal import SignalResponse
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
    query = active_query(db.query(Deal), Deal, org_id=api_key.organization_id)
    if status is not None:
        query = query.filter(Deal.status == status.value)
    if city:
        query = query.filter(Deal.city == city)
    return query.order_by(Deal.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/deals/{deal_id}", response_model=DealDetailResponse)
def get_public_deal(
    deal_id: str,
    api_key: OrganizationApiKey = Depends(read_api_key),
    db: Session = Depends(get_db),
):
    deal = active_query(db.query(Deal), Deal, org_id=api_key.organization_id).filter(
        Deal.id == deal_id
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    return _deal_to_detail(deal)


@router.get("/signals", response_model=list[SignalResponse])
def list_public_signals(
    deal_id: str | None = None,
    signal_type: str | None = Query(None, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    api_key: OrganizationApiKey = Depends(read_api_key),
    db: Session = Depends(get_db),
):
    query = scope_query(db.query(Signal), Signal, org_id=api_key.organization_id)
    if deal_id:
        query = query.filter(Signal.deal_id == deal_id)
    if signal_type:
        query = query.filter(Signal.signal_type == signal_type)
    return query.order_by(Signal.created_at.desc()).offset(skip).limit(limit).all()
