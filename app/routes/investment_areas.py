from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.organization_membership import MemberRole
from app.services.investment_areas import investment_area, ranked_markets
from app.utils.auth_deps import require_role_strict

router = APIRouter(tags=["investment-areas"])
read_access = require_role_strict(MemberRole.admin, MemberRole.editor, MemberRole.viewer)


@router.get("/investment-areas/ranked", dependencies=[Depends(read_access)])
def get_ranked_markets(response: Response, q: str | None = Query(None, max_length=120),
                       limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return ranked_markets(query=q, limit=limit, offset=offset)
    except (RuntimeError, ValueError):
        raise HTTPException(503, "Investment-area inputs are temporarily unavailable",
                            headers={"Retry-After": "60", "Cache-Control": "no-store"}) from None


@router.get("/investment-areas", dependencies=[Depends(read_access)])
def get_investment_area(response: Response, cbsa: str = Query(..., pattern=r"^\d{5}$"), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Authorization, Cookie"
    try:
        return investment_area(db, cbsa)
    except LookupError:
        raise HTTPException(404, "Metro has insufficient aligned input data",
                            headers={"Cache-Control": "no-store"}) from None
    except (RuntimeError, ValueError):
        raise HTTPException(503, "Investment-area inputs are temporarily unavailable",
                            headers={"Retry-After": "60", "Cache-Control": "no-store"}) from None
