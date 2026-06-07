"""Routes for deal enrichment and scoring."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.deal import Deal
from app.schemas.deal import DealResponse
from app.services.enrichment_service import enrich_deal
from app.services.scoring_service import score_deal
from app.services.rate_limiter import limiter, AI_LIMIT, AI_WINDOW
from app.utils.org_scope import active_query, get_org_id
from app.utils.auth_deps import require_role
from app.models.organization_membership import MemberRole

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


@router.post(
    "/deals/{deal_id}/enrich",
    response_model=DealResponse,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def enrich(deal_id: str, db: Session = Depends(get_db)):
    """Run deterministic mock enrichment on a deal, filling missing fields."""
    decision = limiter.check(key=f"ai:{get_org_id()}", limit=AI_LIMIT, window_seconds=AI_WINDOW)
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="AI rate limit exceeded. Try again shortly.",
            headers={"Retry-After": str(decision.retry_after)},
        )
    deal = _get_deal(deal_id, db)
    enriched = enrich_deal(db, deal)
    return enriched


@router.post(
    "/deals/{deal_id}/score",
    response_model=ScoreResponse,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def score(deal_id: str, db: Session = Depends(get_db)):
    """Score a deal 0-100 and assign a risk level."""
    decision = limiter.check(key=f"ai:{get_org_id()}", limit=AI_LIMIT, window_seconds=AI_WINDOW)
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="AI rate limit exceeded. Try again shortly.",
            headers={"Retry-After": str(decision.retry_after)},
        )
    deal = _get_deal(deal_id, db)
    result = score_deal(db, deal)
    return result
