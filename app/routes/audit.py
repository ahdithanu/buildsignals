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

import csv
import io
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.audit_log import AuditLog
from app.models.organization_membership import MemberRole
from app.models.user import User
from app.schemas.audit import AuditLogEntry, AuditLogPage
from app.services.audit_service import log_change
from app.utils.auth_deps import require_role_strict

router = APIRouter(prefix="/audit", tags=["audit"])

# Hard cap on rows per export to prevent an admin from hosing the server
# with a multi-million-row download. Patchable in tests.
EXPORT_ROW_CAP = 50_000

# Admin-only, auth-required. Bound as `principal` on each handler so the
# guard is visible on the signature (audit-friendly) and the principal is
# available for org-scoped queries and actor stamping. Replaces the previous
# in-handler `_require_admin(db, principal=...)` call.
_admin_principal = require_role_strict(MemberRole.admin)


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
    principal: dict = Depends(_admin_principal),
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


_EXPORT_COLUMNS = [
    "created_at",
    "request_id",
    "actor_email",
    "actor_name",
    "entity_type",
    "entity_id",
    "action",
    "old_values",
    "new_values",
]


def _parse_iso(name: str, raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        # Accept trailing 'Z' as UTC.
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ISO8601 value for {name}: {raw!r}",
        )


@router.get("/export")
def export_audit_logs(
    principal: dict = Depends(_admin_principal),
    db: Session = Depends(get_db),
    format: str = Query("csv", pattern="^(csv|json)$"),
    since: Optional[str] = Query(None, description="ISO8601 lower bound on created_at (inclusive)."),
    until: Optional[str] = Query(None, description="ISO8601 upper bound on created_at (exclusive)."),
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
):
    """Download the org's audit log as CSV (streamed) or JSON.

    Admin-only, org-scoped. Bounded by EXPORT_ROW_CAP to keep a single
    request from monopolising the worker.
    """
    org_id = principal["org_id"]

    since_dt = _parse_iso("since", since)
    until_dt = _parse_iso("until", until)

    q = (
        db.query(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .filter(AuditLog.organization_id == org_id)
    )
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if action:
        q = q.filter(AuditLog.action == action)
    if actor_id:
        q = q.filter(AuditLog.actor_id == actor_id)
    if since_dt is not None:
        q = q.filter(AuditLog.created_at >= since_dt)
    if until_dt is not None:
        q = q.filter(AuditLog.created_at < until_dt)

    total = q.count()
    if total > EXPORT_ROW_CAP:
        # 413 Payload Too Large communicates "your request shape is fine but
        # the response would be huge — narrow the filters."
        raise HTTPException(
            status_code=413,
            detail=(
                f"Export would return {total} rows, exceeding the per-export "
                f"limit of {EXPORT_ROW_CAP}. Apply tighter filters "
                f"(since/until/entity_type/action/actor_id) and retry."
            ),
        )

    q = q.order_by(AuditLog.created_at.desc())

    org_short = org_id.split("-")[0] if org_id else "org"
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename_base = f"audit-{org_short}-{today}"

    # Snapshot the export action itself BEFORE streaming the response —
    # if we waited, a client disconnect could cancel the generator and we'd
    # lose the audit record of who pulled the log.
    log_change(
        db,
        "audit_log",
        "*",
        "export",
        actor_id=principal.get("user_id"),
        organization_id=org_id,
        new_values={"format": format, "row_count": total},
    )
    db.commit()

    if format == "json":
        items = []
        for log, user in q.all():
            items.append({
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "request_id": log.request_id,
                "actor_email": user.email if user else None,
                "actor_name": user.full_name if user else None,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "action": log.action,
                "old_values": _decode_json(log.old_values),
                "new_values": _decode_json(log.new_values),
            })
        return JSONResponse(
            content=items,
            headers={
                "Content-Disposition": f'attachment; filename="{filename_base}.json"',
            },
        )

    # CSV path — stream row-by-row so we never materialize the full output.
    def _rows():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(_EXPORT_COLUMNS)
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)

        # `.yield_per` lets SQLAlchemy stream rows from the cursor rather than
        # loading them all at once.
        for log, user in q.yield_per(500):
            writer.writerow([
                log.created_at.isoformat() if log.created_at else "",
                log.request_id or "",
                (user.email if user else "") or "",
                (user.full_name if user else "") or "",
                log.entity_type or "",
                log.entity_id or "",
                log.action or "",
                log.old_values or "",
                log.new_values or "",
            ])
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    return StreamingResponse(
        _rows(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename_base}.csv"',
        },
    )
