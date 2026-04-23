"""Tests for PR #9 auth hardening: rate limiting + password policy."""
from __future__ import annotations

import pytest

from app.services.rate_limiter import limiter
from app.services.password_policy import PasswordPolicyError, validate_password


STRONG_PW = "CorrectHorseBattery42"


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Each test gets a clean rate-limit state."""
    limiter.clear()
    yield
    limiter.clear()


# ── password policy ────────────────────────────────────────────────────────


class TestPasswordPolicy:
    def test_accepts_strong_password(self):
        validate_password(STRONG_PW, email="alice@example.com")  # no raise

    @pytest.mark.parametrize("pw,reason", [
        ("short1!", "too short"),
        ("a" * 129, "too long"),
        ("123456789012345", "digits only"),
        ("abcdefghijklm", "letters only (no digit/symbol)"),
        ("password1234", "common"),
        ("alicesmith2024xy", "contains email handle"),
    ])
    def test_rejects_weak_password(self, pw, reason):
        with pytest.raises(PasswordPolicyError):
            validate_password(pw, email="alicesmith@example.com")

    def test_register_rejects_weak_password(self, client):
        r = client.post("/auth/register", json={
            "email": "bob@example.com",
            "password": "password1234",  # in common-bad list
            "full_name": "Bob",
            "organization_name": "Acme",
        })
        assert r.status_code == 422
        assert "common" in r.json()["detail"].lower()

    def test_register_accepts_strong_password(self, client):
        r = client.post("/auth/register", json={
            "email": "bob@example.com",
            "password": STRONG_PW,
            "full_name": "Bob",
            "organization_name": "Acme",
        })
        assert r.status_code == 201, r.text


# ── login rate limit ───────────────────────────────────────────────────────


class TestLoginRateLimit:
    def _register(self, client):
        assert client.post("/auth/register", json={
            "email": "carol@example.com",
            "password": STRONG_PW,
            "full_name": "Carol",
            "organization_name": "Acme",
        }).status_code == 201

    def test_grinding_wrong_password_eventually_returns_429(self, client):
        self._register(client)
        last = None
        # LOGIN_LIMIT is 10 — the 11th hit must be throttled.
        for _ in range(11):
            last = client.post("/auth/login", json={
                "email": "carol@example.com",
                "password": "nope-nope-nope",
            })
        assert last.status_code == 429
        assert last.headers.get("Retry-After", "").isdigit()

    def test_successful_login_resets_budget(self, client):
        self._register(client)
        # Burn 9 failed attempts (below limit).
        for _ in range(9):
            r = client.post("/auth/login", json={
                "email": "carol@example.com",
                "password": "nope",
            })
            assert r.status_code == 401
        # Correct password succeeds AND resets the bucket.
        ok = client.post("/auth/login", json={
            "email": "carol@example.com",
            "password": STRONG_PW,
        })
        assert ok.status_code == 200
        # After reset, another 9 failures should still be allowed (not 429).
        for _ in range(9):
            r = client.post("/auth/login", json={
                "email": "carol@example.com",
                "password": "nope",
            })
            assert r.status_code == 401

    def test_different_emails_have_independent_buckets(self, client):
        # Exhaust one email's budget.
        for _ in range(11):
            client.post("/auth/login", json={
                "email": "victim@example.com",
                "password": "nope",
            })
        # A different email from the same IP must still work.
        r = client.post("/auth/login", json={
            "email": "other@example.com",
            "password": "nope",
        })
        assert r.status_code == 401  # user doesn't exist, but NOT 429


# ── register rate limit ────────────────────────────────────────────────────


class TestRegisterRateLimit:
    def test_register_flood_returns_429(self, client):
        # REGISTER_LIMIT is 5 per IP — the 6th attempt must be throttled,
        # even before the payload is inspected.
        for i in range(5):
            client.post("/auth/register", json={
                "email": f"flood{i}@example.com",
                "password": STRONG_PW,
                "full_name": "Flood",
                "organization_name": f"F{i}",
            })
        blocked = client.post("/auth/register", json={
            "email": "flood99@example.com",
            "password": STRONG_PW,
            "full_name": "Flood",
            "organization_name": "F99",
        })
        assert blocked.status_code == 429


# ── limiter unit tests ─────────────────────────────────────────────────────


class TestRateLimiterUnit:
    def test_allows_under_limit(self):
        for _ in range(5):
            d = limiter.check(key="k", limit=5, window_seconds=60)
            assert d.allowed
        blocked = limiter.check(key="k", limit=5, window_seconds=60)
        assert not blocked.allowed
        assert blocked.retry_after > 0

    def test_reset_clears_bucket(self):
        for _ in range(5):
            limiter.check(key="k", limit=5, window_seconds=60)
        assert not limiter.check(key="k", limit=5, window_seconds=60).allowed
        limiter.reset("k")
        assert limiter.check(key="k", limit=5, window_seconds=60).allowed

    def test_keys_are_independent(self):
        for _ in range(5):
            limiter.check(key="a", limit=5, window_seconds=60)
        # `a` is full; `b` is fresh.
        assert not limiter.check(key="a", limit=5, window_seconds=60).allowed
        assert limiter.check(key="b", limit=5, window_seconds=60).allowed
