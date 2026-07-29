from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.deal import Deal
from app.models.organization_membership import MemberRole
from app.schemas.assumptions import AssumptionsResponse
from app.schemas.deal import (
    DealCreate,
    DealDetailResponse,
    DealResponse,
    DealStatus,
    DealUpdate,
)
from app.schemas.outputs import OutputsResponse
from app.services.audit_service import log_change, snapshot_fields
from app.services.deal_service import create_deal_with_defaults
from app.services.normalization_service import normalize_property_type
from app.utils.auth_deps import require_role
from app.utils.org_scope import active_query

router = APIRouter(prefix="/deals", tags=["deals"])


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_deal_or_404(deal_id: str, db: Session) -> Deal:
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    return deal


def _deal_to_detail(deal: Deal) -> dict:
    data = DealResponse.model_validate(deal).model_dump()
    data["assumptions"] = (
        AssumptionsResponse.model_validate(deal.assumptions) if deal.assumptions else None
    )
    data["outputs"] = (
        OutputsResponse.model_validate(deal.outputs) if deal.outputs else None
    )
    data["contacts_count"] = len(deal.contacts) if deal.contacts else 0
    return data


# ── list deals ───────────────────────────────────────────────────────────────

@router.get("", response_model=list[DealResponse])
def list_deals(
    status: Optional[DealStatus] = Query(None),
    property_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = active_query(db.query(Deal), Deal)
    if status is not None:
        q = q.filter(Deal.status == status.value)
    if property_type is not None:
        q = q.filter(Deal.property_type == property_type)
    deals = q.order_by(Deal.created_at.desc()).offset(skip).limit(limit).all()
    return deals


# ── create deal ──────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=DealDetailResponse,
    status_code=201,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def create_deal(payload: DealCreate, db: Session = Depends(get_db)):
    deal = create_deal_with_defaults(db, payload)
    db.commit()

    log_change(db, "deal", deal.id, "create", new_values={"name": deal.name})
    db.commit()

    db.refresh(deal)
    return _deal_to_detail(deal)


# ── get deal detail ──────────────────────────────────────────────────────────

@router.get("/{deal_id}", response_model=DealDetailResponse)
def get_deal(deal_id: str, db: Session = Depends(get_db)):
    deal = _get_deal_or_404(deal_id, db)
    return _deal_to_detail(deal)


# ── partial update ───────────────────────────────────────────────────────────

@router.patch(
    "/{deal_id}",
    response_model=DealResponse,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def update_deal(deal_id: str, payload: DealUpdate, db: Session = Depends(get_db)):
    deal = _get_deal_or_404(deal_id, db)
    update_data = payload.model_dump(exclude_unset=True)
    old = snapshot_fields(deal, ["name", "address", "property_type", "asking_price", "notes"])
    if "property_type" in update_data:
        update_data["property_type"] = normalize_property_type(update_data["property_type"])
    for field, value in update_data.items():
        setattr(deal, field, value)
    db.commit()

    log_change(db, "deal", deal.id, "update", old_values=old, new_values=update_data)
    db.commit()

    db.refresh(deal)
    return deal


# ── bulk import ──────────────────────────────────────────────────────────────

# ── soft delete ─────────────────────────────────────────────────────────────

@router.delete(
    "/{deal_id}", status_code=204,
    dependencies=[Depends(require_role(MemberRole.admin))],
)
def delete_deal(deal_id: str, db: Session = Depends(get_db)):
    deal = _get_deal_or_404(deal_id, db)
    old = snapshot_fields(deal, ["name", "status"])
    deal.soft_delete()
    db.commit()
    log_change(db, "deal", deal.id, "soft_delete", old_values=old)
    db.commit()
    return None


# ── bulk import ──────────────────────────────────────────────────────────────

@router.post(
    "/import",
    response_model=list[DealDetailResponse],
    status_code=201,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def import_deals(payloads: list[DealCreate], db: Session = Depends(get_db)):
    results = []
    for payload in payloads:
        deal = create_deal_with_defaults(db, payload)
        db.flush()
        db.refresh(deal)
        results.append(_deal_to_detail(deal))
    db.commit()
    return results
