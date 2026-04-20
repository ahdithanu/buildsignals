from __future__ import annotations

import json
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def log_change(
    db: Session,
    entity_type: str,
    entity_id: str,
    action: str,
    *,
    actor_id: Optional[str] = None,
    old_values: Optional[dict] = None,
    new_values: Optional[dict] = None,
    organization_id: str = "default-org",
    request_id: Optional[str] = None,
) -> AuditLog:
    """Create an audit log entry. Does NOT call db.commit() — caller is responsible.

    actor_id should be a valid User.id or None for system-generated actions.
    """
    entry = AuditLog(
        organization_id=organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        old_values=json.dumps(old_values) if old_values else None,
        new_values=json.dumps(new_values) if new_values else None,
        request_id=request_id,
    )
    db.add(entry)
    return entry


def snapshot_fields(obj, fields: List[str]) -> dict:
    """Take a snapshot of specific fields from an ORM object for audit logging."""
    result = {}
    for f in fields:
        val = getattr(obj, f, None)
        if hasattr(val, 'value'):  # Handle enums
            val = val.value
        elif hasattr(val, 'isoformat'):  # Handle datetimes
            val = val.isoformat()
        result[f] = val
    return result
