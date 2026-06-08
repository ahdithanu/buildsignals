"""Tests for the password-reset flow (/auth/password/forgot and /reset).

We swap the module-level email_service.send to a MagicMock so we can
assert calls and extract the reset URL the user would have received.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.config import REFRESH_COOKIE_NAME
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services import email_service as email_module
from app.services.account_lockout import lockout
from app.services.rate_limiter import limiter


STRONG_PW = "CorrectHorseBattery42"
NEW_PW = "NewStrongPass9182!"


REGISTER = {
    "email": "reset@example.com",
    "password": STRONG_PW,
    "full_name": "Reset Tester",
    "organization_name": "ResetCo",
}


@pytest.fixture(autouse=True)
def _reset_state():
    limiter.clear()
    if hasattr(lockout, "clear"):
        lockout.clear()
    yield
    limiter.clear()


@pytest.fixture()
def mock_send(monkeypatch):
    """Replace the singleton's send() with a MagicMock to capture outgoing mail."""
    # In tests RESEND_API_KEY should be unset → ConsoleEmailService.
    assert not os.environ.get("RESEND_API_KEY"), "tests must run without Resend wired"
    mock = MagicMock()
    monkeypatch.setattr(email_module.email_service, "send", mock)
    return mock


def _register(client):
    r = client.post("/auth/register", json=REGISTER)
    assert r.status_code == 201, r.text
    return r


def _extract_token(mock_call) -> str:
    """Pull the plaintext token back out of a captured send() call."""
    kwargs = mock_call.kwargs
    body = kwargs.get("text", "") + kwargs.get("html", "")
    m = re.search(r"reset-password\?token=([A-Za-z0-9_\-]+)", body)
    assert m, f"no reset URL found in email body: {body!r}"
    return m.group(1)


# ── /forgot ──────────────────────────────────────────────────────────────


def test_forgot_unknown_email_returns_204_without_sending(client, mock_send):
    r = client.post("/auth/password/forgot", json={"email": "ghost@example.com"})
    assert r.status_code == 204
    mock_send.assert_not_called()


def test_forgot_known_email_returns_204_and_sends(client, mock_send):
    _register(client)
    r = client.post("/auth/password/forgot", json={"email": REGISTER["email"]})
    assert r.status_code == 204
    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert kwargs["to"] == REGISTER["email"]
    assert "Reset your DealSignal password" in kwargs["subject"]
    assert "/reset-password?token=" in kwargs["text"]


# ── /reset ───────────────────────────────────────────────────────────────


def test_reset_with_valid_token_changes_password(client, mock_send):
    _register(client)
    client.post("/auth/password/forgot", json={"email": REGISTER["email"]})
    token = _extract_token(mock_send.call_args)

    r = client.post(
        "/auth/password/reset",
        json={"token": token, "new_password": NEW_PW},
    )
    assert r.status_code == 204, r.text

    # New password works
    client.cookies.clear()
    ok = client.post(
        "/auth/login",
        json={"email": REGISTER["email"], "password": NEW_PW},
    )
    assert ok.status_code == 200, ok.text

    # Old password no longer works
    client.cookies.clear()
    bad = client.post(
        "/auth/login",
        json={"email": REGISTER["email"], "password": STRONG_PW},
    )
    assert bad.status_code == 401


def test_reset_token_is_single_use(client, mock_send):
    _register(client)
    client.post("/auth/password/forgot", json={"email": REGISTER["email"]})
    token = _extract_token(mock_send.call_args)

    r1 = client.post(
        "/auth/password/reset",
        json={"token": token, "new_password": NEW_PW},
    )
    assert r1.status_code == 204
    r2 = client.post(
        "/auth/password/reset",
        json={"token": token, "new_password": NEW_PW + "x"},
    )
    assert r2.status_code == 400
    assert "Invalid or expired" in r2.json()["detail"]


def test_reset_with_expired_token_rejected(client, mock_send, db):
    _register(client)
    client.post("/auth/password/forgot", json={"email": REGISTER["email"]})
    token = _extract_token(mock_send.call_args)

    # Force expiry in the DB.
    row = db.query(PasswordResetToken).first()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.add(row)
    db.commit()

    r = client.post(
        "/auth/password/reset",
        json={"token": token, "new_password": NEW_PW},
    )
    assert r.status_code == 400
    assert "Invalid or expired" in r.json()["detail"]


def test_reset_with_garbage_token_rejected(client, mock_send):
    _register(client)
    r = client.post(
        "/auth/password/reset",
        json={"token": "not-a-real-token", "new_password": NEW_PW},
    )
    assert r.status_code == 400


def test_reset_with_weak_password_rejected(client, mock_send):
    _register(client)
    client.post("/auth/password/forgot", json={"email": REGISTER["email"]})
    token = _extract_token(mock_send.call_args)

    r = client.post(
        "/auth/password/reset",
        json={"token": token, "new_password": "password1234"},
    )
    assert r.status_code == 422


# ── rate limits ──────────────────────────────────────────────────────────


def test_forgot_per_ip_rate_limit(client, mock_send):
    last = None
    for _ in range(11):
        last = client.post(
            "/auth/password/forgot",
            json={"email": f"x{_}@example.com"},
        )
    assert last.status_code == 429
    assert "Retry-After" in last.headers


def test_forgot_per_email_rate_limit(client, mock_send):
    _register(client)
    last = None
    for _ in range(4):
        last = client.post(
            "/auth/password/forgot",
            json={"email": REGISTER["email"]},
        )
    assert last.status_code == 429


# ── session revocation ──────────────────────────────────────────────────


def test_reset_bumps_token_version_revoking_refresh(client, mock_send):
    r = _register(client)
    original_refresh = client.cookies.get(REFRESH_COOKIE_NAME)
    assert original_refresh

    client.post("/auth/password/forgot", json={"email": REGISTER["email"]})
    token = _extract_token(mock_send.call_args)

    reset = client.post(
        "/auth/password/reset",
        json={"token": token, "new_password": NEW_PW},
    )
    assert reset.status_code == 204

    # Re-attach the pre-reset refresh cookie and confirm it's now rejected.
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE_NAME, original_refresh, path="/auth")
    refreshed = client.post("/auth/refresh")
    assert refreshed.status_code == 401
