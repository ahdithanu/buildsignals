"""Request-ID propagation + access logging.

Every inbound request gets a stable X-Request-ID — either the one the
client sent (so an upstream gateway / browser can correlate traces) or
a freshly minted uuid4. The ID is:

  - stored in a ContextVar so all log records inside the request pick it up
  - echoed back on the response so the client can stash it in a bug report
  - logged with method, path, status, and duration_ms when the request ends

Order matters in `app.main`: this middleware must wrap `AuthContextMiddleware`
from the outside so a 401 from auth still gets a request_id and is logged.
"""
from __future__ import annotations

import logging
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import reset_request_id, set_request_id

REQUEST_ID_HEADER = "X-Request-ID"
_MAX_CLIENT_ID_LEN = 128  # reject absurdly long client-supplied IDs

logger = logging.getLogger("dealsignal.request")


def _sanitize_incoming(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if not raw or len(raw) > _MAX_CLIENT_ID_LEN:
        return None
    # Keep it boring: letters, digits, dash, underscore, colon.
    if not all(c.isalnum() or c in "-_:." for c in raw):
        return None
    return raw


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = _sanitize_incoming(request.headers.get(REQUEST_ID_HEADER))
        request_id = incoming or uuid4().hex
        token = set_request_id(request_id)

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "request.complete",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                    "duration_ms": duration_ms,
                    "client": request.client.host if request.client else None,
                },
            )
            reset_request_id(token)
