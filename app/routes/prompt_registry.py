"""Admin-only prompt registry APIs. Stored prompts are not executed by this route."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.organization_membership import MemberRole
from app.schemas.prompt_registry import (
    PreviewRequest,
    PreviewResponse,
    TemplateCreate,
    TemplateDetail,
    TemplateSummary,
    VersionCreate,
)
from app.services import prompt_registry_service as service
from app.utils.auth_deps import require_role_strict

router = APIRouter(prefix="/prompts", tags=["prompt-registry"])
admin = require_role_strict(MemberRole.admin)


@router.get("", response_model=list[TemplateSummary])
def list_prompts(principal: dict = Depends(admin), db: Session = Depends(get_db)):
    return service.list_templates(db, principal["org_id"])


@router.post("", response_model=TemplateDetail, status_code=201)
def create_prompt(payload: TemplateCreate, principal: dict = Depends(admin), db: Session = Depends(get_db)):
    return service.create_template(db, principal["org_id"], principal["user_id"], payload)


@router.get("/{template_id}", response_model=TemplateDetail)
def prompt_detail(template_id: str, principal: dict = Depends(admin), db: Session = Depends(get_db)):
    return service.detail(db, principal["org_id"], template_id)


@router.post("/{template_id}/versions", response_model=TemplateDetail, status_code=201)
def new_version(template_id: str, payload: VersionCreate, principal: dict = Depends(admin), db: Session = Depends(get_db)):
    return service.create_version(db, principal["org_id"], principal["user_id"], template_id, payload)


@router.post("/{template_id}/versions/{version}/activate", response_model=TemplateDetail)
def activate(template_id: str, version: int, principal: dict = Depends(admin), db: Session = Depends(get_db)):
    return service.activate(db, principal["org_id"], principal["user_id"], template_id, version)


@router.post("/{template_id}/preview", response_model=PreviewResponse)
def preview(template_id: str, payload: PreviewRequest, principal: dict = Depends(admin), db: Session = Depends(get_db)):
    return service.preview(db, principal["org_id"], template_id, payload)
