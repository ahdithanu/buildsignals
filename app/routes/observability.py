"""Workspace-admin operational summary."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.organization_membership import MemberRole
from app.schemas.observability import ObservabilityOverview, ObservabilityWindow
from app.services.observability_service import get_overview
from app.utils.auth_deps import require_role_strict

router = APIRouter(prefix="/observability", tags=["observability"])
admin = require_role_strict(MemberRole.admin)


@router.get("/overview", response_model=ObservabilityOverview)
def overview(
    days: ObservabilityWindow = ObservabilityWindow.week,
    principal: dict = Depends(admin),
    db: Session = Depends(get_db),
):
    return get_overview(db, principal["org_id"], days)
