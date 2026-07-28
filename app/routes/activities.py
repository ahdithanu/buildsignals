from datetime import datetime
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.deal import Deal
from app.models.organization_membership import MemberRole
from app.models.outreach_activity import ActivityType, OutreachActivity
from app.utils.auth_deps import require_role
from app.utils.org_scope import active_query, get_org_id

router = APIRouter(tags=["activities"])

VALID_ACTIVITY_TYPES = {e.value for e in ActivityType}


# ── Schemas (local to this router) ────────────────────────────────────────

class ActivityTypeEnum(str, Enum):
    call = "call"
    email = "email"
    sms = "sms"
    note = "note"
    meeting = "meeting"
    system = "system"


class ActivityCreate(BaseModel):
    contact_id: Optional[str] = None
    activity_type: ActivityTypeEnum
    subject: Optional[str] = Field(None, max_length=500)
    body: Optional[str] = None
    follow_up_date: Optional[datetime] = None
    completed: bool = False


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    contact_id: Optional[str] = None
    activity_type: ActivityTypeEnum
    subject: Optional[str] = None
    body: Optional[str] = None
    follow_up_date: Optional[datetime] = None
    completed: bool
    created_at: datetime


# ── Helpers ────────────────────────────────────────────────────────────────

def _get_deal_or_404(db: Session, deal_id: str) -> Deal:
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found.")
    return deal


# ── GET /deals/{deal_id}/activities ────────────────────────────────────────

@router.get("/deals/{deal_id}/activities", response_model=list[ActivityResponse])
def list_activities(
    deal_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    _get_deal_or_404(db, deal_id)
    activities = (
        active_query(db.query(OutreachActivity), OutreachActivity)
        .filter(OutreachActivity.deal_id == deal_id)
        .order_by(OutreachActivity.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return activities


# ── POST /deals/{deal_id}/activities ───────────────────────────────────────

@router.post(
    "/deals/{deal_id}/activities",
    response_model=ActivityResponse,
    status_code=201,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def create_activity(
    deal_id: str,
    payload: ActivityCreate,
    db: Session = Depends(get_db),
):
    _get_deal_or_404(db, deal_id)

    # Strict enum validation (Pydantic already handles this, but be explicit)
    if payload.activity_type.value not in VALID_ACTIVITY_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid activity_type '{payload.activity_type}'.")

    activity = OutreachActivity(
        deal_id=deal_id,
        contact_id=payload.contact_id,
        activity_type=ActivityType(payload.activity_type.value),
        subject=payload.subject,
        body=payload.body,
        follow_up_date=payload.follow_up_date,
        completed=payload.completed,
    )
    activity.organization_id = get_org_id()
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


# ── GET /outreach/follow-ups ──────────────────────────────────────────────

@router.get("/outreach/follow-ups", response_model=list[ActivityResponse])
def list_follow_ups(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    activities = (
        active_query(db.query(OutreachActivity), OutreachActivity)
        .filter(
            OutreachActivity.follow_up_date.isnot(None),
            OutreachActivity.completed == False,  # noqa: E712
        )
        .order_by(OutreachActivity.follow_up_date.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return activities
