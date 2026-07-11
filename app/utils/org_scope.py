from __future__ import annotations

"""Organization scoping, soft-delete filtering, and auth context helpers.

The `get_current_context` dependency provides the org_id and user_id
for every request. During the demo/migration phase, it falls back to
the default org and system user. Once JWT auth is wired in, the
`get_current_context` function will resolve from the token instead.
"""

from contextvars import ContextVar
from typing import NamedTuple, Optional

from sqlalchemy.orm import Query

DEFAULT_ORG_ID = "default-org"
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"


class RequestContext(NamedTuple):
    """Immutable auth context for a single request."""
    org_id: str
    user_id: str


# Per-request context set by AuthContextMiddleware (app/middleware/auth_context.py).
# Unauthenticated requests fall back to the default org + system user, which
# preserves backward compatibility with the demo flow and existing tests.
_current_context: ContextVar[Optional[RequestContext]] = ContextVar(
    "dealsignal_request_context", default=None,
)


def set_current_context(ctx: Optional[RequestContext]) -> object:
    """Set the current request context. Returns a token for resetting."""
    return _current_context.set(ctx)


def reset_current_context(token: object) -> None:
    """Reset the context back to a previous state (for cleanup)."""
    _current_context.reset(token)  # type: ignore[arg-type]


def get_current_context() -> RequestContext:
    """Return the current request's org + user context.

    Resolves from the ContextVar set by AuthContextMiddleware. Falls back to
    the default org and system user when no token is present (demo mode).
    """
    ctx = _current_context.get()
    if ctx is not None:
        return ctx
    return RequestContext(org_id=DEFAULT_ORG_ID, user_id=SYSTEM_USER_ID)


# ── Backward-compatible convenience wrappers ───────────────────────────────

def get_org_id() -> str:
    """Get the current organization ID (backward compat wrapper)."""
    return get_current_context().org_id


def get_user_id() -> str:
    """Get the current user ID."""
    return get_current_context().user_id


# ── Query helpers ──────────────────────────────────────────────────────────

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
