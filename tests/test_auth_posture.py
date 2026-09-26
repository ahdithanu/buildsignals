"""Tests for ALLOW_ANONYMOUS posture and the public-path allowlist.

Strategy: spin up an independent TestClient per test with a patched
ALLOW_ANONYMOUS value, so we can prove:

- anon request to protected path in strict mode → 401
- anon request to public path in strict mode → 200 (not 401)
- anon request in permissive mode → 200 (legacy demo behavior)
- invalid bearer token in strict mode → 401 with "invalid or expired"
- production config rejects ALLOW_ANONYMOUS=true at startup
- public_path matcher: prefix behavior, exact match, root "/"
"""
from __future__ import annotations

import importlib
import sys
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import config as app_config
from app.db import Base, get_db
from app.main import app

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def strict_client(tmp_path, monkeypatch):
    """TestClient with ALLOW_ANONYMOUS forced to False."""
    monkeypatch.setattr(app_config, "ALLOW_ANONYMOUS", False)
    # The middleware imports ALLOW_ANONYMOUS by name; patch the binding there too.
    from app.middleware import auth_context as mw

    monkeypatch.setattr(mw, "ALLOW_ANONYMOUS", False)

    db_path = str(tmp_path / f"test_{uuid.uuid4().hex[:8]}.db")
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    def _override():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    engine.dispose()


# ── is_public_path unit tests ─────────────────────────────────────────────


def test_public_path_matcher_exact_and_prefix():
    from app.config import is_public_path

    # Exact & prefix matches
    assert is_public_path("/health")
    assert is_public_path("/health/ready")
    assert is_public_path("/auth/login")
    assert is_public_path("/auth/register")
    assert is_public_path("/docs")
    assert is_public_path("/docs/oauth2-redirect")
    assert is_public_path("/openapi.json")
    assert is_public_path("/")

    # Protected paths
    assert not is_public_path("/deals")
    assert not is_public_path("/dashboard")
    assert not is_public_path("/authx")  # must not match /auth
    assert not is_public_path("/healt")  # must not match /health


# ── Middleware behaviour ──────────────────────────────────────────────────


def test_strict_unauthorized_response_allows_browser_refresh(strict_client):
    origin = app_config.CORS_ALLOWED_ORIGINS[0]
    response = strict_client.get("/v1/auth/me", headers={"Origin": origin})
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "x-request-id" in response.headers


def test_strict_unauthorized_response_does_not_allow_untrusted_origin(strict_client):
    response = strict_client.get("/v1/auth/me", headers={"Origin": "https://untrusted.invalid"})
    assert response.status_code == 401
    assert "access-control-allow-origin" not in response.headers


def test_permissive_mode_allows_anon_to_protected(client):
    """Default test fixture runs with ALLOW_ANONYMOUS=True (legacy demo)."""
    r = client.get("/dashboard/summary")
    assert r.status_code != 401, "permissive mode should not 401 on anon"


def test_strict_mode_rejects_anon_to_protected(strict_client):
    r = strict_client.get("/dashboard/summary")
    assert r.status_code == 401
    assert r.json()["detail"] == "Authentication required"
    assert r.headers.get("www-authenticate") == "Bearer"


def test_strict_mode_allows_anon_to_public(strict_client):
    r = strict_client.get("/health")
    assert r.status_code == 200


def test_strict_mode_allows_anon_to_auth_login(strict_client):
    # Login route should be reachable even without a token; payload may be
    # invalid, but it must NOT be 401 from the middleware.
    r = strict_client.post("/auth/login", json={})
    assert r.status_code != 401


def test_strict_mode_allows_cors_preflight_to_protected_path(strict_client):
    r = strict_client.options(
        "/dashboard/summary",
        headers={
            "Origin": "http://localhost:8080",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:8080"
    assert r.headers["access-control-allow-credentials"] == "true"


def test_strict_mode_rejects_invalid_bearer(strict_client):
    r = strict_client.get(
        "/dashboard/summary",
        headers={"Authorization": "Bearer totally-not-a-jwt"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid or expired authentication token"


# ── Production config guard ───────────────────────────────────────────────


def test_production_rejects_allow_anonymous_true(monkeypatch):
    sys.modules.pop("app.config", None)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS", "https://app.example.com"
    )  # satisfy CORS guard
    monkeypatch.setenv("ALLOW_ANONYMOUS", "true")

    with pytest.raises(RuntimeError, match="ALLOW_ANONYMOUS=true is not permitted"):
        importlib.import_module("app.config")

    # Cleanup so later imports return to dev config.
    sys.modules.pop("app.config", None)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("ALLOW_ANONYMOUS", raising=False)

def test_production_defaults_allow_anonymous_false(monkeypatch):
    sys.modules.pop("app.config", None)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("SECRET_KEY", "a" * 64)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.com/x")
    monkeypatch.delenv("ALLOW_ANONYMOUS", raising=False)

    config = importlib.import_module("app.config")
    importlib.reload(config)

    assert config.ALLOW_ANONYMOUS is False

    sys.modules.pop("app.config", None)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_development_defaults_allow_anonymous_true(monkeypatch):
    sys.modules.pop("app.config", None)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("ALLOW_ANONYMOUS", raising=False)

    config = importlib.import_module("app.config")
    importlib.reload(config)

    assert config.ALLOW_ANONYMOUS is True

    sys.modules.pop("app.config", None)
