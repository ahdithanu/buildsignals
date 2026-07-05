"""Env-overridable rate-limit policy parsing.

Note: the module-level constants (LOGIN_LIMIT etc.) are read from env once
at import time — a load-test or ops environment sets the env var before the
process boots. We test the _int_env parser directly rather than reloading
the module, because reloading recreates the `limiter` singleton and would
desync it from the routes/fixtures that already imported it.
"""
from __future__ import annotations

import app.services.rate_limiter as rl


def test_int_env_parses_override(monkeypatch):
    monkeypatch.setenv("REGISTER_RATE_LIMIT", "500")
    assert rl._int_env("REGISTER_RATE_LIMIT", 5) == 500


def test_int_env_falls_back_when_unset(monkeypatch):
    monkeypatch.delenv("REGISTER_RATE_LIMIT", raising=False)
    assert rl._int_env("REGISTER_RATE_LIMIT", 5) == 5


def test_int_env_falls_back_on_garbage(monkeypatch):
    monkeypatch.setenv("REGISTER_RATE_LIMIT", "not-a-number")
    assert rl._int_env("REGISTER_RATE_LIMIT", 5) == 5


def test_int_env_ignores_whitespace_only(monkeypatch):
    monkeypatch.setenv("REGISTER_RATE_LIMIT", "   ")
    assert rl._int_env("REGISTER_RATE_LIMIT", 5) == 5


def test_defaults_are_production_safe():
    # Guard against someone fat-fingering a default up. These are the
    # documented production values.
    assert rl.LOGIN_LIMIT == 10
    assert rl.REGISTER_LIMIT == 5
    assert rl.AI_LIMIT == 30
