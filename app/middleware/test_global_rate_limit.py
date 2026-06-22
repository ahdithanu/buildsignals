"""Global per-IP rate limit middleware."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.rate_limit import GlobalRateLimitMiddleware
from app.services.rate_limiter import limiter


@pytest.fixture()
def tiny_limit_app(monkeypatch):
    # Drop the global limit way down so we can trip it in a few requests.
    monkeypatch.setattr("app.middleware.rate_limit.GLOBAL_LIMIT", 3)
    monkeypatch.setattr("app.middleware.rate_limit.GLOBAL_WINDOW", 60)
    limiter.clear()

    app = FastAPI()
    app.add_middleware(GlobalRateLimitMiddleware)

    @app.get("/protected")
    def protected():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    yield app
    limiter.clear()


def test_returns_429_after_limit(tiny_limit_app):
    with TestClient(tiny_limit_app) as c:
        for _ in range(3):
            assert c.get("/protected").status_code == 200
        r = c.get("/protected")
        assert r.status_code == 429
        assert r.json()["detail"] == "Too many requests"
        assert int(r.headers["Retry-After"]) >= 1


def test_health_is_exempt(tiny_limit_app):
    with TestClient(tiny_limit_app) as c:
        for _ in range(10):
            assert c.get("/health").status_code == 200


def test_remaining_header_decrements(tiny_limit_app):
    with TestClient(tiny_limit_app) as c:
        r1 = c.get("/protected")
        r2 = c.get("/protected")
        assert int(r1.headers["X-RateLimit-Remaining"]) > int(
            r2.headers["X-RateLimit-Remaining"]
        )


def test_x_forwarded_for_isolates_buckets(tiny_limit_app):
    with TestClient(tiny_limit_app) as c:
        for _ in range(3):
            c.get("/protected", headers={"X-Forwarded-For": "1.1.1.1"})
        # Different IP should still have full budget.
        r = c.get("/protected", headers={"X-Forwarded-For": "2.2.2.2"})
        assert r.status_code == 200
