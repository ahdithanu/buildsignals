"""Middleware that extracts JWT claims and sets a request-scoped org/user context.

Posture is governed by `ALLOW_ANONYMOUS` in app.config:

- ALLOW_ANONYMOUS=True  (dev/staging default)
    A missing or invalid Authorization header falls through without raising;
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
                        token_obj = set_current_context(
                            RequestContext(org_id=org_id, user_id=user_id)
                        )
                        has_valid_token = True

        if (
            not has_valid_token
            and not ALLOW_ANONYMOUS
            and not is_public_path(request.url.path)
        ):
            # Strict mode: reject anonymous requests to protected paths.
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
        return response
