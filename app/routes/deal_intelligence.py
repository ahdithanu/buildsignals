"""Routes for deal enrichment and scoring."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.deal import Deal
from app.schemas.deal import DealResponse
from app.services.enrichment_service import enrich_deal
from app.services.scoring_service import score_deal
from app.utils.org_scope import active_query

router = APIRouter(tags=["deal-intelligence"])


class ScoreResponse(BaseModel):
    deal_id: str
    score: float
    risk_level: str
    breakdown: dict


def _get_deal(deal_id: str, db: Session) -> Deal:
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


@router.post("/deals/{deal_id}/enrich", response_model=DealResponse)
def enrich(deal_id: str, db: Session = Depends(get_db)):
    """Run deterministic mock enrichment on a deal, filling missing fields."""
    deal = _get_deal(deal_id, db)
    enriched = enrich_deal(db, deal)
    return enriched


@router.post("/deals/{deal_id}/score", response_model=ScoreResponse)
def score(deal_id: str, db: Session = Depends(get_db)):
    """Score a deal 0-100 and assign a risk level."""
    deal = _get_deal(deal_id, db)
    result = score_deal(db, deal)
    return result
