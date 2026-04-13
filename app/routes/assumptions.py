"""Routes for deal assumptions and underwriting outputs."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.deal import Deal
from app.models.deal_assumptions import DealAssumptions
from app.schemas.assumptions import AssumptionsUpdate, AssumptionsResponse
from app.schemas.outputs import OutputsResponse
from app.services.underwriting_service import calculate_and_persist, UnderwritingError
from app.utils.org_scope import active_query
from app.services.audit_service import log_change, snapshot_fields

router = APIRouter(tags=["assumptions"])


def _get_deal(deal_id: str, db: Session) -> Deal:
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


# ── GET assumptions ─────────────────────────────────────────────────────────

@router.get("/deals/{deal_id}/assumptions", response_model=AssumptionsResponse)
def get_assumptions(deal_id: str, db: Session = Depends(get_db)):
    deal = _get_deal(deal_id, db)
    if deal.assumptions is None:
        raise HTTPException(status_code=404, detail="No assumptions found for this deal")
    return deal.assumptions


# ── PUT assumptions (auto-recalculate) ──────────────────────────────────────

@router.put("/deals/{deal_id}/assumptions", response_model=AssumptionsResponse)
def update_assumptions(
    deal_id: str,
    payload: AssumptionsUpdate,
    db: Session = Depends(get_db),
):
    deal = _get_deal(deal_id, db)

    if deal.assumptions is None:
        # Create new assumptions from payload + defaults
        assumptions = DealAssumptions(deal_id=deal_id)
        db.add(assumptions)
        db.flush()
        deal.assumptions = assumptions

    old = snapshot_fields(deal.assumptions, ["purchase_price", "interest_rate", "loan_amount", "vacancy_pct"])
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(deal.assumptions, field, value)

    db.commit()

    log_change(db, "deal_assumptions", deal.assumptions.id, "update", old_values=old, new_values=update_data)
    db.commit()

    db.refresh(deal.assumptions)

    # Auto-recalculate outputs (business rule #2)
    try:
        calculate_and_persist(db, deal.assumptions)
    except UnderwritingError:
        # Assumptions may be incomplete — that is okay, outputs just won't update
        pass

    db.refresh(deal.assumptions)
    return deal.assumptions


# ── GET outputs ─────────────────────────────────────────────────────────────

@router.get("/deals/{deal_id}/outputs", response_model=OutputsResponse)
def get_outputs(deal_id: str, db: Session = Depends(get_db)):
    deal = _get_deal(deal_id, db)
    if deal.outputs is None:
        raise HTTPException(status_code=404, detail="No outputs found for this deal")
    return deal.outputs


# ── POST recalculate ────────────────────────────────────────────────────────

@router.post("/deals/{deal_id}/recalculate", response_model=OutputsResponse)
def recalculate(deal_id: str, db: Session = Depends(get_db)):
    deal = _get_deal(deal_id, db)
    if deal.assumptions is None:
        raise HTTPException(status_code=400, detail="Cannot recalculate — no assumptions exist")

    try:
        outputs = calculate_and_persist(db, deal.assumptions)
    except UnderwritingError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return outputs
