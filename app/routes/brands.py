from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.brand import BrandProfile
from app.models.deal import Deal
from app.models.organization_membership import MemberRole
from app.schemas.brand import (
    BrandProfileResponse,
    PermitBrandMatchEvidenceResponse,
    PermitBrandMatchResponse,
    PermitBrandMatchReview,
    PermitBrandOpportunityCreate,
    PermitBrandOpportunityResponse,
)
from app.services.audit_service import log_change
from app.services.brand_intelligence import (
    create_or_get_opportunity_from_brand_match,
    get_brand_match_evidence,
    list_brand_matches,
    list_deal_brand_matches,
    review_brand_match,
    serialize_brand_match,
)
from app.utils.auth_deps import require_role
from app.utils.org_scope import active_query

router = APIRouter(tags=["brand intelligence"])


@router.get("/brands", response_model=list[BrandProfileResponse])
def get_brands(db: Session = Depends(get_db)):
    return active_query(db.query(BrandProfile), BrandProfile).order_by(
        BrandProfile.priority.desc(), BrandProfile.name
    ).all()


@router.get("/permit-brand-matches", response_model=list[PermitBrandMatchResponse])
def get_permit_brand_matches(
    review_status: str | None = Query(
        default=None, pattern=r"^(candidate|confirmed|dismissed|retracted)$"
    ),
    approval_stage: str | None = Query(
        default=None, pattern=r"^(pre_approval|approved)$"
    ),
    detection_method: str | None = Query(
        default=None, pattern=r"^(direct_alias|historical_party)$"
    ),
    freshness: str | None = Query(
        default=None, pattern=r"^(fresh|active|aging|stale)$"
    ),
    sort_by: str = Query(default="confidence", pattern=r"^(confidence|freshness)$"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return list_brand_matches(
        db,
        review_status=review_status,
        approval_stage=approval_stage,
        detection_method=detection_method,
        freshness=freshness,
        sort_by=sort_by,
        limit=limit,
    )


@router.get(
    "/deals/{deal_id}/permit-brand-matches",
    response_model=list[PermitBrandMatchResponse],
)
def get_deal_permit_brand_matches(
    deal_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return list_deal_brand_matches(db, deal_id, limit=limit)


@router.get(
    "/permit-brand-matches/{match_id}/evidence",
    response_model=PermitBrandMatchEvidenceResponse,
)
def get_permit_brand_match_evidence(
    match_id: str,
    db: Session = Depends(get_db),
):
    evidence = get_brand_match_evidence(db, match_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Permit brand match not found")
    return evidence


@router.patch(
    "/permit-brand-matches/{match_id}",
    response_model=PermitBrandMatchResponse,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def patch_permit_brand_match(
    match_id: str,
    payload: PermitBrandMatchReview,
    db: Session = Depends(get_db),
):
    match = review_brand_match(db, match_id, payload.review_status)
    if match is None:
        raise HTTPException(status_code=404, detail="Permit brand match not found")
    db.commit()
    db.refresh(match)
    return serialize_brand_match(db, match)


@router.post(
    "/permit-brand-matches/{match_id}/opportunity",
    response_model=PermitBrandOpportunityResponse,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def create_opportunity_from_brand_match(
    match_id: str,
    payload: PermitBrandOpportunityCreate,
    db: Session = Depends(get_db),
):
    result = create_or_get_opportunity_from_brand_match(db, match_id, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Permit brand match not found")
    if result.created:
        log_change(
            db,
            "deal",
            result.deal.id,
            "create_from_permit_brand_match",
            new_values={"name": result.deal.name, "match_id": match_id},
        )
    db.commit()
    return result
