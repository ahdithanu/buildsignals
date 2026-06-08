"""End-to-end tests for TOTP-based 2FA enrollment and login enforcement.

Covers:
  - /auth/2fa/setup mints a secret + otpauth URI
  - /auth/2fa/verify with the live TOTP code flips totp_enabled
  - /auth/2fa/verify with a bad code rejects
  - login without code when 2FA is on → 401 + X-Auth-Reason: totp_required
  - login with the correct code → 200
  - /auth/2fa/disable needs password AND code
  - /auth/2fa/setup on an already-enabled user → 400
"""
from __future__ import annotations

import pyotp
import pytest

from app.models.user import User
from app.services.account_lockout import lockout
from app.services.rate_limiter import limiter


STRONG_PW = "CorrectHorseBattery42"


@pytest.fixture(autouse=True)
def _reset_state():
    """Rate limiter + lockout are process-global; bleed between tests will
    falsely 429 us or falsely 423 us."""
    limiter.clear()
    lockout.clear()
    yield
    limiter.clear()
    lockout.clear()


def _register(client, email="alice@example.com"):
    r = client.post("/auth/register", json={
        "email": email,
        "password": STRONG_PW,
        "full_name": "Alice",
        "organization_name": f"Org-{email}",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _enroll(client, token):
    """Run /setup + /verify and return the secret."""
    r = client.post("/auth/2fa/setup", headers=_auth(token))
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    code = pyotp.TOTP(secret).now()
    r = client.post("/auth/2fa/verify", headers=_auth(token), json={"code": code})
    assert r.status_code == 204, r.text
    return secret


# ── /setup ─────────────────────────────────────────────────────────────────

def test_setup_returns_secret_and_otpauth_uri(client):
    body = _register(client)
    r = client.post("/auth/2fa/setup", headers=_auth(body["access_token"]))
    assert r.status_code == 200
    data = r.json()
    assert data["secret"]
    assert data["otpauth_uri"].startswith("otpauth://totp/")
    assert "DealSignal" in data["otpauth_uri"]
    assert data["secret"] in data["otpauth_uri"]


def test_setup_when_already_enabled_returns_400(client):
    body = _register(client)
    _enroll(client, body["access_token"])
    r = client.post("/auth/2fa/setup", headers=_auth(body["access_token"]))
    assert r.status_code == 400


# ── /verify ────────────────────────────────────────────────────────────────

def test_verify_with_correct_code_enables_2fa(client, db):
    body = _register(client)
    r = client.post("/auth/2fa/setup", headers=_auth(body["access_token"]))
    secret = r.json()["secret"]
    code = pyotp.TOTP(secret).now()
    r = client.post(
        "/auth/2fa/verify",
        headers=_auth(body["access_token"]),
        json={"code": code},
    )
    assert r.status_code == 204
    user = db.query(User).filter(User.id == body["user_id"]).first()
    assert user.totp_enabled is True


def test_verify_with_wrong_code_rejects(client, db):
    body = _register(client)
    client.post("/auth/2fa/setup", headers=_auth(body["access_token"]))
    r = client.post(
        "/auth/2fa/verify",
        headers=_auth(body["access_token"]),
        json={"code": "000000"},
    )
    assert r.status_code in (400, 401)
    user = db.query(User).filter(User.id == body["user_id"]).first()
    assert user.totp_enabled is False


def test_verify_without_setup_returns_400(client):
    body = _register(client)
    r = client.post(
        "/auth/2fa/verify",
        headers=_auth(body["access_token"]),
        json={"code": "123456"},
    )
    assert r.status_code == 400


# ── login enforcement ─────────────────────────────────────────────────────

def test_login_without_code_when_2fa_enabled_returns_totp_required(client):
    body = _register(client, email="bob@example.com")
    _enroll(client, body["access_token"])
    r = client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": STRONG_PW},
    )
    assert r.status_code == 401
    assert r.headers.get("X-Auth-Reason") == "totp_required"


def test_login_with_correct_code_when_2fa_enabled_succeeds(client):
    body = _register(client, email="carol@example.com")
    secret = _enroll(client, body["access_token"])
    code = pyotp.TOTP(secret).now()
    r = client.post(
        "/auth/login",
        json={
            "email": "carol@example.com",
            "password": STRONG_PW,
            "totp_code": code,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]


def test_login_with_invalid_code_when_2fa_enabled_returns_totp_invalid(client):
    body = _register(client, email="dave@example.com")
    _enroll(client, body["access_token"])
    r = client.post(
        "/auth/login",
        json={
            "email": "dave@example.com",
            "password": STRONG_PW,
            "totp_code": "000000",
        },
    )
    assert r.status_code == 401
    assert r.headers.get("X-Auth-Reason") == "totp_invalid"


def test_login_without_code_when_2fa_disabled_still_works(client):
    """Sanity: existing users (no 2FA) keep their old login flow."""
    _register(client, email="eve@example.com")
    r = client.post(
        "/auth/login",
        json={"email": "eve@example.com", "password": STRONG_PW},
    )
    assert r.status_code == 200


# ── /disable ───────────────────────────────────────────────────────────────

def test_disable_with_password_only_returns_401(client):
    body = _register(client, email="frank@example.com")
    _enroll(client, body["access_token"])
    r = client.post(
        "/auth/2fa/disable",
        headers=_auth(body["access_token"]),
        json={"password": STRONG_PW, "code": "000000"},
    )
    assert r.status_code == 401


def test_disable_with_wrong_password_returns_401(client):
    body = _register(client, email="grace@example.com")
    secret = _enroll(client, body["access_token"])
    code = pyotp.TOTP(secret).now()
    r = client.post(
        "/auth/2fa/disable",
        headers=_auth(body["access_token"]),
        json={"password": "wrong-password", "code": code},
    )
    assert r.status_code == 401


def test_disable_with_password_and_valid_code_succeeds(client, db):
    body = _register(client, email="heidi@example.com")
    secret = _enroll(client, body["access_token"])
    code = pyotp.TOTP(secret).now()
    r = client.post(
        "/auth/2fa/disable",
        headers=_auth(body["access_token"]),
        json={"password": STRONG_PW, "code": code},
    )
    assert r.status_code == 204
    user = db.query(User).filter(User.id == body["user_id"]).first()
    assert user.totp_enabled is False
    assert user.totp_secret is None
