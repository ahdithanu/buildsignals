"""Immutable prompt versioning and audited activation, with no implicit execution."""

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.prompt_registry import PromptTemplate, PromptVersion
from app.schemas.prompt_registry import (
    HistoryRead,
    PreviewRequest,
    PreviewResponse,
    TemplateCreate,
    TemplateDetail,
    TemplateSummary,
    VersionCreate,
    VersionRead,
    render,
)
from app.services.audit_service import log_change


def _digest(body: str, variables: list[str]) -> str:
    payload = json.dumps({"body": body, "variables": sorted(variables)}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _template(db: Session, org_id: str, template_id: str, *, lock: bool = False) -> PromptTemplate:
    query = db.query(PromptTemplate).filter_by(organization_id=org_id, id=template_id)
    row = (query.with_for_update() if lock else query).first()
    if row is None:
        raise HTTPException(404, "Prompt template not found")
    return row


def _version(db: Session, org_id: str, template_id: str, number: int) -> PromptVersion:
    row = db.query(PromptVersion).filter_by(
        organization_id=org_id, template_id=template_id, version=number,
    ).first()
    if row is None:
        raise HTTPException(404, "Prompt version not found")
    return row


def list_templates(db: Session, org_id: str) -> list[TemplateSummary]:
    rows = db.query(PromptTemplate).filter_by(organization_id=org_id).order_by(PromptTemplate.key).limit(201).all()
    if len(rows) > 200:
        raise HTTPException(409, "Template listing limit reached")
    return [TemplateSummary.model_validate(row) for row in rows]


def detail(db: Session, org_id: str, template_id: str) -> TemplateDetail:
    template = _template(db, org_id, template_id)
    versions = db.query(PromptVersion).filter_by(
        organization_id=org_id, template_id=template_id,
    ).order_by(PromptVersion.version.desc()).limit(201).all()
    if len(versions) > 200:
        raise HTTPException(409, "Version listing limit reached")
    logs = db.query(AuditLog).filter_by(
        organization_id=org_id, entity_type="prompt_template", entity_id=template_id,
    ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(200).all()
    return TemplateDetail(
        **TemplateSummary.model_validate(template).model_dump(),
        versions=[VersionRead.model_validate(row) for row in versions],
        history=[HistoryRead(
            id=row.id, action=row.action, version=json.loads(row.new_values or "{}").get("version", 0),
            actor_id=row.actor_id, created_at=row.created_at,
        ) for row in logs],
    )


def create_template(db: Session, org_id: str, actor_id: str, payload: TemplateCreate) -> TemplateDetail:
    template = PromptTemplate(
        id=str(uuid4()), organization_id=org_id, key=payload.key, name=payload.name, workflow=payload.workflow,
        description=payload.description, created_by=actor_id,
    )
    version = PromptVersion(
        organization_id=org_id, template_id=template.id, version=1,
        body=payload.body, variables=payload.variables, checksum=_digest(payload.body, payload.variables),
        created_by=actor_id,
    )
    db.add_all([template, version])
    log_change(db, "prompt_template", template.id, "create", actor_id=actor_id,
               new_values={"version": 1, "key": payload.key, "checksum": version.checksum}, organization_id=org_id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Prompt key already exists") from exc
    return detail(db, org_id, template.id)


def create_version(db: Session, org_id: str, actor_id: str, template_id: str, payload: VersionCreate) -> TemplateDetail:
    _template(db, org_id, template_id, lock=True)
    latest = db.query(func.max(PromptVersion.version)).filter_by(
        organization_id=org_id, template_id=template_id,
    ).scalar() or 0
    if latest >= 200:
        raise HTTPException(409, "Version limit reached")
    version = PromptVersion(
        organization_id=org_id, template_id=template_id, version=latest + 1,
        body=payload.body, variables=payload.variables, checksum=_digest(payload.body, payload.variables),
        created_by=actor_id,
    )
    db.add(version)
    log_change(db, "prompt_template", template_id, "version_create", actor_id=actor_id,
               new_values={"version": version.version, "checksum": version.checksum}, organization_id=org_id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Concurrent version creation; retry") from exc
    return detail(db, org_id, template_id)


def activate(db: Session, org_id: str, actor_id: str, template_id: str, number: int) -> TemplateDetail:
    template = _template(db, org_id, template_id, lock=True)
    version = _version(db, org_id, template_id, number)
    if template.active_version == number:
        return detail(db, org_id, template_id)
    previous = template.active_version
    template.active_version = number
    version.activated_at = datetime.now(timezone.utc)
    log_change(db, "prompt_template", template_id, "rollback" if previous and number < previous else "activate",
               actor_id=actor_id, old_values={"version": previous},
               new_values={"version": number, "checksum": version.checksum}, organization_id=org_id)
    db.commit()
    return detail(db, org_id, template_id)


def preview(db: Session, org_id: str, template_id: str, payload: PreviewRequest) -> PreviewResponse:
    _template(db, org_id, template_id)
    version = _version(db, org_id, template_id, payload.version)
    if set(payload.values) != set(version.variables):
        raise HTTPException(422, "Preview values must match version variables exactly")
    return PreviewResponse(rendered=render(version.body, payload.values), version=version.version)
