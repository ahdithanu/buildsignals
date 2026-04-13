from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.deal import Deal
from app.services.pipeline_service import move_deal_stage
from app.utils.org_scope import active_query

router = APIRouter(tags=["pipeline"])


# ── Schemas ────────────────────────────────────────────────────────────────

class MoveStageRequest(BaseModel):
    stage: str = Field(..., min_length=1)
    changed_by: str = Field(default="system", min_length=1)


class PipelineEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    from_stage: str
    to_stage: str
    changed_by: Optional[str] = None
    created_at: datetime


# ── POST /deals/{deal_id}/move-stage ──────────────────────────────────────

@router.post("/deals/{deal_id}/move-stage", response_model=PipelineEventResponse)
def move_stage(
    deal_id: str,
    payload: MoveStageRequest,
    db: Session = Depends(get_db),
):
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found.")

    event = move_deal_stage(db, deal, payload.stage, changed_by=payload.changed_by)
    db.commit()
    db.refresh(event)
    return event
