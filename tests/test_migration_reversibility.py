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

import importlib.util
import os as _os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_raw_observation_downgrade_relaxes_rls_for_occurrence_cleanup():
    migration_path = (
        _PROJECT_ROOT
        / "alembic/versions/20260809_0001_add_raw_source_record_observations.py"
    )
    spec = importlib.util.spec_from_file_location("raw_observation_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    operations: list[str] = []

    class _Batch:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def drop_constraint(self, name, **_kwargs):
            operations.append(f"drop constraint {name}")

        def create_unique_constraint(self, name, _columns):
            operations.append(f"create constraint {name}")

    class _Dialect:
        name = "postgresql"

    class _Bind:
        dialect = _Dialect()

    class _Operations:
        @staticmethod
        def get_bind():
            return _Bind()

        @staticmethod
        def execute(statement):
            operations.append(str(statement))

        @staticmethod
        def drop_index(name, **_kwargs):
            operations.append(f"drop index {name}")

        @staticmethod
        def drop_table(name):
            operations.append(f"drop table {name}")

        @staticmethod
        def batch_alter_table(_name):
            return _Batch()

    migration.op = _Operations()
    migration.downgrade()

    relax = operations.index('ALTER TABLE "parcel_facts" NO FORCE ROW LEVEL SECURITY')
    cleanup = next(i for i, operation in enumerate(operations) if operation.startswith("DELETE"))
    restore = operations.index('ALTER TABLE "parcel_facts" FORCE ROW LEVEL SECURITY')
    constraint = operations.index("create constraint uq_parcel_fact_source_version")
    assert relax < cleanup < restore < constraint


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


def test_raw_observation_migration_backfills_existing_versions(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'observation-backfill.db'}"
    before = _alembic("upgrade", "20260808_0002", db_url=db_url)
    assert before.returncode == 0, before.stderr
    engine = create_engine(db_url, future=True)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO organizations (id, name, slug) "
            "VALUES ('default-org', 'Default', 'default')"
        ))
        connection.execute(text(
            "INSERT INTO ingestion_sources "
            "(id, key, name, adapter, record_type, organization_id) "
            "VALUES ('source-1', 'source-1', 'Source 1', 'csv', 'permit', 'default-org')"
        ))
        connection.execute(text(
            "INSERT INTO ingestion_runs "
            "(id, source_id, status, trigger, organization_id) "
            "VALUES ('run-1', 'source-1', 'completed', 'manual', 'default-org')"
        ))
        connection.execute(text(
            "INSERT INTO raw_source_records "
            "(id, source_id, run_id, external_record_id, record_type, content_hash, "
            "payload, received_at, organization_id) VALUES "
            "('raw-1', 'source-1', 'run-1', 'record-1', 'permit', 'hash-1', "
            "'{}', '2026-08-09 12:00:00', 'default-org')"
        ))
    engine.dispose()

    upgraded = _alembic("upgrade", "head", db_url=db_url)
    assert upgraded.returncode == 0, upgraded.stderr
    engine = create_engine(db_url, future=True)
    try:
        with engine.connect() as connection:
            backfilled = connection.execute(text(
                "SELECT count(*) FROM raw_source_record_observations o "
                "JOIN raw_source_records r ON r.id = o.raw_source_record_id "
                "WHERE o.organization_id = r.organization_id "
                "AND o.last_observed_at = r.received_at"
            )).scalar_one()
        assert backfilled == 1
    finally:
        engine.dispose()


# ── Postgres-specific reversibility ─────────────────────────────────────────
# SQLite has no first-class ENUM type (enums are VARCHAR+CHECK), so the SQLite
# round-trip above CANNOT catch a downgrade that drops tables but leaves the
# Postgres ENUM types behind — the exact bug that made re-upgrade fail with
# `type "memberrole" already exists`. This gated test runs the round-trip on a
# real Postgres and asserts the schema comes back to a truly empty state.
#
# Set TEST_POSTGRES_URL to a THROWAWAY database (it gets upgraded/downgraded
# destructively). Skipped otherwise, like tests/test_rls_postgres.py.
_PG_URL = _os.environ.get("TEST_POSTGRES_URL")


@pytest.mark.skipif(not _PG_URL, reason="TEST_POSTGRES_URL not set")
def test_postgres_round_trip_leaves_no_orphaned_enum_types():
    # Start clean, then upgrade → downgrade → upgrade. The re-upgrade is the
    # step that regresses if a downgrade forgets to DROP TYPE.
    assert _alembic("downgrade", "base", db_url=_PG_URL).returncode == 0
    assert _alembic("upgrade", "head", db_url=_PG_URL).returncode == 0
    down = _alembic("downgrade", "base", db_url=_PG_URL)
    assert down.returncode == 0, f"downgrade base failed:\n{down.stderr}"

    # At base, no user-defined ENUM types should remain.
    engine = create_engine(_PG_URL, future=True)
    try:
        with engine.connect() as conn:
            orphaned = conn.execute(
                text(
                    "select count(distinct t.typname) "
                    "from pg_type t join pg_enum e on t.oid = e.enumtypid"
                )
            ).scalar()
        assert orphaned == 0, f"{orphaned} enum type(s) left behind after downgrade"
    finally:
        engine.dispose()

    # And it rebuilds cleanly (the regression symptom was here).
    reup = _alembic("upgrade", "head", db_url=_PG_URL)
    assert reup.returncode == 0, f"re-upgrade after clean downgrade failed:\n{reup.stderr}"
