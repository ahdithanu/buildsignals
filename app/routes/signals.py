from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.buildsignal import BuildSignalReview, BuildSignalRevision
from app.models.deal import Deal
from app.models.organization_membership import MemberRole
from app.models.signal import Signal
from app.schemas.buildsignal import (
    BuildSignalAssessmentDraft,
    BuildSignalAssessmentResponse,
    BuildSignalReviewCreate,
    BuildSignalReviewResponse,
    BuildSignalRevisionResponse,
)
from app.schemas.signal import SignalCreate, SignalResponse
from app.services.buildsignal_assessment import (
    get_revision,
    resolve_assessment,
    review_revision,
    save_revision,
)
from app.services.normalization_service import normalize_signal_type
from app.utils.auth_deps import require_role, require_role_strict
from app.utils.org_scope import active_query, get_org_id, scope_query

router = APIRouter(tags=["signals"])


@router.post("/signals/{signal_id}/assessment-revisions", response_model=BuildSignalRevisionResponse, status_code=201)
def create_assessment_revision(
    signal_id: str, payload: BuildSignalAssessmentDraft,
    principal: dict = Depends(require_role_strict(MemberRole.admin, MemberRole.editor)),
    db: Session = Depends(get_db),
):
    return save_revision(db, signal_id, payload, principal["user_id"])


@router.get("/signals/{signal_id}/assessment-revisions", response_model=list[BuildSignalRevisionResponse],
            dependencies=[Depends(require_role_strict(MemberRole.admin, MemberRole.editor, MemberRole.viewer))])
def list_assessment_revisions(
    signal_id: str, limit: int = Query(50, ge=1, le=100), skip: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    if not scope_query(db.query(Signal), Signal).filter_by(id=signal_id).first():
        raise HTTPException(404, "Signal not found")
    return scope_query(db.query(BuildSignalRevision), BuildSignalRevision).filter_by(signal_id=signal_id).order_by(
        BuildSignalRevision.created_at.desc(), BuildSignalRevision.id.desc(),
    ).offset(skip).limit(limit).all()


@router.post("/assessment-revisions/{revision_id}/reviews", response_model=BuildSignalReviewResponse, status_code=201)
def create_assessment_review(
    revision_id: str, payload: BuildSignalReviewCreate,
    principal: dict = Depends(require_role_strict(MemberRole.admin)), db: Session = Depends(get_db),
):
    return review_revision(db, revision_id, payload, principal["user_id"])


@router.get("/assessment-revisions/{revision_id}/reviews", response_model=list[BuildSignalReviewResponse],
            dependencies=[Depends(require_role_strict(MemberRole.admin, MemberRole.editor, MemberRole.viewer))])
def list_assessment_reviews(
    revision_id: str, limit: int = Query(50, ge=1, le=100), skip: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    get_revision(db, revision_id)
    return scope_query(db.query(BuildSignalReview), BuildSignalReview).filter_by(revision_id=revision_id).order_by(
        BuildSignalReview.created_at.desc(), BuildSignalReview.id.desc(),
    ).offset(skip).limit(limit).all()


@router.post(
    "/signals/{signal_id}/assessment-preview",
    response_model=BuildSignalAssessmentResponse,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def preview_assessment(
    signal_id: str, payload: BuildSignalAssessmentDraft, db: Session = Depends(get_db),
):
    """Validate and resolve an analyst draft without publishing or storing it."""
    return resolve_assessment(db, signal_id, payload)


# ── list all signals ─────────────────────────────────────────────────────────

@router.get("/signals", response_model=list[SignalResponse])
def list_signals(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    signals = (
        scope_query(db.query(Signal), Signal)
        .order_by(Signal.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return signals


# ── create signal ────────────────────────────────────────────────────────────

@router.post(
    "/signals",
    response_model=SignalResponse,
    status_code=201,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def create_signal(payload: SignalCreate, db: Session = Depends(get_db)):
    if payload.deal_id:
        # Org-scope the deal lookup so we return 404 rather than leaking that a
        # deal with this id exists in a different organization.
        deal = (
            active_query(db.query(Deal), Deal)
            .filter(Deal.id == payload.deal_id)
            .first()
        )
        if not deal:
            raise HTTPException(status_code=404, detail=f"Deal {payload.deal_id} not found")
    signal = Signal(**payload.model_dump())
    signal.organization_id = get_org_id()
    signal.signal_type = normalize_signal_type(signal.signal_type) or signal.signal_type
    db.add(signal)
    db.commit()
    db.refresh(signal)
    return signal


# ── signals for a specific deal ──────────────────────────────────────────────

@router.get("/deals/{deal_id}/signals", response_model=list[SignalResponse])
def list_deal_signals(
    deal_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    # Org-scope: cross-org deal ids must look like "not found".
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    signals = (
        scope_query(db.query(Signal), Signal)
        .filter(Signal.deal_id == deal_id)
        .order_by(Signal.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return signals
