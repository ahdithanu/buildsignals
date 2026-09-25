"""Hosting templates must not bypass the application's validated peer contract."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import Mock

import pytest
from starlette.requests import Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app import server
from app.services.rate_limiter import InMemoryRateLimiter
from app.utils.client_address import client_address


@pytest.mark.parametrize("value", [
    None, "", " ", "*", "0.0.0.0/0", "::/0", "invalid", "192.0.2.1/24", "192.0.2.1,*",
    "0.0.0.0/1,128.0.0.0/1", "::/1,8000::/1",
])
def test_production_requires_explicit_bounded_proxy_trust(value):
    env = {"ENVIRONMENT": "production"}
    if value is not None:
        env["FORWARDED_ALLOW_IPS"] = value
    with pytest.raises(ValueError):
        server.server_options(env)


def test_explicit_direct_listener_disables_forwarded_headers():
    options = server.server_options({"ENVIRONMENT": "production", "FORWARDED_ALLOW_IPS": "none"})
    assert options["proxy_headers"] is False
    assert options["forwarded_allow_ips"] == []


def test_launcher_preserves_port_workers_and_reviewed_trust(monkeypatch):
    env = {"ENVIRONMENT": "production", "FORWARDED_ALLOW_IPS": "192.0.2.0/24, 2001:db8::1", "PORT": "8123", "WEB_CONCURRENCY": "3"}
    monkeypatch.setattr(server.os, "environ", env)
    run = Mock()
    monkeypatch.setattr(server.uvicorn, "run", run)
    server.main()
    run.assert_called_once_with("app.main:app", host="0.0.0.0", port=8123, workers=3,
                                proxy_headers=True, forwarded_allow_ips=["192.0.2.0/24", "2001:db8::1"])


def test_missing_production_trust_cannot_start_listener(monkeypatch):
    monkeypatch.setattr(server.os, "environ", {"ENVIRONMENT": "production"})
    run = Mock()
    monkeypatch.setattr(server.uvicorn, "run", run)
    with pytest.raises(ValueError):
        server.main()
    run.assert_not_called()


def test_real_proxy_middleware_distinguishes_clients_and_ignores_forged_prefixes():
    budget = InMemoryRateLimiter()
    decisions = []

    async def application(scope, receive, send):
        peer = client_address(Request(scope))
        decisions.append((peer, budget.check(key=peer, limit=1, window_seconds=60, required=True).allowed))

    proxy = ProxyHeadersMiddleware(application, trusted_hosts=["192.0.2.10"])

    async def request(peer, forwarded):
        scope = {"type": "http", "client": (peer, 54321), "headers": [(b"x-forwarded-for", forwarded.encode())]}
        await proxy(scope, None, None)

    # A trusted edge appends the verified source; arbitrary earlier prefixes
    # do not determine the chosen client. Distinct actual clients stay distinct.
    asyncio.run(request("192.0.2.10", "203.0.113.99, 198.51.100.1"))
    asyncio.run(request("192.0.2.10", "203.0.113.88, 198.51.100.2"))
    asyncio.run(request("192.0.2.10", "203.0.113.77, 198.51.100.1"))
    # A direct untrusted peer cannot pick its own identity at all.
    asyncio.run(request("203.0.113.1", "198.51.100.99"))
    asyncio.run(request("203.0.113.1", "198.51.100.88"))
    assert decisions == [
        ("198.51.100.1", True), ("198.51.100.2", True), ("198.51.100.1", False),
        ("203.0.113.1", True), ("203.0.113.1", False),
    ]


def test_templates_pin_non_evicting_security_store_and_shared_launcher():
    root = Path(__file__).resolve().parents[1]
    blueprint = (root / "render.yaml").read_text()
    assert "maxmemoryPolicy: noeviction" in blueprint
    assert "allkeys-lru" not in blueprint
    assert "startCommand: python -m app.server" in blueprint
    assert "- key: FORWARDED_ALLOW_IPS\n        sync: false" in blueprint
    assert "exec python -m app.server" in (root / "docker-entrypoint.sh").read_text()
    assert (root / "Procfile").read_text().strip() == "web: python -m app.server"
