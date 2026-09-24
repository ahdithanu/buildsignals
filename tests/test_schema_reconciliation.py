"""Real migration/data round trips; never connect to the application database.

TEST_SCHEMA_RECONCILIATION_POSTGRES_URL opts into PostgreSQL using a disposable
database with PostGIS and postgis_topology already provisioned. The role must own its tables and
have CREATE SCHEMA, but must NOT be superuser/BYPASSRLS. Each test creates and
removes only a uniquely named schema. SQLite always uses pytest's tmp_path.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

from app.db import Base

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = "20260920_0001"
REVISION = "20260923_0001"
PG_URL = os.environ.get("TEST_SCHEMA_RECONCILIATION_POSTGRES_URL")
PATH = ROOT / "alembic/versions/20260923_0001_reconcile_schema.py"


def _migration():
    spec = importlib.util.spec_from_file_location("schema_reconciliation", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _alembic(url, *args, succeeds=True):
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=ROOT,
        env={**os.environ, "DATABASE_URL": url, "ENVIRONMENT": "ci",
             "SECRET_KEY": "schema-reconciliation-isolated-test-secret"},
        capture_output=True, text=True, timeout=180,
    )
    if succeeds:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode != 0, result.stdout + result.stderr
    return result


@pytest.fixture(params=["sqlite", "postgresql"])
def database(request, tmp_path):
    if request.param == "sqlite":
        url = f"sqlite:///{tmp_path / 'reconciliation.db'}"
        _alembic(url, "upgrade", PREVIOUS)
        engine = sa.create_engine(url)
        try:
            yield url, engine
        finally:
            engine.dispose()
        return
    if not PG_URL:
        pytest.skip("TEST_SCHEMA_RECONCILIATION_POSTGRES_URL not set")
    admin = sa.create_engine(PG_URL)
    schema = f"reconcile_{uuid4().hex}"
    engine = None
    try:
        with admin.begin() as connection:
            role = connection.execute(sa.text(
                "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )).one()
            assert not role.rolsuper and not role.rolbypassrls
            assert connection.execute(sa.text(
                "SELECT count(*) FROM pg_extension WHERE extname = 'postgis'"
            )).scalar_one() == 1, "Provision PostGIS before running owner-role migration tests"
            connection.execute(sa.schema.CreateSchema(schema))
            # Shadow any public Alembic version table before invoking env.py.
            connection.exec_driver_sql(
                f'CREATE TABLE "{schema}".alembic_version (version_num VARCHAR(32) PRIMARY KEY)'
            )
        url = sa.engine.make_url(PG_URL).update_query_dict({
            "options": f"-csearch_path={schema},public",
        }).render_as_string(hide_password=False)
        _alembic(url, "upgrade", PREVIOUS)
        engine = sa.create_engine(url)
        yield url, engine
    finally:
        if engine is not None:
            engine.dispose()
        with admin.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True, if_exists=True))
        admin.dispose()


def _org(connection, tenant):
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("SELECT set_config('app.current_org', :org, true)"),
                           {"org": f"org-{tenant}"})


def _seed(engine):
    """Two tenants, every rebuilt table, and children outside the revision."""
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    with engine.begin() as connection:
        for tenant in ("a", "b"):
            _org(connection, tenant)
            rows = {
                "organizations": {"name": tenant, "slug": tenant},
                "users": {"email": f"{tenant}@example.test", "full_name": tenant,
                          "password_hash": "fixture"},
                "organization_memberships": {"user_id": f"user-{tenant}"},
                "deals": {"name": tenant, "notes": "preserve historical text"},
                "contacts": {"name": tenant},
                "deal_assumptions": {"purchase_price": 123456.75},
                "deal_outputs": {"noi": 12345.5},
                "deal_distributions": {"recipient_name": tenant,
                                       "recipient_email": f"{tenant}@example.test"},
                "documents": {"filename": "evidence.pdf", "created_by": f"user-{tenant}"},
                "memos": {"content": "preserve memo", "version": 7},
                "outreach_activities": {"activity_type": "call", "contact_id": f"contacts-{tenant}"},
                "pipeline_events": {"from_stage": "new", "to_stage": "qualified"},
                "signals": {"signal_type": "permit"},
                "buy_boxes": {"user_id": f"user-{tenant}"},
                "audit_logs": {"entity_type": "deal", "entity_id": f"deal-{tenant}",
                               "action": "create", "actor_id": f"user-{tenant}"},
                "password_reset_tokens": {"user_id": f"user-{tenant}",
                                          "token_hash": tenant * 64, "expires_at": now},
                "eval_dataset": {"name": tenant, "workflow": "copilot_answer",
                                 "created_by": f"user-{tenant}"},
                "eval_case": {"dataset_id": f"eval_dataset-{tenant}", "name": tenant,
                              "input_json": {"question": tenant}, "expected_output": {}},
                "ingestion_sources": {"key": tenant, "name": tenant, "adapter": "csv",
                                      "record_type": "permit"},
                "ingestion_runs": {"source_id": f"ingestion_sources-{tenant}",
                                   "status": "completed", "trigger": "manual"},
                "raw_source_records": {"source_id": f"ingestion_sources-{tenant}",
                                       "run_id": f"ingestion_runs-{tenant}",
                                       "external_record_id": tenant, "record_type": "permit",
                                       "content_hash": tenant * 64, "payload": {"original": tenant}},
            }
            for name, values in rows.items():
                table = Base.metadata.tables[name]
                prefix = {"organizations": "org", "users": "user", "deals": "deal"}.get(name, name)
                values = dict(values, id=f"{prefix}-{tenant}")
                if "organization_id" in table.c:
                    values["organization_id"] = f"org-{tenant}"
                if "deal_id" in table.c:
                    values["deal_id"] = f"deal-{tenant}"
                for column in table.c:
                    if isinstance(column.type, sa.DateTime) and not column.nullable:
                        values.setdefault(column.name, now)
                connection.execute(table.insert().values(**values))


def _snapshot(engine):
    result = {}
    with engine.begin() as connection:
        for tenant in ("a", "b"):
            _org(connection, tenant)
            for name, table in Base.metadata.tables.items():
                # Explicit model columns exclude PostGIS's generated centroid.
                statement = sa.select(table).order_by(*table.primary_key.columns)
                if "organization_id" in table.c:
                    statement = statement.where(table.c.organization_id == f"org-{tenant}")
                result[tenant, name] = connection.execute(statement).all()
    return result


def _assert_parity(url):
    assert "No new upgrade operations detected" in _alembic(url, "check").stdout


def _schema(engine):
    def stable(items):
        return sorted(json.dumps(item, sort_keys=True, default=str) for item in items)

    with engine.connect() as connection:
        inspector = sa.inspect(connection)
        result = {"tables": sorted(inspector.get_table_names())}
        for table in Base.metadata.tables:
            result[table] = (
                [(c["name"], str(c["type"]), c["nullable"], c["default"])
                 for c in inspector.get_columns(table)],
                stable(inspector.get_indexes(table)), stable(inspector.get_unique_constraints(table)),
                stable(inspector.get_foreign_keys(table)), stable(inspector.get_check_constraints(table)),
            )
        if connection.dialect.name == "postgresql":
            result["rls"] = connection.execute(sa.text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relnamespace = current_schema()::regnamespace AND relkind='r' ORDER BY relname"
            )).all()
            result["policies"] = connection.execute(sa.text(
                "SELECT * FROM pg_policies WHERE schemaname = current_schema() ORDER BY tablename, policyname"
            )).all()
            result["enums"] = inspector.get_enums()
        else:
            result["triggers"] = connection.exec_driver_sql(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger' ORDER BY name"
            ).all()
        return result


def test_fresh_head_has_no_model_drift(database):
    url, engine = database
    _alembic(url, "upgrade", "head")
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == REVISION
    _assert_parity(url)


def test_populated_upgrade_downgrade_reupgrade_preserves_every_row(database):
    url, engine = database
    _seed(engine)
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TRIGGER preserve_user_guard BEFORE UPDATE OF full_name ON users "
                "WHEN NEW.full_name='blocked' BEGIN SELECT RAISE(ABORT, 'user guard'); END"
            )
    original = _snapshot(engine)
    schema = _schema(engine)
    _alembic(url, "upgrade", "head")
    assert _snapshot(engine) == original
    _assert_parity(url)
    upgraded = _schema(engine)
    for key in ("rls", "policies", "enums", "triggers"):
        if key in schema:
            assert upgraded[key] == schema[key]
    _alembic(url, "downgrade", PREVIOUS)
    assert _snapshot(engine) == original
    assert _schema(engine) == schema
    _alembic(url, "upgrade", "head")
    assert _snapshot(engine) == original
    _assert_parity(url)
    with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        else:
            assert connection.exec_driver_sql("SELECT count(*) FROM contacts").scalar_one() == 0
        _org(connection, "a")
        if connection.dialect.name == "postgresql":
            assert connection.exec_driver_sql("SELECT count(*) FROM contacts").scalar_one() == 1
        for table, columns in _migration().REQUIRED.items():
            for column in columns:
                with pytest.raises(IntegrityError), connection.begin_nested():
                    connection.execute(sa.text(f'UPDATE "{table}" SET "{column}"=NULL'))
        for table, column, _ in _migration().UNIQUE:
            duplicate = {"email": "b@example.test", "slug": "b", "token_hash": "b" * 64}[column]
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(sa.text(
                    f'UPDATE "{table}" SET "{column}"=:value WHERE id LIKE :id'
                ), {"value": duplicate, "id": "%-a"})
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(sa.text("UPDATE contacts SET deal_id='missing-parent'"))
        _org(connection, "a")
        with pytest.raises(sa.exc.DBAPIError, match="raw_source_records are immutable"):
            connection.execute(sa.text("UPDATE raw_source_records SET payload='{}'"))


def test_all_null_preflights_fail_without_data_or_schema_changes(database):
    url, engine = database
    _seed(engine)
    migration = _migration()
    with engine.begin() as connection:
        # Only tenant b has bad rows. Missing app.current_org must not hide them.
        _org(connection, "b")
        for table, columns in migration.REQUIRED.items():
            assignment = ", ".join(f'"{column}"=NULL' for column in columns)
            connection.execute(sa.text(f'UPDATE "{table}" SET {assignment} WHERE id LIKE :id'),
                               {"id": "%-b"})
    before = _snapshot(engine)
    schema = _schema(engine)
    result = _alembic(url, "upgrade", "head", succeeds=False)
    assert "Schema reconciliation preflight failed; no rows were changed" in result.stderr
    for table, columns in migration.REQUIRED.items():
        for column in columns:
            assert f"{table}.{column}: 1 NULL row(s)" in result.stderr
    assert _snapshot(engine) == before
    assert _schema(engine) == schema
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == PREVIOUS


def test_sqlite_refuses_cascading_batch_rebuild(tmp_path):
    url = f"sqlite:///{tmp_path / 'foreign-keys.db'}"
    _alembic(url, "upgrade", PREVIOUS)
    engine = sa.create_engine(url)
    try:
        _seed(engine)
        original = _snapshot(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            migration = _migration()
            migration.op = Operations(MigrationContext.configure(connection))
            with pytest.raises(RuntimeError, match="refusing batch rebuild"):
                migration.upgrade()
        assert _snapshot(engine) == original
    finally:
        engine.dispose()


def test_offline_generation_refuses_to_skip_preflight():
    migration = _migration()
    migration.op = Operations(MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True}))
    with pytest.raises(RuntimeError, match="requires an online data preflight"):
        migration.upgrade()


def test_late_ddl_failure_rolls_back_rebuilds_and_rls(database, monkeypatch):
    _, engine = database
    _seed(engine)
    original = _snapshot(engine)
    schema = _schema(engine)
    migration = _migration()

    def fail(*args, **kwargs):
        raise RuntimeError("injected late DDL failure")

    with pytest.raises(RuntimeError, match="injected late DDL failure"):
        with engine.begin() as connection:
            migration.op = Operations(MigrationContext.configure(connection))
            # Batch work is complete by the first outer create_index operation.
            monkeypatch.setattr(migration.op, "create_index", fail)
            migration.upgrade()
    assert _snapshot(engine) == original
    assert _schema(engine) == schema


def test_sqlite_orphans_abort_before_rebuild(tmp_path):
    url = f"sqlite:///{tmp_path / 'orphan.db'}"
    _alembic(url, "upgrade", PREVIOUS)
    engine = sa.create_engine(url)
    try:
        _seed(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql("UPDATE contacts SET deal_id='missing-parent' WHERE id='contacts-b'")
        original = _snapshot(engine)
        schema = _schema(engine)
        result = _alembic(url, "upgrade", "head", succeeds=False)
        assert "SQLite foreign-key violations in contacts" in result.stderr
        assert _snapshot(engine) == original
        assert _schema(engine) == schema
    finally:
        engine.dispose()


def test_cli_drift_check_still_rejects_unexpected_columns(database):
    url, engine = database
    _alembic(url, "upgrade", "head")
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE parcel_records ADD COLUMN unexpected_drift INTEGER")
    result = _alembic(url, "check", succeeds=False)
    assert "unexpected_drift" in result.stdout + result.stderr


def _topology_url(database):
    url, engine = database
    with engine.connect() as connection:
        assert connection.execute(sa.text(
            "SELECT count(*) FROM pg_extension WHERE extname='postgis_topology'"
        )).scalar_one() == 1, "Provision postgis_topology before running topology drift tests"
        schema = connection.exec_driver_sql("SELECT current_schema()").scalar_one()
    return sa.engine.make_url(url).update_query_dict({
        "options": f"-csearch_path={schema},public,topology",
    }).render_as_string(hide_password=False)


@pytest.mark.parametrize("database", ["postgresql"], indirect=True)
def test_cli_check_preserves_visible_postgis_topology_relations(database):
    url = _topology_url(database)
    _alembic(url, "upgrade", "head")
    engine = sa.create_engine(url)
    try:
        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == REVISION
            # Reproduce the Docker PostGIS image: extension tables outside the
            # current schema appear in default-schema reflection as schema=None.
            visible = set(sa.inspect(connection).get_table_names())
            assert {"spatial_ref_sys", "layer", "topology"} <= visible
            for name in ("layer", "topology"):
                table = sa.Table(name, sa.MetaData(), autoload_with=connection)
                assert table.schema is None
        _assert_parity(url)
        with engine.connect() as connection:
            assert {"spatial_ref_sys", "layer", "topology"} <= set(
                sa.inspect(connection).get_table_names()
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize("database", ["postgresql"], indirect=True)
@pytest.mark.parametrize("name", ["layer", "topology", "spatial_ref_sys"])
def test_cli_check_rejects_application_tables_shadowing_postgis(database, name):
    url = _topology_url(database)
    _alembic(url, "upgrade", "head")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE TABLE "{name}" (id INTEGER PRIMARY KEY)')
            assert connection.execute(sa.text(
                "SELECT n.nspname = current_schema() FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=to_regclass(:name)"
            ), {"name": name}).scalar_one()
        result = _alembic(url, "check", succeeds=False)
        assert f"Table('{name}'" in result.stdout + result.stderr
    finally:
        engine.dispose()
