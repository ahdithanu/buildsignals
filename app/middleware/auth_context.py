"""Middleware that extracts JWT claims and sets a request-scoped org/user context.

Posture is governed by `ALLOW_ANONYMOUS` in app.config:

- ALLOW_ANONYMOUS=True  (dev/staging default)
    A missing Authorization header falls through without raising;
    the request continues and `get_current_context()` returns the default org +
    system user. Preserves the demo workflow and legacy tests.

- ALLOW_ANONYMOUS=False (production default)
    Any non-public path without a valid Bearer token is rejected with 401.
    Public paths are defined in `app.config.PUBLIC_PATH_PREFIXES`
    (/health, /auth/login, /auth/register, /docs, etc.).

For endpoints that require authentication *regardless* of posture, use
`Depends(get_current_user)` from `app.utils.auth_deps`, which also verifies
organization membership.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import ALLOW_ANONYMOUS, is_public_path
from app.services.demo_access import (
    demo_path_allowed,
    demo_read_only,
    is_demo_identity,
    valid_demo_claims,
)
from app.services.security import decode_access_token
from app.utils.org_scope import (
    RequestContext,
    reset_current_context,
    set_current_context,
)


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


class AuthContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # CORS preflight requests never carry application credentials. Let the
        # configured CORSMiddleware validate the origin, method, and headers.
        if request.method == "OPTIONS":
            return await call_next(request)

        token_obj = None
        demo_context = None
        has_valid_token = False
        auth_header = request.headers.get("authorization")

        if auth_header:
            parts = auth_header.split(" ", 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                claims = decode_access_token(parts[1].strip())
                if claims:
                    user_id = claims.get("sub")
                    org_id = claims.get("org_id")
                    if user_id and org_id:
                        if is_demo_identity(claims):
                            if not valid_demo_claims(claims):
                                return _unauthorized("Demo session is unavailable")
                            if not demo_path_allowed(request.method, request.url.path):
                                return JSONResponse(status_code=403, content={"detail": "Demo sessions are read-only; this endpoint is unavailable"})
                            demo_context = demo_read_only.set(True)
                        token_obj = set_current_context(
                            RequestContext(org_id=org_id, user_id=user_id)
                        )
                        has_valid_token = True

        if (
            not has_valid_token
            and not is_public_path(request.url.path)
            and (bool(auth_header) or not ALLOW_ANONYMOUS)
        ):
            # Invalid supplied credentials never downgrade to the default tenant.
            # Distinguish "token was sent but invalid" from "no token at all".
            detail = (
                "Invalid or expired authentication token"
                if auth_header
                else "Authentication required"
            )
            return _unauthorized(detail)

        try:
            response = await call_next(request)
        finally:
            if token_obj is not None:
                reset_current_context(token_obj)
            if demo_context is not None:
                demo_read_only.reset(demo_context)
        if demo_context is not None or "/auth/demo" in request.url.path:
            response.headers["Cache-Control"] = "no-store"
        return response
