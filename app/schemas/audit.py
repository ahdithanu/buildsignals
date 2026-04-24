from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class AuditLogEntry(BaseModel):
    """One row of the audit trail as the client sees it.

    `old_values` / `new_values` are persisted as JSON strings in SQLite
    (TEXT column) — we decode them here so the frontend can read them
    as objects directly instead of double-parsing.
    """
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    entity_type: str
    entity_id: str
    action: str
    actor_id: Optional[str] = None
    actor_email: Optional[str] = None
    actor_name: Optional[str] = None
    old_values: Optional[dict[str, Any]] = None
    new_values: Optional[dict[str, Any]] = None
    request_id: Optional[str] = None
    created_at: datetime


class AuditLogPage(BaseModel):
    """Cursor-less pagination: client passes ?offset=N&limit=M.

    `total` is best-effort — cheap because audit_logs is small per org.
    If it ever gets expensive we swap to a keyset cursor keyed on
    (created_at, id) without breaking callers.
    """
    items: list[AuditLogEntry]
    total: int
    offset: int
    limit: int
