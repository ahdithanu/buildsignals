"""Alembic migration reversibility.

A migration whose downgrade is missing or broken is invisible until the
night you actually need to roll back. This exercises the full round-trip
against a throwaway SQLite DB so a non-reversible migration fails in CI
instead of at 3am.

Runs alembic as a subprocess (not the in-process command API) because
alembic/env.py resolves the DB URL from app.config at import time — a
fresh process with DATABASE_URL pointed at a temp file is the clean way
to isolate it from the app's real database.

Limitation: migration 003 (Postgres row-level security) is a no-op on
SQLite, so its up/down DDL is not exercised here. That path is covered
by tests/test_rls_postgres.py when TEST_POSTGRES_URL is set.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _alembic(*args: str, db_url: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(_PROJECT_ROOT),
        env={
            "PATH": __import__("os").environ.get("PATH", ""),
            "DATABASE_URL": db_url,
            # app.config refuses to import in production without these; give
            # it dev-safe values so the subprocess boots regardless of the
            # ambient environment CI runs under.
            "SECRET_KEY": "migration-reversibility-test-secret-key-32b",
            "ENVIRONMENT": "ci",
        },
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_full_downgrade_and_reupgrade_round_trip(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'rev.db'}"

    up = _alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"upgrade head failed:\n{up.stderr}"

    # Every downgrade, all the way to an empty schema.
    down = _alembic("downgrade", "base", db_url=db_url)
    assert down.returncode == 0, f"downgrade base failed:\n{down.stderr}"

    # And the schema rebuilds cleanly from scratch afterward.
    reup = _alembic("upgrade", "head", db_url=db_url)
    assert reup.returncode == 0, f"re-upgrade head failed:\n{reup.stderr}"


def test_single_step_down_up_targets_latest_migration(tmp_path):
    """down -1 / up +1 specifically exercises the newest migration's
    reversibility — the one a PR most likely just added."""
    db_url = f"sqlite:///{tmp_path / 'rev2.db'}"

    assert _alembic("upgrade", "head", db_url=db_url).returncode == 0

    down_one = _alembic("downgrade", "-1", db_url=db_url)
    assert down_one.returncode == 0, f"downgrade -1 failed:\n{down_one.stderr}"

    up_one = _alembic("upgrade", "head", db_url=db_url)
    assert up_one.returncode == 0, f"re-upgrade failed:\n{up_one.stderr}"
