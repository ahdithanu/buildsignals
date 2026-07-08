"""API versioning middleware.

Routers mount at `/v1` only — that's the shape of the OpenAPI schema
and the contract new clients should follow. This middleware handles
the backward-compatibility half: it rewrites unversioned inbound paths
(`/deals`, `/auth/login`, …) to their versioned equivalent
(`/v1/deals`, `/v1/auth/login`) before dispatching, and stamps a
`Deprecation: true` + `Sunset: <date>` header on the response so clients
using the old URLs get a visible push to migrate.

Infrastructure endpoints (`/health`, `/health/deep`, `/openapi.json`,
`/docs`, `/redoc`, root) are exempt — they're not part of the versioned
API contract.

Deletion timeline: pull this middleware once every client is on /v1 and
the sunset date has passed. Grep the access logs for unversioned paths
before ripping it out.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# Bump this when the current major version changes. Kept as a module-level
# constant so grep-for-migration works.
CURRENT_API_PREFIX = "/v1"

# The date after which unversioned paths may return 410 Gone. Advertised
# on every deprecated response via the standard `Sunset` header (RFC 8594).
SUNSET_DATE = "2027-01-01"

# Paths that stay unversioned — infrastructure, not part of the versioned
# public API. Match exact or as-a-prefix (/health/ covers /health/deep).
_UNVERSIONED_PREFIXES = (
    "/health",
    "/healthz",
    "/metrics",
    "/openapi.json",
    "/docs",
    "/redoc",
    # Ad-hoc test probes registered under /__probe/* by individual tests
    # (see tests/test_request_id.py). Never part of the public API.
    "/__probe",
)


def _is_unversioned_path(path: str) -> bool:
    if path == "/" or path.startswith(CURRENT_API_PREFIX + "/") or path == CURRENT_API_PREFIX:
        return False
    return not any(
        path == p or path.startswith(p + "/") for p in _UNVERSIONED_PREFIXES
    )


class ApiVersioningMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        original_path = request.url.path

        if _is_unversioned_path(original_path):
            # Rewrite scope in-place so downstream router sees /v1/<path>.
            new_path = f"{CURRENT_API_PREFIX}{original_path}"
            request.scope["path"] = new_path
            # `raw_path` is bytes and Starlette respects it if set — keep in sync.
            request.scope["raw_path"] = new_path.encode("ascii")
            response = await call_next(request)
            # setdefault so a route that intentionally sets these keeps them.
            response.headers.setdefault("Deprecation", "true")
            response.headers.setdefault("Sunset", SUNSET_DATE)
            response.headers.setdefault(
                "Link",
                f'<{new_path}>; rel="successor-version"',
            )
            return response

        return await call_next(request)
