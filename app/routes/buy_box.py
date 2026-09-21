import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.acquisition_screen import AcquisitionScreenSnapshot
from app.models.buy_box import BuyBox
from app.models.deal import Deal
from app.models.organization_membership import MemberRole
from app.schemas.buy_box import AcquisitionCriteria, BuyBoxCreate, BuyBoxResponse
from app.services.acquisition_history import (
    review_export_context,
    save_screen_snapshot,
    verified_snapshot_content,
)
from app.services.acquisition_screening import screen_acquisition
from app.services.audit_service import log_change
from app.services.matching_service import match_deal
from app.utils.auth_deps import get_current_user, require_role
from app.utils.org_scope import active_query, get_org_id, scope_query

router = APIRouter(tags=["buy-box"])


@router.get("/deals/{deal_id}/acquisition-screen", dependencies=[Depends(get_current_user)])
def acquisition_screen(
    deal_id: str, response: Response,
    profile: str = Query(default="small_multifamily", pattern="^(small_multifamily|small_bay_retail)$"),
    market_city: str | None = Query(default=None, min_length=1, max_length=100),
    market_state: str | None = Query(default=None, pattern="^[A-Za-z]{2}$"),
    db: Session = Depends(get_db),
    buy_box_id: str | None = None,
):
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    response.headers["Cache-Control"] = "no-store"
    custom = None
    if buy_box_id is not None:
        box = scope_query(db.query(BuyBox), BuyBox).filter(BuyBox.id == buy_box_id).first()
        if box is None:
            raise HTTPException(status_code=404, detail="Buy box not found")
        if box.acquisition_criteria is None:
            raise HTTPException(status_code=422, detail="Buy box has no structured acquisition criteria")
        custom = AcquisitionCriteria.model_validate(box.acquisition_criteria)
    result = screen_acquisition(deal, profile, market_city, market_state, custom_criteria=custom)
    result["buy_box_id"] = buy_box_id
    result["criteria_snapshot"] = custom.model_dump() if custom else None
    return result


@router.post("/deals/{deal_id}/acquisition-screen/export",
             dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))])
def export_acquisition_screen(
    deal_id: str,
    profile: str = Query(default="small_multifamily", pattern="^(small_multifamily|small_bay_retail)$"),
    market_city: str | None = Query(default=None, min_length=1, max_length=100),
    market_state: str | None = Query(default=None, pattern="^[A-Za-z]{2}$"),
    principal: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    buy_box_id: str | None = None,
):
    screen = acquisition_screen(deal_id, Response(), profile, market_city, market_state, db, buy_box_id)
    criteria = screen["criteria_snapshot"]
    if criteria:
        market_city, market_state = criteria["market_city"], criteria["market_state"]
    try:
        reviews = review_export_context(db, deal_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    snapshot = {
        "schema_version": "acquisition-screen-export-v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_market": {"city": market_city, "state": market_state},
        "screen": screen,
        "diligence_reviews": reviews,
        "limitations": [
            "Snapshot of recorded deal facts, not verified source evidence or underwriting.",
            "Unknown criteria remain unresolved; this is not an investment recommendation.",
            "Does not establish listing availability, parcel ownership, or market coverage.",
            "Includes at most ten latest opportunity reviews; assessments do not override screening and may conflict.",
        ],
    }
    content = json.dumps(jsonable_encoder(snapshot), ensure_ascii=True, allow_nan=False, indent=2)
    saved = save_screen_snapshot(db, deal_id, principal["user_id"], content)
    log_change(db, "deal", deal_id, "acquisition_screen_export", actor_id=principal["user_id"],
               new_values={"content_sha256": saved.content_sha256, "snapshot_id": saved.id,
                           "method_version": screen["method_version"], "profile": screen["profile"],
                           "buy_box_id": buy_box_id,
                           "counts": screen["counts"], "generated_at": snapshot["generated_at"]})
    db.commit()
    return Response(content=content, media_type="application/json", headers={
        "Cache-Control": "no-store",
        "X-Acquisition-Snapshot-Id": saved.id,
        "Content-Disposition": 'attachment; filename="acquisition-screen.json"',
    })


@router.get("/deals/{deal_id}/acquisition-screen/history", dependencies=[Depends(get_current_user)])
def acquisition_screen_history(
    deal_id: str, response: Response,
    skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first() is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    rows = scope_query(db.query(AcquisitionScreenSnapshot), AcquisitionScreenSnapshot).filter(
        AcquisitionScreenSnapshot.deal_id == deal_id,
    ).order_by(AcquisitionScreenSnapshot.created_at.desc(), AcquisitionScreenSnapshot.id.desc()).offset(skip).limit(limit + 1).all()
    response.headers["Cache-Control"] = "no-store"
    return {"items": [{"id": row.id, "created_at": row.created_at,
                       "author_id": row.author_id, "content_sha256": row.content_sha256}
                      for row in rows[:limit]], "has_more": len(rows) > limit}


@router.get("/deals/{deal_id}/acquisition-screen/history/{snapshot_id}",
            dependencies=[Depends(get_current_user)])
def acquisition_screen_snapshot(deal_id: str, snapshot_id: str, db: Session = Depends(get_db)):
    if active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first() is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    row = scope_query(db.query(AcquisitionScreenSnapshot), AcquisitionScreenSnapshot).filter(
        AcquisitionScreenSnapshot.deal_id == deal_id, AcquisitionScreenSnapshot.id == snapshot_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    try:
        content = verified_snapshot_content(row)
    except ValueError:
        raise HTTPException(status_code=500, detail="Snapshot integrity check failed") from None
    return Response(content=content, media_type="application/json", headers={
        "Cache-Control": "no-store",
        "Content-Disposition": 'attachment; filename="acquisition-screen.json"',
    })


# ── create buy box ──────────────────────────────────────────────────────────

@router.post(
    "/buy-box",
    response_model=BuyBoxResponse,
    status_code=201,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def create_buy_box(payload: BuyBoxCreate, db: Session = Depends(get_db),
                   principal: dict = Depends(get_current_user)):
    box = BuyBox(**payload.model_dump())
    box.organization_id = get_org_id()
    box.user_id = principal["user_id"]
    db.add(box)
    db.commit()
    db.refresh(box)
    return box


# ── list buy boxes ──────────────────────────────────────────────────────────

@router.get("/buy-box", response_model=list[BuyBoxResponse])
def list_buy_boxes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    boxes = (
        scope_query(db.query(BuyBox), BuyBox)
        .order_by(BuyBox.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return boxes


# ── match deal to buy boxes ─────────────────────────────────────────────────

@router.get("/deals/{deal_id}/match-buy-boxes")
def match_deal_to_buy_boxes(deal_id: str, db: Session = Depends(get_db)):
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    matches = match_deal(db, deal)
    return {"deal_id": deal_id, "matches": matches}
