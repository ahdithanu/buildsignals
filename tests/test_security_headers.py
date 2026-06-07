"""Tests for SecurityHeadersMiddleware.

Verifies that the baseline set of security headers is stamped on every
response — including error responses produced before any route runs — and that
HSTS is gated on ``app.config.IS_PRODUCTION``.
"""

import pytest
from fastapi.testclient import TestClient

from app import config as app_config
from app.main import app


ALWAYS_ON = {
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

HSTS_VALUE = "max-age=31536000; includeSubDomains"


@pytest.fixture()
def client():
    return TestClient(app)


def test_health_has_all_always_on_headers(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    for name, value in ALWAYS_ON.items():
        assert resp.headers.get(name) == value, f"header {name} mismatch"


def test_404_has_all_always_on_headers(client):
    resp = client.get("/__nope__")
    assert resp.status_code == 404
    for name, value in ALWAYS_ON.items():
        assert resp.headers.get(name) == value, f"header {name} mismatch on 404"


def test_hsts_absent_by_default_and_present_in_production(client, monkeypatch):
    # Default (tests don't run in production) — HSTS must be absent.
    assert app_config.IS_PRODUCTION is False
    resp = client.get("/health")
    assert "Strict-Transport-Security" not in resp.headers

    # Flip the module-level flag — middleware reads it at request time.
    monkeypatch.setattr(app_config, "IS_PRODUCTION", True)
    resp = client.get("/health")
    assert resp.headers.get("Strict-Transport-Security") == HSTS_VALUE
