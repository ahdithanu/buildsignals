"""Audit-log read API.

Every mutating route calls `audit_service.log_change(...)` which writes
a row into `audit_logs`. This module exposes those rows read-only to
org admins so a pilot customer can answer "who changed what when" on
demand — a trust-builder worth shipping before any sales call.

Scoping & posture
-----------------
- Strictly org-scoped via `_require_admin_of`: a request signed for
  org-A can never read org-B's audit trail, even with a raw DB row
  id, because the filter is `organization_id == principal.org_id`.
- Admin-only. Editors/viewers don't get to audit other members.
- Read-only. There is intentionally no DELETE — tampering with your
  own audit trail is the classic red-flag pattern we're guarding
  against.

Pagination
----------
Offset-based (not cursor) for simplicity. Audit-log tables stay small
on a per-org basis (thousands of rows, not millions) so the
`OFFSET N LIMIT M` scan is fine. If a future customer scales past that,
swap in keyset pagination on (created_at DESC, id) without changing
the response envelope.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.audit_log import AuditLog
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.schemas.audit import AuditLogEntry, AuditLogPage
from app.utils.auth_deps import get_current_user

router = APIRouter(prefix="/audit", tags=["audit"])


def _require_admin(db: Session, *, principal: dict) -> None:
    """Audit visibility is admin-only inside the principal's active org."""
    m = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == principal["user_id"],
            OrganizationMembership.organization_id == principal["org_id"],
        )
        .first()
    )
    if not m:
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    if m.role != MemberRole.admin:
        raise HTTPException(status_code=403, detail="Admin role required")


def _decode_json(raw: Optional[str]) -> Optional[dict]:
    """`old_values`/`new_values` are stored as JSON strings — decode for clients."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except (json.JSONDecodeError, TypeError):
        # A row written before we standardized on JSON, or corrupted data —
        # surface it as a string rather than dropping the evidence.
        return {"raw": raw}


@router.get("", response_model=AuditLogPage)
def list_audit_logs(
    principal: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    entity_type: Optional[str] = Query(
        None, description="Filter: 'deal', 'membership', 'user', ..."
    ),
    entity_id: Optional[str] = Query(None, description="Filter to a single entity."),
    actor_id: Optional[str] = Query(None, description="Filter to changes by one user."),
    action: Optional[str] = Query(
        None, description="Filter: 'create', 'update', 'delete', 'role_change', ..."
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List audit log entries for the caller's active org.

    Most recent first. Joined with `users` so the UI can render "Alice
    deleted deal X" without a second round-trip.
    """
    _require_admin(db, principal=principal)
    org_id = principal["org_id"]

    q = db.query(AuditLog, User).outerjoin(
        User, User.id == AuditLog.actor_id
    ).filter(AuditLog.organization_id == org_id)

    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    if actor_id:
        q = q.filter(AuditLog.actor_id == actor_id)
    if action:
        q = q.filter(AuditLog.action == action)

    # Count before paginating so the UI can render "Showing 1-50 of 312".
    total = q.count()

    rows = (
        q.order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [
        AuditLogEntry(
            id=log.id,
            organization_id=log.organization_id,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            action=log.action,
            actor_id=log.actor_id,
            actor_email=user.email if user else None,
            actor_name=user.full_name if user else None,
            old_values=_decode_json(log.old_values),
            new_values=_decode_json(log.new_values),
            request_id=log.request_id,
            created_at=log.created_at,
        )
        for log, user in rows
    ]

    return AuditLogPage(items=items, total=total, offset=offset, limit=limit)
