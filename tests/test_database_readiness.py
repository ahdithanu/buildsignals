"""Public readiness against disposable schema-only SQLite databases."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import OperationalError

from app.db import Base
from app.services import database_readiness as readiness


@pytest.fixture()
def ready_db(db):
    # Test-only version metadata: never run migrations or touch the app database.
    heads = readiness._expected_heads(readiness._ALEMBIC_CONFIG)
    with db.get_bind().begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        for head in heads:
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
                {"head": head},
            )
    return db


def _assert_not_ready(response):
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert response.headers["cache-control"] == "no-store"


def test_ready_schema_is_public_even_with_strict_auth(client, ready_db, monkeypatch):
    monkeypatch.setattr("app.middleware.auth_context.ALLOW_ANONYMOUS", False)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert response.headers["cache-control"] == "no-store"
    assert "deprecation" not in response.headers
    assert client.get("/v1/deals").status_code == 401


@pytest.mark.parametrize("table_name", [
    "planning_records", "planning_company_matches", "deals", "organizations",
])
def test_missing_mapped_table_fails_despite_select_one(client, ready_db, table_name):
    with ready_db.get_bind().begin() as connection:
        connection.execute(text(f'DROP TABLE "{table_name}"'))
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/deep").json() == {"status": "ok", "db": "ok"}
    _assert_not_ready(client.get("/health/ready"))
    assert not inspect(ready_db.get_bind()).has_table(table_name)


@pytest.mark.parametrize(("table_name", "column_name"), [
    ("planning_records", "title"),
    ("planning_company_matches", "confidence"),
    ("deals", "name"),
])
def test_stale_mapped_columns_fail(client, ready_db, table_name, column_name):
    with ready_db.get_bind().begin() as connection:
        connection.execute(text(
            f'ALTER TABLE "{table_name}" RENAME COLUMN "{column_name}" TO stale_column'
        ))
    _assert_not_ready(client.get("/health/ready"))


@pytest.mark.parametrize("revision", ["001", "unknown-or-newer-revision", None])
def test_pending_unknown_or_empty_revision_fails(client, ready_db, revision):
    with ready_db.get_bind().begin() as connection:
        connection.execute(text("DELETE FROM alembic_version"))
        if revision is not None:
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                {"revision": revision},
            )
    _assert_not_ready(client.get("/health/ready"))


def test_missing_version_table_fails_without_creating_it(client, db):
    _assert_not_ready(client.get("/health/ready"))
    assert not inspect(db.get_bind()).has_table("alembic_version")


def test_extra_revision_rows_fail(client, ready_db):
    with ready_db.get_bind().begin() as connection:
        connection.execute(text(
            "INSERT INTO alembic_version SELECT version_num FROM alembic_version"
        ))
    _assert_not_ready(client.get("/health/ready"))


@pytest.mark.parametrize("failure", [
    OperationalError(
        "SELECT private_customer FROM planning_records", {},
        Exception("postgresql://secret:password@private-db/customer"),
    ),
    RuntimeError("private_customer postgresql://secret:password@private-db/customer"),
])
def test_connection_failure_is_sanitized(client, ready_db, failure):
    with patch.object(ready_db.get_bind(), "connect", side_effect=failure):
        _assert_not_ready(client.get("/health/ready"))


def test_query_failure_is_sanitized_and_connection_recovers(client, ready_db):
    with patch(
        "sqlalchemy.engine.Connection.execute",
        side_effect=OperationalError(
            "SELECT private_customer FROM planning_records", {},
            Exception("permission denied postgresql://secret:password@private-db/customer"),
        ),
    ):
        _assert_not_ready(client.get("/health/ready"))
    assert client.get("/health/ready").status_code == 200


def test_probe_only_resolves_schema_and_reads_bounded_version_rows(client, ready_db):
    statements = []
    commits = []
    engine = ready_db.get_bind()

    def record(_conn, _cursor, statement, parameters, _context, _many):
        statements.append((statement, parameters))

    def record_commit(_conn):
        commits.append(True)

    event.listen(engine, "before_cursor_execute", record)
    event.listen(engine, "commit", record_commit)
    try:
        with patch.object(ready_db, "flush", side_effect=AssertionError("Unexpected flush")):
            assert client.get("/health/ready").status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", record)
        event.remove(engine, "commit", record_commit)

    assert not commits
    assert len(statements) == len(Base.metadata.tables) + 1
    for statement, parameters in statements[:-1]:
        assert statement.startswith("SELECT ")
        assert "WHERE 0 = 1" in statement
        assert parameters == (0, 0)  # LIMIT 0 OFFSET 0, no application rows.
    statement, parameters = statements[-1]
    assert "FROM alembic_version" in statement
    assert parameters == (len(readiness._expected_heads(readiness._ALEMBIC_CONFIG)) + 1, 0)


def test_migration_heads_resolve_from_config_not_cwd(client, ready_db, tmp_path):
    readiness._expected_heads.cache_clear()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.chdir(tmp_path)
        assert client.get("/health/ready").status_code == 200


def test_configured_script_location_is_honored(client, ready_db, tmp_path, monkeypatch):
    config_path = tmp_path / "alembic.ini"
    config_path.write_text("[alembic]\nscript_location = missing-release-scripts\n")
    monkeypatch.setattr(readiness, "_ALEMBIC_CONFIG", config_path)
    _assert_not_ready(client.get("/health/ready"))


def test_missing_migration_config_fails_closed(client, ready_db, tmp_path, monkeypatch):
    monkeypatch.setattr(readiness, "_ALEMBIC_CONFIG", tmp_path / "missing.ini")
    _assert_not_ready(client.get("/health/ready"))


def test_budget_exhaustion_stops_before_checkout(client, ready_db):
    with (
        patch.object(readiness, "monotonic", side_effect=[0, 6]),
        patch.object(ready_db.get_bind(), "connect") as connect,
    ):
        _assert_not_ready(client.get("/health/ready"))
    connect.assert_not_called()


def test_budget_exhaustion_stops_probing_and_closes_connection():
    db = MagicMock()
    connection = db.get_bind.return_value.connect.return_value.__enter__.return_value
    connection.dialect.name = "sqlite"
    with (
        patch.object(readiness, "_expected_heads", return_value=frozenset({"head"})),
        patch.object(readiness, "monotonic", side_effect=[0, 0, 0, 0, 6]),
    ):
        assert not readiness.is_database_ready(db)
    assert connection.execute.call_count == 1
    db.get_bind.return_value.connect.return_value.__exit__.assert_called_once()


def test_postgres_probe_is_read_only_and_sets_local_timeouts():
    db = MagicMock()
    connection = db.get_bind.return_value.connect.return_value.__enter__.return_value
    connection.dialect.name = "postgresql"
    connection.execute.return_value.__enter__.return_value.scalars.return_value.all.return_value = [
        "head"
    ]
    with patch.object(readiness, "_expected_heads", return_value=frozenset({"head"})):
        assert readiness.is_database_ready(db)
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert statements[:3] == [
        "SET TRANSACTION READ ONLY",
        "SET LOCAL statement_timeout = '1000ms'",
        "SET LOCAL lock_timeout = '250ms'",
    ]
    assert all(statement.startswith("SELECT ") for statement in statements[3:])
    connection.commit.assert_not_called()
    db.flush.assert_not_called()
    db.get_bind.return_value.connect.return_value.__exit__.assert_called_once()
