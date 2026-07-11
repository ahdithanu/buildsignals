from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.deal import Deal
from app.models.memo import Memo
from app.models.organization_membership import MemberRole
from app.services.memo_service import generate_memo
from app.services.rate_limiter import AI_LIMIT, AI_WINDOW, limiter
from app.utils.auth_deps import require_role
from app.utils.org_scope import active_query, get_org_id

router = APIRouter(tags=["memos"])


# ── Response / Request schemas ──────────────────────────────────────────────

class MemoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    title: Optional[str] = None
    content: Optional[str] = None
    version: int
    created_at: datetime
    updated_at: datetime


class MemoUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


# ── Helpers ─────────────────────────────────────────────────────────────────

def _ensure_deal_exists(db: Session, deal_id: str) -> Deal:
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


# ── Routes ──────────────────────────────────────────────────────────────────

@router.get("/deals/{deal_id}/memo", response_model=MemoResponse)
def get_memo(deal_id: str, db: Session = Depends(get_db)):
    """Return the existing memo for a deal, or 404 if none exists."""
    _ensure_deal_exists(db, deal_id)
    memo = active_query(db.query(Memo), Memo).filter(Memo.deal_id == deal_id).first()
    if memo is None:
        raise HTTPException(status_code=404, detail="Memo not found for this deal")
    return memo


@router.post(
    "/deals/{deal_id}/generate-memo",
    response_model=MemoResponse,
    status_code=201,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def generate_deal_memo(deal_id: str, db: Session = Depends(get_db)):
    """Generate (or regenerate) an investment memo from DB data."""
    decision = limiter.check(key=f"ai:{get_org_id()}", limit=AI_LIMIT, window_seconds=AI_WINDOW)
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="AI rate limit exceeded. Try again shortly.",
            headers={"Retry-After": str(decision.retry_after)},
        )
    _ensure_deal_exists(db, deal_id)
    memo = generate_memo(db, deal_id)
    if memo is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return memo


@router.put(
    "/deals/{deal_id}/memo",
    response_model=MemoResponse,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def update_memo(deal_id: str, payload: MemoUpdate, db: Session = Depends(get_db)):
    """Manually update memo content or title."""
    _ensure_deal_exists(db, deal_id)
    # Defence-in-depth: even though _ensure_deal_exists already scoped the
    # deal to the current org, scope the memo query too so a stray memo
    # whose organization_id has drifted cannot be mutated cross-org.
    memo = (
        active_query(db.query(Memo), Memo).filter(Memo.deal_id == deal_id).first()
    )
    if memo is None:
        raise HTTPException(status_code=404, detail="Memo not found for this deal")

    if payload.title is not None:
        memo.title = payload.title
    if payload.content is not None:
        memo.content = payload.content

    db.commit()
    db.refresh(memo)
    return memo


@router.delete(
    "/deals/{deal_id}/memo", status_code=204,
    dependencies=[Depends(require_role(MemberRole.admin))],
)
def delete_memo(deal_id: str, db: Session = Depends(get_db)):
    """Soft-delete the memo for a deal."""
    _ensure_deal_exists(db, deal_id)
    memo = active_query(db.query(Memo), Memo).filter(Memo.deal_id == deal_id).first()
    if memo is None:
        raise HTTPException(status_code=404, detail="Memo not found for this deal")
    memo.soft_delete()
    db.commit()
    return None
