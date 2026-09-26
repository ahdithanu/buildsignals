from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.organization_membership import MemberRole
from app.schemas.planning import (
    PlanningCompanyMatchResponse,
    PlanningCompanyMatchReview,
    PlanningRecordResponse,
)
from app.services.planning_intelligence import (
    get_planning_record,
    list_planning_records,
    review_company_match,
)
from app.utils.auth_deps import require_role

router = APIRouter(prefix="/planning", tags=["planning intelligence"])


@router.get("/events", response_model=list[PlanningRecordResponse])
def list_events(
    brand_id: str | None = Query(default=None, min_length=1, max_length=36),
    state: str | None = Query(default=None, min_length=2, max_length=2),
    city: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=100),
    minimum_priority: float = Query(default=0, ge=0, le=100),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return list_planning_records(
        db,
        brand_id=brand_id,
        state=state,
        city=city,
        category=category,
        minimum_priority=minimum_priority,
        limit=limit,
    )


@router.get("/events/{record_id}", response_model=PlanningRecordResponse)
def get_event(
    record_id: str,
    db: Session = Depends(get_db),
):
    record = get_planning_record(db, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Planning event not found")
    return record


@router.patch(
    "/company-matches/{match_id}",
    response_model=PlanningCompanyMatchResponse,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def review_match(
    match_id: str,
    payload: PlanningCompanyMatchReview,
    db: Session = Depends(get_db),
):
    match = review_company_match(db, match_id, payload.review_status)
    if match is None:
        raise HTTPException(status_code=404, detail="Planning company match not found")
    return match
