"""Tests for CORS allowlist behavior and config validation.

Covers:
- dev default includes localhost origins, excludes "*"
- production without CORS_ALLOWED_ORIGINS → startup fails
- production with "*" in list → startup fails
- runtime: disallowed Origin gets no Access-Control-Allow-Origin header
- runtime: allowed Origin is echoed back with credentials
"""
from __future__ import annotations

import importlib
import sys

import pytest


def _reload_config_and_main(monkeypatch, **env):
    """Reload app.config and app.main with the given env, return the fresh app module."""
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)

    # Drop cached modules so top-level config reads fresh env.
    for mod in list(sys.modules):
        if mod == "app.config" or mod == "app.main":
            sys.modules.pop(mod, None)

    importlib.import_module("app.config")
    return importlib.import_module("app.main")


# ── config-time assertions ────────────────────────────────────────────────


def test_dev_defaults_contain_localhost(monkeypatch):
    sys.modules.pop("app.config", None)
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    config = importlib.import_module("app.config")
    importlib.reload(config)

    assert "http://localhost:8080" in config.CORS_ALLOWED_ORIGINS
    assert "*" not in config.CORS_ALLOWED_ORIGINS


def test_production_requires_origins(monkeypatch):
    sys.modules.pop("app.config", None)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    with pytest.raises(RuntimeError, match="CORS_ALLOWED_ORIGINS must be set"):
        importlib.import_module("app.config")

    # Cleanup so later imports don't see production env.
    sys.modules.pop("app.config", None)
    monkeypatch.setenv("ENVIRONMENT", "development")


def test_production_rejects_wildcard(monkeypatch):
    sys.modules.pop("app.config", None)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.example.com,*")

    with pytest.raises(RuntimeError, match="cannot contain '\\*'"):
        importlib.import_module("app.config")

    sys.modules.pop("app.config", None)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)


def test_origins_parser_trims_and_drops_trailing_slashes(monkeypatch):
    sys.modules.pop("app.config", None)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "  https://one.example.com/ , https://two.example.com  ,, ",
    )
    config = importlib.import_module("app.config")
    importlib.reload(config)

    assert config.CORS_ALLOWED_ORIGINS == [
        "https://one.example.com",
        "https://two.example.com",
    ]

    sys.modules.pop("app.config", None)
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)


# ── runtime assertions via TestClient ────────────────────────────────────


def test_allowed_origin_receives_cors_headers(client):
    r = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:8080",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8080"
    assert r.headers.get("access-control-allow-credentials") == "true"


def test_disallowed_origin_gets_no_allow_header(client):
    r = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Starlette's CORSMiddleware omits the header entirely for unapproved origins.
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers.keys()}
