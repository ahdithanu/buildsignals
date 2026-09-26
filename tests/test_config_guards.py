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


# ── ENVIRONMENT validation (keystone guard) ─────────────────────────────────

def test_unknown_environment_rejected():
    # A typo like "prod" must crash loudly, not silently leave IS_PRODUCTION
    # False and disable every guard that branches on ENVIRONMENT.
    r = _import_config({"ENVIRONMENT": "prod"})
    assert r.returncode != 0
    assert "RuntimeError" in r.stderr and "ENVIRONMENT" in r.stderr


def test_ci_environment_imports_clean():
    # CI runs with ENVIRONMENT=ci (see .github/workflows/ci.yml); it must stay a
    # recognized (non-deployed) environment or the whole suite fails to import.
    r = _import_config({"ENVIRONMENT": "ci"})
    assert r.returncode == 0, r.stderr


def test_staging_rejects_explicit_anonymous():
    # Staging is a deployed environment → fail-closed. ALLOW_ANONYMOUS=true is
    # rejected (previously staging silently allowed anonymous mutations).
    r = _import_config({"ENVIRONMENT": "staging", "ALLOW_ANONYMOUS": "true"})
    assert r.returncode != 0
    assert "RuntimeError" in r.stderr and "ALLOW_ANONYMOUS" in r.stderr


def test_staging_imports_clean_and_fail_closed_by_default():
    # Without the flag, staging imports fine (prod-only guards don't apply) and
    # defaults to no anonymous access.
    r = _import_config({"ENVIRONMENT": "staging"})
    assert r.returncode == 0, r.stderr
