"""Production fail-fast config guards.

app/config.py evaluates its guards at import time, so each case runs in a
fresh subprocess with a controlled environment. These lock in the behavior
that a misconfigured production deploy crashes loudly (with a clear
RuntimeError) instead of booting insecurely — or, as one bug did, dying with
a confusing NameError.
"""
from __future__ import annotations

import subprocess
import sys


def _import_config(env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", "import app.config"],
        env={"PATH": __import__("os").environ.get("PATH", ""), **env},
        capture_output=True,
        text=True,
        timeout=30,
    )


_PROD_BASE = {
    "ENVIRONMENT": "production",
    "SECRET_KEY": "a-strong-production-secret-key-over-32-chars",
    "DATABASE_URL": "postgresql://u:p@host:5432/db",
    "CORS_ALLOWED_ORIGINS": "https://app.example.com",
}


def test_valid_production_config_imports_clean():
    r = _import_config(_PROD_BASE)
    assert r.returncode == 0, r.stderr


def test_samesite_none_without_secure_raises_runtimeerror():
    # Regression: REFRESH_COOKIE_SECURE was USED in this guard before it was
    # DEFINED, so this path raised NameError instead of the intended error.
    r = _import_config({
        **_PROD_BASE,
        "REFRESH_COOKIE_SAMESITE": "none",
        "REFRESH_COOKIE_SECURE": "false",
    })
    assert r.returncode != 0
    assert "RuntimeError" in r.stderr
    assert "NameError" not in r.stderr
    assert "SAMESITE" in r.stderr.upper() or "samesite" in r.stderr


def test_dev_secret_key_rejected_in_production():
    r = _import_config({**_PROD_BASE, "SECRET_KEY": "dev-secret-change-in-production"})
    assert r.returncode != 0
    assert "RuntimeError" in r.stderr and "SECRET_KEY" in r.stderr


def test_sqlite_rejected_in_production():
    r = _import_config({**_PROD_BASE, "DATABASE_URL": "sqlite:///./x.db"})
    assert r.returncode != 0
    assert "RuntimeError" in r.stderr and "PostgreSQL" in r.stderr


def test_wildcard_cors_rejected_in_production():
    r = _import_config({**_PROD_BASE, "CORS_ALLOWED_ORIGINS": "*"})
    assert r.returncode != 0
    assert "RuntimeError" in r.stderr
