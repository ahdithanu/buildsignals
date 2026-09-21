"""Execute the eval migration and FORCE RLS checks on real PostgreSQL.

Opt in with TEST_EVAL_POSTGRES_URL pointing to a disposable database owned
by a non-superuser, non-BYPASSRLS role with CREATE SCHEMA permission. This
module creates and removes only its unique schema; it needs no other app
migrations. Never point this variable at a production database.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from app.models.evaluation import EvalCase, EvalDataset, EvalMetric, EvalResult, EvalRun

POSTGRES_URL = os.environ.get("TEST_EVAL_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TEST_EVAL_POSTGRES_URL not set; real eval PostgreSQL tests are opt-in",
)
MODELS = (EvalDataset, EvalCase, EvalRun, EvalResult, EvalMetric)
TABLES = tuple(model.__table__ for model in MODELS)


def _org(connection, organization):
    connection.execute(
        sa.text("SELECT set_config('app.current_org', :org, true)"),
        {"org": organization},
    )


def _rows(tenant, suffix=""):
    tag = f"{tenant}{suffix}"
    common = {"organization_id": f"org-{tenant}"}
    return (
        dict(common, id=f"dataset-{tag}", name=f"Dataset {tag}",
             workflow="copilot_answer", created_by="author"),
        dict(common, id=f"case-{tag}", dataset_id=f"dataset-{tag}",
             name="Case", input_json={}, expected_output={}),
        dict(common, id=f"run-{tag}", dataset_id=f"dataset-{tag}",
             created_by="author", mode="replay", model="fixture",
             prompt_version="v1", status="running",
             dataset_fingerprint="a" * 64, thresholds={}),
        dict(common, id=f"result-{tag}", run_id=f"run-{tag}",
             case_id=f"case-{tag}", case_snapshot={}, status="passed",
             model="fixture", prompt_version="v1", latency_ms=1.5),
        dict(common, id=f"metric-{tag}", result_id=f"result-{tag}",
             name=f"quality-{tag}", value=1),
    )


@pytest.fixture(scope="module")
def pg_database():
    # New physical connections make the missing-GUC test genuinely unset,
    # rather than relying on a pooled session's empty custom setting.
    engine = sa.create_engine(POSTGRES_URL, poolclass=NullPool)
    schema = f"eval_rls_{uuid4().hex}"
    path = Path(__file__).resolve().parents[1] / "alembic/versions/20260920_0001_ai_evaluations.py"
    spec = importlib.util.spec_from_file_location(f"migration_{schema}", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    created = False
    try:
        with engine.begin() as connection:
            assert connection.dialect.name == "postgresql"
            role = connection.execute(sa.text(
                "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )).one()
            assert not role.rolsuper and not role.rolbypassrls, (
                "Real RLS tests require a non-superuser role without BYPASSRLS"
            )
            connection.execute(sa.schema.CreateSchema(schema))
            connection.execute(sa.text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
            connection.execute(sa.text("CREATE TABLE organizations (id VARCHAR(36) PRIMARY KEY)"))
            connection.execute(sa.text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
            connection.execute(sa.text("INSERT INTO organizations VALUES ('org-a'), ('org-b')"))
            connection.execute(sa.text("INSERT INTO users VALUES ('author')"))
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            for tenant in ("a", "b"):
                _org(connection, f"org-{tenant}")
                for table, row in zip(TABLES, _rows(tenant)):
                    connection.execute(table.insert().values(**row))
        created = True
        yield engine, schema, migration
    finally:
        try:
            if created:
                with engine.begin() as connection:
                    connection.execute(sa.schema.DropSchema(schema, cascade=True))
                with engine.connect() as connection:
                    assert connection.execute(sa.text(
                        "SELECT count(*) FROM pg_namespace WHERE nspname = :schema"
                    ), {"schema": schema}).scalar_one() == 0
        finally:
            engine.dispose()


@pytest.fixture()
def pg_connection(pg_database):
    engine, schema, _ = pg_database
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(sa.text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
            yield connection
        finally:
            transaction.rollback()


def _denied(connection, statement, sqlstate="42501"):
    with pytest.raises(DBAPIError) as error:
        with connection.begin_nested():
            connection.execute(statement)
    assert getattr(error.value.orig, "pgcode", None) == sqlstate


@pytest.mark.parametrize("table", TABLES, ids=lambda table: table.name)
def test_owner_is_subject_to_enabled_and_forced_rls(pg_connection, table):
    row = pg_connection.execute(sa.text(
        "SELECT c.relrowsecurity, c.relforcerowsecurity, "
        "c.relowner = r.oid AS owned_by_current_user, r.rolsuper, r.rolbypassrls "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_roles r ON r.rolname = current_user "
        "WHERE n.nspname = current_schema() AND c.relname = :table"
    ), {"table": table.name}).one()
    assert row.relrowsecurity and row.relforcerowsecurity and row.owned_by_current_user
    assert not row.rolsuper and not row.rolbypassrls
    policies = pg_connection.execute(sa.text(
        "SELECT policyname, cmd, roles, qual, with_check FROM pg_policies "
        "WHERE schemaname = current_schema() AND tablename = :table"
    ), {"table": table.name}).all()
    assert len(policies) == 1
    policy = policies[0]
    assert policy.policyname == "tenant_isolation" and policy.cmd == "ALL"
    assert policy.roles == ["public"]
    assert "app.current_org" in policy.qual and "app.current_org" in policy.with_check


@pytest.mark.parametrize("table", TABLES, ids=lambda table: table.name)
@pytest.mark.parametrize("context", [None, "", "default-org", "unknown-org"])
def test_missing_or_unrecognized_org_denies_reads_and_writes(pg_connection, table, context):
    assert pg_connection.execute(sa.text(
        "SELECT current_setting('app.current_org', true)"
    )).scalar_one() is None
    if context is not None:
        _org(pg_connection, context)
    assert pg_connection.execute(sa.select(table.c.id)).all() == []
    assert pg_connection.execute(table.update().values(organization_id="org-a")).rowcount == 0
    assert pg_connection.execute(table.delete()).rowcount == 0
    row = dict(_rows("a")[TABLES.index(table)], id="forbidden-insert")
    _denied(pg_connection, table.insert().values(**row))


@pytest.mark.parametrize("table", TABLES, ids=lambda table: table.name)
@pytest.mark.parametrize("tenant,other", [("a", "b"), ("b", "a")])
def test_cross_tenant_reads_updates_deletes_and_inserts_blocked(pg_connection, table, tenant, other):
    own_row = _rows(tenant)[TABLES.index(table)]
    other_row = _rows(other)[TABLES.index(table)]
    _org(pg_connection, f"org-{tenant}")
    assert pg_connection.execute(sa.select(table.c.id)).scalars().all() == [own_row["id"]]
    target = table.c.id == other_row["id"]
    assert pg_connection.execute(sa.select(table.c.id).where(target)).all() == []
    assert pg_connection.execute(table.update().where(target).values(organization_id=f"org-{tenant}")).rowcount == 0
    assert pg_connection.execute(table.delete().where(target)).rowcount == 0
    _denied(pg_connection, table.insert().values(**dict(other_row, id="cross-insert")))
    _denied(pg_connection, table.update().where(table.c.id == own_row["id"]).values(organization_id=f"org-{other}"))
    # Verify blocked writes really left the other tenant's row intact.
    _org(pg_connection, f"org-{other}")
    assert pg_connection.execute(sa.select(table.c.id)).scalars().all() == [other_row["id"]]


@pytest.mark.parametrize("tenant", ["a", "b"])
def test_same_tenant_can_insert_read_update_and_delete_all_five_tables(pg_connection, tenant):
    _org(pg_connection, f"org-{tenant}")
    rows = _rows(tenant, "-new")
    changes = ({"description": "updated"}, {"name": "updated"}, {"prompt_version": "v2"},
               {"latency_ms": 5.0}, {"value": 0.5})
    for table, row, values in zip(TABLES, rows, changes):
        pg_connection.execute(table.insert().values(**row))
        target = table.c.id == row["id"]
        assert pg_connection.execute(sa.select(table.c.organization_id).where(target)).scalar_one() == f"org-{tenant}"
        assert pg_connection.execute(table.update().where(target).values(**values)).rowcount == 1
        updated = pg_connection.execute(sa.select(table).where(target)).mappings().one()
        assert all(updated[key] == value for key, value in values.items())
    for table, row in reversed(tuple(zip(TABLES, rows))):
        assert pg_connection.execute(table.delete().where(table.c.id == row["id"])).rowcount == 1
        assert pg_connection.execute(sa.select(table.c.id).where(table.c.id == row["id"])).all() == []


@pytest.mark.parametrize("model,column,foreign_id", [
    (EvalCase, "dataset_id", "dataset-b"),
    (EvalRun, "dataset_id", "dataset-b"),
    (EvalResult, "run_id", "run-b"),
    (EvalResult, "case_id", "case-b"),
    (EvalMetric, "result_id", "result-b"),
])
def test_same_tenant_row_cannot_reference_other_tenant_parent(pg_connection, model, column, foreign_id):
    _org(pg_connection, "org-a")
    _denied(pg_connection, model.__table__.update().values(**{column: foreign_id}), "23503")


@pytest.mark.parametrize("boundary", ["commit", "rollback"])
def test_local_org_context_does_not_survive_transaction(pg_database, boundary):
    engine, schema, _ = pg_database
    with engine.connect() as connection:
        transaction = connection.begin()
        _org(connection, "org-a")
        assert connection.execute(sa.text(
            f'SELECT count(*) FROM "{schema}".eval_dataset'
        )).scalar_one() == 1
        getattr(transaction, boundary)()
        assert connection.execute(sa.text(
            "SELECT current_setting('app.current_org', true)"
        )).scalar_one() in (None, "")
        for table in TABLES:
            assert connection.execute(sa.text(
                f'SELECT count(*) FROM "{schema}"."{table.name}"'
            )).scalar_one() == 0


def test_real_postgres_migration_round_trip(pg_connection, pg_database):
    _, _, migration = pg_database
    migration.op = Operations(MigrationContext.configure(pg_connection))
    migration.downgrade()
    assert set(sa.inspect(pg_connection).get_table_names()) == {"organizations", "users"}
    migration.upgrade()
    assert set(sa.inspect(pg_connection).get_table_names()) == {"organizations", "users", *(table.name for table in TABLES)}
    for table in TABLES:
        test_owner_is_subject_to_enabled_and_forced_rls(pg_connection, table)
