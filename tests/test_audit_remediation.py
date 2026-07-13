"""Regression tests for audit remediation fixes (M-1 timing, input bounds)."""
from __future__ import annotations

import pytest

from app.services.rate_limiter import limiter

STRONG_PW = "CorrectHorseBattery42"


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.clear()
    yield
    limiter.clear()


def _register(client, email="a@x.com", org="Acme"):
    r = client.post("/auth/register", json={
        "email": email, "password": STRONG_PW, "full_name": "A", "organization_name": org,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


# ── Input bounds (unbounded free-text fields) ───────────────────────────────

def test_deal_notes_over_limit_is_422(client):
    reg = _register(client)
    r = client.post("/deals", headers=_auth(reg["access_token"]), json={
        "name": "Deal", "notes": "x" * 10_001,
    })
    assert r.status_code == 422


def test_deal_notes_at_limit_ok(client):
    reg = _register(client)
    r = client.post("/deals", headers=_auth(reg["access_token"]), json={
        "name": "Deal", "notes": "x" * 10_000,
    })
    assert r.status_code in (200, 201), r.text


def test_signal_description_over_limit_is_422(client):
    reg = _register(client)
    r = client.post("/signals", headers=_auth(reg["access_token"]), json={
        "signal_type": "market", "description": "x" * 5_001,
    })
    assert r.status_code == 422


# ── M-1: login on a nonexistent email behaves identically to wrong password ──

def test_login_nonexistent_email_returns_generic_401(client):
    # No user registered — must still 401 with the generic message (no
    # enumeration via status/message; timing is equalized by dummy_verify).
    r = client.post("/auth/login", json={"email": "nobody@x.com", "password": "whatever"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password"


def test_login_wrong_password_same_response_as_unknown_email(client):
    _register(client, email="real@x.com")
    limiter.clear()
    unknown = client.post("/auth/login", json={"email": "ghost@x.com", "password": "nope"})
    limiter.clear()
    wrong = client.post("/auth/login", json={"email": "real@x.com", "password": "wrong-pw"})
    # Identical status + body — the only difference is timing, now equalized.
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()
