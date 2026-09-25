"""Global per-IP rate limit backstop.

Sits in front of route handlers, complementing per-endpoint guards in
app/services/rate_limiter.py. Auth-specific limits live at the route
level (richer keying: email+IP). This middleware just protects every-
thing else from a single client hammering the app.

Health endpoints are exempt so probes never get 429'd. Auth endpoints
are exempt because they have tighter, better-keyed limits already.
"""
from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.services.rate_limiter import limiter
from app.utils.client_address import client_address as _client_ip

GLOBAL_LIMIT = int(os.environ.get("GLOBAL_RATE_LIMIT", "600"))
GLOBAL_WINDOW = int(os.environ.get("GLOBAL_RATE_WINDOW_SECONDS", "60"))

_EXEMPT_PREFIXES = (
    "/health",
    "/healthz",
    "/metrics",
    # Auth routes are rewritten to /v1/auth/* by ApiVersioningMiddleware
    # BEFORE this middleware runs, so only the versioned forms match.
    "/v1/auth/login",
    "/v1/auth/register",
    "/v1/auth/refresh",
    "/openapi.json",
)


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        key = f"global:{_client_ip(request)}"
        decision = limiter.check(
            key=key, limit=GLOBAL_LIMIT, window_seconds=GLOBAL_WINDOW
        )
        if not decision.allowed:
            return JSONResponse(
                {"detail": "Too many requests"},
                status_code=429,
                headers={
                    "Retry-After": str(decision.retry_after),
                    "X-RateLimit-Limit": str(GLOBAL_LIMIT),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(GLOBAL_LIMIT)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        return response
