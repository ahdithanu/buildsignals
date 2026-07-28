from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.buy_box import BuyBox
from app.models.deal import Deal
from app.models.organization_membership import MemberRole
from app.schemas.buy_box import BuyBoxCreate, BuyBoxResponse
from app.services.matching_service import match_deal
from app.utils.auth_deps import require_role
from app.utils.org_scope import active_query, get_org_id, scope_query

router = APIRouter(tags=["buy-box"])


# ── create buy box ──────────────────────────────────────────────────────────

@router.post(
    "/buy-box",
    response_model=BuyBoxResponse,
    status_code=201,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def create_buy_box(payload: BuyBoxCreate, db: Session = Depends(get_db)):
    box = BuyBox(**payload.model_dump())
    box.organization_id = get_org_id()
    db.add(box)
    db.commit()
    db.refresh(box)
    return box


# ── list buy boxes ──────────────────────────────────────────────────────────

@router.get("/buy-box", response_model=list[BuyBoxResponse])
def list_buy_boxes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    boxes = (
        scope_query(db.query(BuyBox), BuyBox)
        .order_by(BuyBox.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return boxes


# ── match deal to buy boxes ─────────────────────────────────────────────────

@router.get("/deals/{deal_id}/match-buy-boxes")
def match_deal_to_buy_boxes(deal_id: str, db: Session = Depends(get_db)):
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    matches = match_deal(db, deal)
    return {"deal_id": deal_id, "matches": matches}
