from __future__ import annotations

"""Organization scoping and soft-delete query helpers."""

from typing import Optional

from sqlalchemy.orm import Query

DEFAULT_ORG_ID = "default-org"


def get_org_id() -> str:
    """Get the current organization ID.
    For now returns a default. Will be replaced by auth context later."""
    return DEFAULT_ORG_ID


def scope_query(query: Query, model, org_id: Optional[str] = None) -> Query:
    """Add organization_id filter to a query."""
    oid = org_id or get_org_id()
    if hasattr(model, 'organization_id'):
        query = query.filter(model.organization_id == oid)
    return query


def exclude_deleted(query: Query, model) -> Query:
    """Exclude soft-deleted records from a query."""
    if hasattr(model, 'deleted_at'):
        query = query.filter(model.deleted_at.is_(None))
    return query


def active_query(query: Query, model, org_id: Optional[str] = None) -> Query:
    """Combine org scoping and soft-delete exclusion."""
    query = scope_query(query, model, org_id)
    query = exclude_deleted(query, model)
    return query
