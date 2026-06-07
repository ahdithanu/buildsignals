"""Tests for refresh-token revocation via /auth/logout-all.

Covers:
- /auth/logout-all bumps user.token_version and clears the refresh cookie.
- A refresh cookie minted before logout-all is rejected with 401.
- A fresh login after logout-all still works (the user is not bricked).
- /auth/logout-all requires authentication.
- The pre-existing /auth/refresh happy path still rotates and issues a new
  access token (sanity check that we didn't break the non-revoked flow).
"""
from __future__ import annotations

import pytest

from app.config import REFRESH_COOKIE_NAME
from app.services.rate_limiter import limiter
from app.services.account_lockout import lockout


@pytest.fixture(autouse=True)
def _reset_throttles():
    """Refresh and login share rate-limit + lockout state across tests; clear
    both before every test so a noisy neighbour doesn't 429 us into a flake."""
    limiter.clear()
    lockout.clear() if hasattr(lockout, "clear") else None
    yield
    limiter.clear()


REGISTER = {
    "email": "revoke@example.com",
    "password": "CorrectHorseBattery42",
    "full_name": "Revoke Tester",
    "organization_name": "RevokeCo",
}


def _register(client):
    r = client.post("/auth/register", json=REGISTER)
    assert r.status_code == 201, r.text
    return r


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_logout_all_revokes_outstanding_refresh_cookie(client):
    r = _register(client)
    access = r.json()["access_token"]
    original_refresh = client.cookies.get(REFRESH_COOKIE_NAME)
    assert original_refresh is not None

    # Sanity: /auth/me works pre-revocation.
    me = client.get("/auth/me", headers=_auth_headers(access))
    assert me.status_code == 200, me.text

    # Logout-all: should return 204 and bump token_version.
    out = client.post("/auth/logout-all", headers=_auth_headers(access))
    assert out.status_code == 204, out.text

    # The clearing Set-Cookie should be present on the response.
    set_cookie = out.headers.get("set-cookie", "")
    assert REFRESH_COOKIE_NAME in set_cookie

    # The TestClient's cookie jar follows Set-Cookie semantics, but to make
    # the assertion airtight we re-attach the captured original cookie and
    # confirm /auth/refresh rejects it.
    client.cookies.set(REFRESH_COOKIE_NAME, original_refresh, path="/auth")
    refreshed = client.post("/auth/refresh")
    assert refreshed.status_code == 401
    assert "revoke" in refreshed.json()["detail"].lower()


def test_fresh_login_after_logout_all_still_works(client):
    r = _register(client)
    access = r.json()["access_token"]

    out = client.post("/auth/logout-all", headers=_auth_headers(access))
    assert out.status_code == 204

    client.cookies.clear()
    # Brand-new login mints a cookie at the new token_version → must succeed.
    login = client.post(
        "/auth/login",
        json={"email": REGISTER["email"], "password": REGISTER["password"]},
    )
    assert login.status_code == 200, login.text

    # And that fresh session can refresh just fine.
    refreshed = client.post("/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text


def test_logout_all_requires_auth(client):
    r = client.post("/auth/logout-all")
    assert r.status_code == 401


def test_refresh_still_works_when_token_version_matches(client):
    """Sanity: the version check doesn't break the normal refresh flow."""
    _register(client)
    r = client.post("/auth/refresh")
    assert r.status_code == 200, r.text
    assert r.json().get("access_token")
