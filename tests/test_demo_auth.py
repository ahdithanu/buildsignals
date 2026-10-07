from __future__ import annotations

from app.config import REFRESH_COOKIE_NAME
from app.routes import auth as auth_routes
from app.middleware import auth_context

DEMO_USER = {
    "email": "demo@buildsignals.ai",
    "password": "LaunchSignalPass123",
    "full_name": "Build Signals Demo",
    "organization_name": "Build Signals Demo Workspace",
}


def test_demo_login_requires_explicit_enablement(client, monkeypatch):
    monkeypatch.setattr(auth_routes, "DEMO_LOGIN_ENABLED", False)
    monkeypatch.setattr(auth_routes, "DEMO_LOGIN_EMAIL", DEMO_USER["email"])
    monkeypatch.setattr(auth_routes, "DEMO_LOGIN_PASSWORD", DEMO_USER["password"])

    response = client.post("/v1/auth/demo")

    assert response.status_code == 404
    assert "not enabled" in response.json()["detail"].lower()


def test_demo_login_stays_public_when_anonymous_access_is_disabled(client, monkeypatch):
    monkeypatch.setattr(auth_context, "ALLOW_ANONYMOUS", False)
    monkeypatch.setattr(auth_routes, "DEMO_LOGIN_ENABLED", False)
    monkeypatch.setattr(auth_routes, "DEMO_LOGIN_EMAIL", DEMO_USER["email"])
    monkeypatch.setattr(auth_routes, "DEMO_LOGIN_PASSWORD", DEMO_USER["password"])

    for path in ("/auth/demo", "/v1/auth/demo"):
        response = client.post(path)
        assert response.status_code == 404
        assert "not enabled" in response.json()["detail"].lower()


def test_demo_login_issues_session_for_seeded_workspace(client, monkeypatch):
    created = client.post("/v1/auth/register", json=DEMO_USER)
    assert created.status_code == 201, created.text
    client.cookies.clear()

    monkeypatch.setattr(auth_routes, "DEMO_LOGIN_ENABLED", True)
    monkeypatch.setattr(auth_routes, "DEMO_LOGIN_EMAIL", DEMO_USER["email"])
    monkeypatch.setattr(auth_routes, "DEMO_LOGIN_PASSWORD", DEMO_USER["password"])

    response = client.post("/v1/auth/demo")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["organization_id"] == created.json()["organization_id"]
    assert REFRESH_COOKIE_NAME in client.cookies
