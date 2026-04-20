from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.deal import Deal
from app.models.deal_distribution import DealDistribution
from app.schemas.deal_distribution import DealDistributionCreate, DealDistributionResponse
from app.utils.org_scope import get_org_id, active_query, scope_query
from app.services.audit_service import log_change

router = APIRouter(tags=["distributions"])


@router.post("/deals/{deal_id}/send", response_model=DealDistributionResponse, status_code=201)
def send_deal(deal_id: str, payload: DealDistributionCreate, db: Session = Depends(get_db)):
    """Log a deal distribution record. Does not send email — tracking only."""
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")

    dist = DealDistribution(
        deal_id=deal_id,
        organization_id=get_org_id(),
        recipient_name=payload.recipient_name,
        recipient_email=payload.recipient_email,
        notes=payload.notes,
        status="logged",
    )
    db.add(dist)
    db.commit()

    log_change(
        db, "deal_distribution", dist.id, "create",
        new_values={"deal_id": deal_id, "recipient": payload.recipient_email},
    )
    db.commit()

    db.refresh(dist)
    return dist


@router.get("/deals/{deal_id}/distributions", response_model=list[DealDistributionResponse])
def list_distributions(
    deal_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    dists = (
        scope_query(db.query(DealDistribution), DealDistribution)
        .filter(DealDistribution.deal_id == deal_id)
        .order_by(DealDistribution.sent_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return dists
