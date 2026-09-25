"""Tests for account-level lockout after repeated failed logins.

The IP-based rate limiter in PR #9 already protects against single-source
grinding. This suite covers the second layer: per-account lockout, which
catches a distributed password-spray (many IPs, one victim email).
"""
from __future__ import annotations

import pytest

from app.services.account_lockout import LOCK_WINDOW, MAX_ATTEMPTS, lockout
from app.services.rate_limiter import limiter

STRONG_PW = "CorrectHorseBattery42"


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Both the rate limiter and the lockout store are process-global —
    bleed between tests would either falsely 429 us or falsely 423 us."""
    limiter.clear()
    lockout.clear()
    # Model the trusted ASGI proxy boundary for distributed-source route tests.
    # Production code must not accept these raw headers itself.
    monkeypatch.setattr("app.routes.auth._client_ip", lambda request: request.headers.get("x-forwarded-for", "testclient"))
    yield
    limiter.clear()
    lockout.clear()


def _register(client, email="victim@example.com"):
    r = client.post("/auth/register", json={
        "email": email,
        "password": STRONG_PW,
        "full_name": "Victim",
        "organization_name": f"Org-{email}",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _bad_login(client, email, ip):
    """Bad-password login simulating a distinct source IP via XFF.

    We have to spoof X-Forwarded-For so the per-IP rate limiter doesn't
    fire first and mask the account-lockout behaviour we're testing.
    """
    return client.post(
        "/auth/login",
        json={"email": email, "password": "wrong-password"},
        headers={"X-Forwarded-For": ip},
    )


def _good_login(client, email, ip):
    return client.post(
        "/auth/login",
        json={"email": email, "password": STRONG_PW},
        headers={"X-Forwarded-For": ip},
    )


class TestAccountLockout:
    def test_locks_after_max_attempts_from_distributed_ips(self, client):
        """10 bad attempts (each from a fresh IP, so the IP limiter never
        fires) lock the account; the 11th request comes back as 423."""
        _register(client)
        for i in range(MAX_ATTEMPTS):
            r = _bad_login(client, "victim@example.com", f"10.0.0.{i+1}")
            assert r.status_code == 401, (i, r.status_code, r.text)
        # The next attempt — even with the *correct* password from a
        # *new* IP — must be refused with 423 Locked.
        locked = client.post(
            "/auth/login",
            json={"email": "victim@example.com", "password": STRONG_PW},
            headers={"X-Forwarded-For": "10.0.0.99"},
        )
        assert locked.status_code == 423
        assert locked.headers.get("Retry-After", "").isdigit()
        retry = int(locked.headers["Retry-After"])
        assert 0 < retry <= LOCK_WINDOW

    def test_successful_login_resets_counter(self, client):
        """Mistype, get it right, then mistype some more — should not
        lock since the success resets the counter."""
        _register(client)
        # 9 bad attempts (under the cap)
        for i in range(MAX_ATTEMPTS - 1):
            assert _bad_login(client, "victim@example.com", f"10.0.0.{i+1}").status_code == 401
        # Correct password succeeds and clears the counter.
        ok = _good_login(client, "victim@example.com", "10.0.0.50")
        assert ok.status_code == 200
        # Another 9 failures from fresh IPs must still be 401, not 423.
        for i in range(MAX_ATTEMPTS - 1):
            r = _bad_login(client, "victim@example.com", f"10.1.0.{i+1}")
            assert r.status_code == 401, (i, r.status_code)

    def test_independent_counters_per_email(self, client):
        """Locking out alice must not lock out bob."""
        _register(client, email="alice@example.com")
        _register(client, email="bob@example.com")
        # Lock alice from many IPs.
        for i in range(MAX_ATTEMPTS):
            assert _bad_login(client, "alice@example.com", f"10.0.0.{i+1}").status_code == 401
        # Alice is now locked.
        alice_next = client.post(
            "/auth/login",
            json={"email": "alice@example.com", "password": STRONG_PW},
            headers={"X-Forwarded-For": "10.0.0.99"},
        )
        assert alice_next.status_code == 423
        # Bob is untouched — correct password still works.
        bob_ok = _good_login(client, "bob@example.com", "10.0.0.99")
        assert bob_ok.status_code == 200

    def test_ip_rate_limit_fires_first_for_single_source(self, client):
        """Precedence check: when the attacker hammers from one IP, the
        IP-based 429 wins because that check runs before the lockout
        check in the login handler. This documents the layering."""
        _register(client)
        # Stick to one IP — LOGIN_LIMIT is 10 per email+IP.
        last = None
        for _ in range(MAX_ATTEMPTS + 1):
            last = client.post(
                "/auth/login",
                json={"email": "victim@example.com", "password": "nope"},
                headers={"X-Forwarded-For": "10.0.0.7"},
            )
        # The first check in the route is the rate limiter, so we get
        # 429 (not 423) when grinding from a single source.
        assert last.status_code == 429


# ── unit tests for the store ──────────────────────────────────────────────


class TestAccountLockoutUnit:
    def test_record_failure_returns_count(self):
        assert lockout.record_failure("u@x.com") == 1
        assert lockout.record_failure("u@x.com") == 2

    def test_is_locked_after_max(self):
        for _ in range(MAX_ATTEMPTS):
            lockout.record_failure("u@x.com")
        locked, retry = lockout.is_locked("u@x.com")
        assert locked
        assert retry > 0

    def test_email_is_case_insensitive(self):
        for _ in range(MAX_ATTEMPTS):
            lockout.record_failure("Mixed@Example.com")
        locked, _ = lockout.is_locked("mixed@example.com")
        assert locked

    def test_reset_clears_counter(self):
        for _ in range(MAX_ATTEMPTS - 1):
            lockout.record_failure("u@x.com")
        lockout.reset("u@x.com")
        # Fresh budget after reset.
        for _ in range(MAX_ATTEMPTS - 1):
            assert not lockout.is_locked("u@x.com")[0]
            lockout.record_failure("u@x.com")

    def test_distinct_emails_are_independent(self):
        for _ in range(MAX_ATTEMPTS):
            lockout.record_failure("a@x.com")
        assert lockout.is_locked("a@x.com")[0]
        assert not lockout.is_locked("b@x.com")[0]
