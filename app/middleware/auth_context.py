"""Middleware that extracts JWT claims and sets a request-scoped org/user context.

This is intentionally PERMISSIVE: an invalid or missing Authorization header
simply falls through to the default context instead of returning 401. That
preserves the demo workflow (no login required for seeded data) while still
scoping requests by the authenticated user's org when a valid token is sent.

For endpoints that require authentication, use `Depends(get_current_user)`
from `app.utils.auth_deps`, which enforces 401 on missing/invalid tokens and
also verifies organization membership.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.services.security import decode_access_token
from app.utils.org_scope import (
    RequestContext,
    reset_current_context,
    set_current_context,
)


class AuthContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        token_obj = None
        auth_header = request.headers.get("authorization")
        if auth_header:
            parts = auth_header.split(" ", 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                claims = decode_access_token(parts[1].strip())
                if claims:
                    user_id = claims.get("sub")
                    org_id = claims.get("org_id")
                    if user_id and org_id:
                        token_obj = set_current_context(
                            RequestContext(org_id=org_id, user_id=user_id)
                        )

        try:
            response = await call_next(request)
        finally:
            if token_obj is not None:
                reset_current_context(token_obj)
        return response
