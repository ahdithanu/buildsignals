"""Tests for the refresh-cookie flow.

Covers the security-critical properties of /auth/refresh and /auth/logout:

- Login/register set an httpOnly refresh cookie scoped to /auth.
- The refresh cookie is httpOnly (no Set-Cookie without HttpOnly).
- /auth/refresh returns a new access token AND rotates the cookie.
- /auth/refresh with no cookie → 401.
- /auth/refresh with a tampered cookie → 401 and the bad cookie is cleared.
- An access token minted for Bearer-auth cannot be used as a refresh token
  (and vice versa) — the typ claim enforces separation.
- /auth/logout clears the cookie, idempotent.
"""
from __future__ import annotations

from app.config import REFRESH_COOKIE_NAME
from app.services.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)

REGISTER = {
    "email": "alice@example.com",
    "password": "hunter2hunter2",
    "full_name": "Alice",
    "organization_name": "Acme",
}


def _register(client):
    r = client.post("/auth/register", json=REGISTER)
    assert r.status_code == 201, r.text
    return r


# ── Cookie is set + has HttpOnly ──────────────────────────────────────────


def test_register_sets_httponly_refresh_cookie(client):
    r = _register(client)
    # httpx stores cookies on the client jar
    assert REFRESH_COOKIE_NAME in client.cookies

    # Inspect the raw Set-Cookie header for HttpOnly + Path.
    set_cookie = r.headers.get("set-cookie", "")
    assert REFRESH_COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/auth" in set_cookie


def test_login_sets_refresh_cookie(client):
    _register(client)
    client.cookies.clear()  # simulate fresh browser

    r = client.post(
        "/auth/login",
        json={"email": REGISTER["email"], "password": REGISTER["password"]},
    )
    assert r.status_code == 200
    assert REFRESH_COOKIE_NAME in client.cookies


# ── Refresh endpoint ──────────────────────────────────────────────────────


def test_refresh_rotates_cookie_and_issues_new_access_token(client):
    r1 = _register(client)
    original_access = r1.json()["access_token"]
    original_refresh = client.cookies.get(REFRESH_COOKIE_NAME)
    assert original_refresh is not None

    r2 = client.post("/auth/refresh")
    assert r2.status_code == 200, r2.text
    new_access = r2.json()["access_token"]
    new_refresh = client.cookies.get(REFRESH_COOKIE_NAME)

    # New access token is issued.
    assert new_access and new_access != original_access
    assert decode_access_token(new_access) is not None

    # Cookie is rotated.
    assert new_refresh and new_refresh != original_refresh


def test_refresh_without_cookie_returns_401(client):
    # Fresh client, never logged in — no cookie.
    r = client.post("/auth/refresh")
    assert r.status_code == 401
    assert "refresh" in r.json()["detail"].lower()


def test_refresh_with_tampered_cookie_returns_401_and_clears_it(client):
    client.cookies.set(REFRESH_COOKIE_NAME, "not.a.valid.jwt", path="/auth")
    r = client.post("/auth/refresh")
    assert r.status_code == 401

    # Server should have sent a clearing Set-Cookie.
    set_cookie = r.headers.get("set-cookie", "")
    assert REFRESH_COOKIE_NAME in set_cookie


# ── Token typ separation ──────────────────────────────────────────────────


def test_access_token_cannot_be_used_as_refresh():
    access = create_access_token(user_id="u", org_id="o")
    assert decode_refresh_token(access) is None


def test_refresh_token_cannot_be_used_as_bearer():
    refresh = create_refresh_token(user_id="u", org_id="o")
    assert decode_access_token(refresh) is None


def test_refresh_endpoint_rejects_access_token_as_cookie(client):
    access = create_access_token(user_id="u", org_id="o")
    client.cookies.set(REFRESH_COOKIE_NAME, access, path="/auth")
    r = client.post("/auth/refresh")
    assert r.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────


def test_logout_clears_the_refresh_cookie(client):
    _register(client)
    assert REFRESH_COOKIE_NAME in client.cookies

    r = client.post("/auth/logout")
    assert r.status_code == 204

    # The clearing directive should be present even if httpx's jar
    # representation is quirky — check the header directly.
    set_cookie = r.headers.get("set-cookie", "")
    assert REFRESH_COOKIE_NAME in set_cookie


def test_logout_without_session_is_idempotent(client):
    r = client.post("/auth/logout")
    assert r.status_code == 204
