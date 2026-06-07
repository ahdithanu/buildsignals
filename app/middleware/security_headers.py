"""HTTP security headers middleware.

Stamps a baseline set of security headers on every response (including error
responses produced by Starlette/FastAPI before any route runs). We use
``response.headers.setdefault`` so route-level overrides win — e.g. a future
endpoint that needs a relaxed CSP can set its own header and we won't clobber
it.

The module imports ``app.config`` rather than the ``IS_PRODUCTION`` value
directly so tests can monkeypatch ``app.config.IS_PRODUCTION`` at runtime to
flip HSTS on and off without reloading the middleware.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app import config as app_config


_ALWAYS_ON_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    ),
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}

_HSTS_VALUE = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds standard HTTP security headers to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for name, value in _ALWAYS_ON_HEADERS.items():
            response.headers.setdefault(name, value)
        if app_config.IS_PRODUCTION:
            response.headers.setdefault("Strict-Transport-Security", _HSTS_VALUE)
        return response
