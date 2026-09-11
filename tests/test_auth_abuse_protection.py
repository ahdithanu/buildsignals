"""Required authentication budgets must never silently bypass protection."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import redis
from starlette.requests import Request

import app.routes.auth as auth
import app.routes.health as health
import app.routes.password_reset as password_reset
import app.routes.twofa as twofa
import app.services.account_lockout as account_lockout
import app.services.rate_limiter as rate_limiter
from app.models.browser_session import BrowserSession
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services.account_lockout import AccountLockout, RedisAccountLockout
from app.services.rate_limiter import (
    InMemoryRateLimiter,
    RateLimitUnavailable,
    RedisRateLimiter,
    UnavailableRateLimiter,
    redis_key,
)
from app.utils.client_address import client_address


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch):
    budget = InMemoryRateLimiter()
    lockout = AccountLockout()
    for route in (auth, password_reset, twofa):
        monkeypatch.setattr(route, "limiter", budget)
    monkeypatch.setattr(auth, "lockout", lockout)
    monkeypatch.setattr(password_reset, "lockout", lockout)


def register(client):
    response = client.post("/auth/register", json={
        "email": "abuse-test@example.com", "password": "CorrectHorseBattery42",
        "full_name": "Synthetic Security Test", "organization_name": "Synthetic Security",
    })
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("route,payload,module", [
    ("/auth/login", {"email": "abuse-test@example.com", "password": "CorrectHorseBattery42"}, auth),
    ("/auth/register", {"email": "new@example.com", "password": "CorrectHorseBattery42", "full_name": "New"}, auth),
    ("/auth/refresh", {}, auth),
    ("/auth/password/forgot", {"email": "abuse-test@example.com"}, password_reset),
    ("/auth/password/reset", {"token": "not-a-token", "new_password": "CorrectHorseBattery99"}, password_reset),
    ("/auth/2fa/verify", {"code": "000000"}, twofa),
    ("/auth/2fa/disable", {"password": "CorrectHorseBattery42", "code": "000000"}, twofa),
])
def test_missing_protection_returns_503_without_mutation(client, db, monkeypatch, route, payload, module):
    actor = register(client)
    before_users = db.query(User).count()
    before_sessions = db.query(BrowserSession).count()
    send = Mock()
    monkeypatch.setattr(password_reset, "get_email_service", send)
    monkeypatch.setattr(module, "limiter", UnavailableRateLimiter())
    response = client.post(route, json=payload, headers={"Authorization": f"Bearer {actor['access_token']}"})
    assert response.status_code == 503, response.text
    assert response.headers["Retry-After"] == "30"
    assert response.headers["Cache-Control"] == "no-store"
    assert "set-cookie" not in response.headers
    assert "temporarily unavailable" in response.json()["detail"]
    assert db.query(User).count() == before_users
    assert db.query(BrowserSession).count() == before_sessions
    assert db.query(PasswordResetToken).count() == 0
    send.assert_not_called()


@pytest.mark.parametrize("method,password", [
    ("is_locked", "CorrectHorseBattery42"),
    ("record_failure", "wrong-password"),
    ("reset", "CorrectHorseBattery42"),
])
def test_lockout_failure_cannot_issue_session(client, db, monkeypatch, method, password):
    register(client)
    before = [(row.id, row.generation) for row in db.query(BrowserSession).all()]
    monkeypatch.setattr(auth.lockout, method, Mock(side_effect=RateLimitUnavailable("secret backend URL")))
    response = client.post("/auth/login", json={"email": "abuse-test@example.com", "password": password})
    assert response.status_code == 503
    assert "secret backend" not in response.text
    assert "set-cookie" not in response.headers
    db.expire_all()
    assert [(row.id, row.generation) for row in db.query(BrowserSession).all()] == before


def test_success_does_not_reset_account_admission_budget(client, monkeypatch):
    register(client)
    monkeypatch.setattr(auth, "LOGIN_ACCOUNT_LIMIT", 2)
    for _ in range(2):
        assert client.post("/auth/login", json={"email": "abuse-test@example.com", "password": "CorrectHorseBattery42"}).status_code == 200
    response = client.post("/auth/login", json={"email": "abuse-test@example.com", "password": "CorrectHorseBattery42"})
    assert response.status_code == 429


def test_ip_budget_covers_password_spraying_across_emails(client, monkeypatch):
    monkeypatch.setattr(auth, "LOGIN_IP_LIMIT", 2)
    verify = Mock()
    monkeypatch.setattr(auth, "dummy_verify", verify)
    for index in range(2):
        assert client.post("/auth/login", json={"email": f"unknown-{index}@example.com", "password": "wrong"}).status_code == 401
    response = client.post("/auth/login", json={"email": "third@example.com", "password": "wrong"}, headers={"X-Forwarded-For": "192.0.2.99"})
    assert response.status_code == 429
    assert verify.call_count == 2


def test_account_admission_budget_survives_changed_source_address(client, monkeypatch):
    monkeypatch.setattr(auth, "LOGIN_ACCOUNT_LIMIT", 2)
    monkeypatch.setattr(auth, "_client_ip", lambda request: request.headers["x-test-trusted-peer"])
    monkeypatch.setattr(auth, "dummy_verify", Mock())
    for index in range(2):
        assert client.post("/auth/login", json={"email": "unknown@example.com", "password": "wrong"}, headers={"X-Test-Trusted-Peer": f"192.0.2.{index}"}).status_code == 401
    response = client.post("/auth/login", json={"email": "unknown@example.com", "password": "wrong"}, headers={"X-Test-Trusted-Peer": "192.0.2.99"})
    assert response.status_code == 429


@pytest.mark.parametrize("route,payload,module,limit_name", [
    ("/auth/register", {"email": "new@example.com", "password": "abcdefghijklmn", "full_name": "New"}, auth, "REGISTER_LIMIT"),
    ("/auth/password/forgot", {"email": "unknown@example.com"}, password_reset, "FORGOT_IP_LIMIT"),
    ("/auth/password/reset", {"token": "unknown", "new_password": "CorrectHorseBattery99"}, password_reset, "RESET_IP_LIMIT"),
])
def test_forged_forwarded_address_cannot_refresh_auth_budget(client, monkeypatch, route, payload, module, limit_name):
    monkeypatch.setattr(module, limit_name, 1)
    first = client.post(route, json=payload, headers={"X-Forwarded-For": "192.0.2.1"})
    assert first.status_code in (204, 400, 422)
    second = client.post(route, json=payload, headers={"X-Forwarded-For": "192.0.2.2"})
    assert second.status_code == 429


@pytest.mark.parametrize("host,expected", [("192.0.2.10", "192.0.2.10"), ("2001:0db8:0:0::1", "2001:db8::1")])
def test_client_address_uses_only_resolved_asgi_peer(host, expected):
    request = Request({"type": "http", "client": (host, 12345), "headers": [(b"x-forwarded-for", b"192.0.2.99"), (b"forwarded", b"for=192.0.2.88")]})
    assert client_address(request) == expected


@pytest.mark.parametrize("limit,window", [(0, 60), (-1, 60), (1, 0), (True, 60)])
def test_invalid_required_policy_never_disables_protection(limit, window):
    for backend in (InMemoryRateLimiter(), RedisRateLimiter("redis://127.0.0.1:1/0")):
        with pytest.raises(RateLimitUnavailable):
            backend.check(key="key", limit=limit, window_seconds=window, required=True)


def test_local_capacity_fails_closed_without_evicting_active_counters(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(rate_limiter.time, "monotonic", lambda: now[0])
    budget = InMemoryRateLimiter(max_buckets=1)
    assert budget.check(key="a", limit=1, window_seconds=60, required=True).allowed
    with pytest.raises(RateLimitUnavailable):
        budget.check(key="b", limit=1, window_seconds=60, required=True)
    assert not budget.check(key="a", limit=1, window_seconds=60, required=True).allowed
    now[0] += 61
    assert budget.check(key="b", limit=1, window_seconds=60, required=True).allowed


def test_local_concurrency_admits_exact_budget():
    budget = InMemoryRateLimiter()
    with ThreadPoolExecutor(max_workers=16) as workers:
        results = list(workers.map(lambda _: budget.check(key="account", limit=10, window_seconds=60, required=True).allowed, range(100)))
    assert sum(results) == 10


def test_local_failure_expiry_and_no_lock_extension(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(account_lockout.time, "monotonic", lambda: now[0])
    lockout = AccountLockout(max_entries=1)
    lockout.record_failure("synthetic@example.com")
    with pytest.raises(RateLimitUnavailable):
        lockout.record_failure("other@example.com")
    now[0] += account_lockout.LOCK_WINDOW + 1
    assert lockout.record_failure("synthetic@example.com") == 1
    for _ in range(account_lockout.MAX_ATTEMPTS - 1):
        lockout.record_failure("synthetic@example.com")
    now[0] += 10
    lockout.record_failure("synthetic@example.com")
    assert lockout.is_locked("synthetic@example.com") == (True, account_lockout.LOCK_WINDOW - 10)
    now[0] += account_lockout.LOCK_WINDOW
    assert lockout.is_locked("synthetic@example.com") == (False, 0)


def test_redis_failures_are_closed_only_for_required_budgets(caplog):
    backend = RedisRateLimiter("redis://127.0.0.1:1/0")
    failure = redis.ConnectionError("redis://private-user:private-password@internal-host")
    backend._client = SimpleNamespace(eval=Mock(side_effect=failure), delete=Mock(side_effect=failure))
    assert backend.check(key="ordinary", limit=10, window_seconds=60).allowed
    with pytest.raises(RateLimitUnavailable):
        backend.check(key="authentication", limit=10, window_seconds=60, required=True)
    with pytest.raises(RateLimitUnavailable):
        backend.reset("authentication", required=True)
    assert "private-password" not in caplog.text
    assert "internal-host" not in caplog.text


@pytest.mark.parametrize("result", [[1], [1, -1], [0, 50], ["bad", 50], None])
def test_invalid_redis_response_is_not_permission_to_authenticate(result):
    backend = RedisRateLimiter("redis://127.0.0.1:1/0")
    backend._client = SimpleNamespace(eval=Mock(return_value=result))
    with pytest.raises(RateLimitUnavailable):
        backend.check(key="authentication", limit=10, window_seconds=60, required=True)


def test_redis_clearing_is_disabled_and_keys_are_scoped_digests():
    for backend in (RedisRateLimiter("redis://127.0.0.1:1/0"), RedisAccountLockout("redis://127.0.0.1:1/0")):
        backend._client = Mock()
        with pytest.raises(RuntimeError):
            backend.clear()
        assert backend._client.mock_calls == []
    assert "victim@example.com" not in redis_key("rate", "login:victim@example.com")
    assert redis_key("rate", "same") != redis_key("lockout", "same")


@pytest.mark.parametrize("failure", [ImportError, ValueError])
def test_configured_broken_backend_never_falls_back(monkeypatch, failure):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(rate_limiter, "RedisRateLimiter", Mock(side_effect=failure))
    monkeypatch.setattr(account_lockout, "RedisAccountLockout", Mock(side_effect=failure))
    with pytest.raises(RateLimitUnavailable):
        rate_limiter._build_limiter().check(key="login", limit=1, window_seconds=1, required=True)
    with pytest.raises(RateLimitUnavailable):
        account_lockout._build_lockout().is_locked("synthetic@example.com")


def test_production_requires_shared_backend_but_local_development_does_not(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RateLimitUnavailable):
        rate_limiter._build_limiter().check(key="login", limit=1, window_seconds=1, required=True)
    with pytest.raises(RateLimitUnavailable):
        account_lockout._build_lockout().is_locked("synthetic@example.com")
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert isinstance(rate_limiter._build_limiter(), InMemoryRateLimiter)
    assert isinstance(account_lockout._build_lockout(), AccountLockout)


def test_readiness_distinguishes_local_mode_and_does_not_consume_login_budget(client, monkeypatch):
    monkeypatch.setattr(health, "limiter", auth.limiter)
    monkeypatch.setattr(health, "lockout", auth.lockout)
    for _ in range(5):
        response = client.get("/health/auth-protection")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "auth_protection": "local"}
        assert response.headers["Cache-Control"] == "no-store"
    assert not auth.limiter._buckets
    assert not auth.lockout._entries


@pytest.mark.parametrize("store,operation", [
    ("limiter", "check"), ("limiter", "reset"), ("lockout", "record_failure"),
    ("lockout", "is_locked"), ("lockout", "reset"),
])
def test_readiness_requires_all_authentication_store_permissions(client, monkeypatch, store, operation):
    monkeypatch.setattr(health, "limiter", auth.limiter)
    monkeypatch.setattr(health, "lockout", auth.lockout)
    monkeypatch.setattr(getattr(health, store), operation, Mock(side_effect=RateLimitUnavailable("denied")))
    response = client.get("/health/auth-protection")
    assert response.status_code == 503
    assert response.json()["auth_protection"] == "unavailable"
    assert response.headers["Cache-Control"] == "no-store"


def test_unavailable_auth_readiness_does_not_fail_liveness_or_logout(client, monkeypatch):
    actor = register(client)
    monkeypatch.setattr(health, "limiter", UnavailableRateLimiter())
    monkeypatch.setattr(auth, "limiter", UnavailableRateLimiter())
    response = client.get("/health/auth-protection")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "auth_protection": "unavailable"}
    assert client.get("/health").status_code == 200
    response = client.post("/auth/logout", headers={"Authorization": f"Bearer {actor['access_token']}"})
    assert response.status_code == 204
