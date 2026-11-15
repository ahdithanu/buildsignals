"""Offline resource/order tests for the opt-in disposable PostgreSQL harness."""
import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import StatementError
from sqlalchemy.pool import NullPool

from tests import snapshot_postgres_support as support
from tests.snapshot_postgres_support import verified_snapshot_connection

_REAL_LISTEN = event.listen


@pytest.fixture(autouse=True)
def no_libpq_overrides(monkeypatch):
    for name in tuple(os.environ):
        if name.startswith("PG"):
            monkeypatch.delenv(name)

    def listen(engine, name, callback, **kwargs):
        if not isinstance(engine, Engine):
            return _REAL_LISTEN(engine, name, callback, **kwargs)
        assert name == "do_connect"
        engine.connect_guard = callback

    monkeypatch.setattr(support.event, "listen", listen)


def _target():
    run = uuid4().hex
    database = f"bs_snapshot_test_{run}"
    return f"postgresql+psycopg2://appuser:synthetic-password@127.0.0.1:55432/{database}", run


class Connection:
    def __init__(self, run, events, **identity):
        self.events = events
        self.dialect = type("Dialect", (), {"name": "postgresql"})()
        self.identity = {
            "database_name": f"bs_snapshot_test_{run}", "role_name": "appuser",
            "session_role": "appuser", "rolsuper": False, "rolbypassrls": False,
            "marker": f"BuildSignals disposable snapshot test:{run}", **identity,
        }

    @contextmanager
    def begin(self):
        self.events.append("begin")
        try:
            yield
        except Exception:
            self.events.append("rollback")
            raise
        else:
            self.events.append("end-read-only")

    def exec_driver_sql(self, sql):
        self.events.append(sql)

    def execute(self, sql):
        if getattr(self, "invalidated", False):
            self.engine.connect()
            self.invalidated = False
        assert "pg_catalog.pg_database" in str(sql)
        assert "pg_catalog.pg_roles" in str(sql)
        assert not any(word in str(sql).upper() for word in ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP"))
        self.events.append("identity-read")
        return self

    def mappings(self):
        return self

    def one(self):
        return self.identity

    def close(self):
        self.events.append("close")

    def invalidate(self):
        self.invalidated = True

    def rollback(self):
        self.events.append("body-rollback")


class Engine:
    def __init__(self, connection, events):
        self.connection, self.events = connection, events
        connection.engine = self

    def connect(self):
        if hasattr(self, "connect_guard"):
            self.connect_guard(None, None, [], {})
        self.events.append("connect")
        return self.connection

    def dispose(self):
        self.events.append("dispose")


def test_connection_is_verified_read_only_before_yield_and_owned_resources_close():
    url, run = _target()
    events, arguments = [], []
    connection = Connection(run, events)

    def factory(target, **kwargs):
        arguments.append((target, kwargs))
        return Engine(connection, events)

    with verified_snapshot_connection(url, run, engine_factory=factory) as actual:
        assert actual is connection
        assert events == ["connect", "begin", "SET TRANSACTION READ ONLY", "identity-read", "end-read-only"]
        events.append("test-body")
    assert events[-3:] == ["test-body", "close", "dispose"]
    assert arguments[0][1]["echo"] is False
    assert arguments[0][1]["connect_args"]["connect_timeout"] == 5
    assert "statement_timeout=10000" in arguments[0][1]["connect_args"]["options"]
    assert "lock_timeout=5000" in arguments[0][1]["connect_args"]["options"]


@pytest.mark.parametrize("bad_identity", [
    {"database_name": "production"}, {"marker": "wrong"}, {"marker": None},
    {"role_name": "other"}, {"session_role": "other"},
    {"rolsuper": True}, {"rolbypassrls": True}, {"rolsuper": 0},
])
def test_mismatched_identity_or_privileged_role_never_yields(bad_identity):
    url, run = _target()
    events = []
    connection = Connection(run, events, **bad_identity)
    with pytest.raises(RuntimeError, match="verification failed"):
        with verified_snapshot_connection(url, run, engine_factory=lambda *_a, **_kw: Engine(connection, events)):
            pytest.fail("Unverified connection must never reach test code")
    assert events[-2:] == ["close", "dispose"]
    assert "rollback" in events


@pytest.mark.parametrize("key", ["PGHOST", "PGHOSTADDR", "PGSERVICE", "PGPORT", "PGOPTIONS", "PGPASSWORD"])
def test_ambient_driver_configuration_fails_before_engine(monkeypatch, key):
    url, run = _target()
    monkeypatch.setenv(key, "synthetic-sensitive-value")
    called = []
    with pytest.raises(ValueError) as failure:
        with verified_snapshot_connection(url, run, engine_factory=lambda *_a, **_kw: called.append(True)):
            pytest.fail("Ambient override must fail")
    assert not called and "synthetic-sensitive-value" not in str(failure.value)


@pytest.mark.parametrize("stage", ["factory", "connect", "query"])
def test_preflight_failures_are_redacted_and_cleanup_attempted(stage):
    url, run = _target()
    events = []
    connection = Connection(run, events)
    engine = Engine(connection, events)

    def failure(*_a, **_kw):
        raise RuntimeError(f"driver exposed {url} /keys/synthetic")

    if stage == "connect":
        engine.connect = failure
    if stage == "query":
        connection.execute = failure
    factory = failure if stage == "factory" else lambda *_a, **_kw: engine
    with pytest.raises(RuntimeError) as error:
        with verified_snapshot_connection(url, run, engine_factory=factory):
            pytest.fail("Failed preflight must not yield")
    assert "synthetic-password" not in str(error.value) and "/keys/" not in str(error.value)
    assert error.value.__suppress_context__
    assert error.value.__context__ is None
    if stage != "factory":
        assert events[-1] == "dispose"
    if stage == "query":
        assert events[-2] == "close"


def test_test_body_exception_is_not_replaced_by_preflight_error():
    url, run = _target()
    events = []
    connection = Connection(run, events)
    with pytest.raises(AssertionError, match="real assertion"):
        with verified_snapshot_connection(url, run, engine_factory=lambda *_a, **_kw: Engine(connection, events)):
            raise AssertionError("real assertion")
    assert events[-2:] == ["close", "dispose"]


def test_each_acquisition_uses_a_new_verified_connection():
    url, run = _target()
    events, connections = [], []

    def factory(*_a, **_kw):
        connection = Connection(run, events)
        connections.append(connection)
        return Engine(connection, events)

    with verified_snapshot_connection(url, run, engine_factory=factory) as first:
        with verified_snapshot_connection(url, run, engine_factory=factory) as second:
            assert first is not second
    assert len(connections) == events.count("identity-read") == 2
    assert events.count("close") == events.count("dispose") == 2


@pytest.mark.parametrize("stage", ["close", "dispose"])
def test_cleanup_errors_are_redacted_and_all_cleanup_is_attempted(stage):
    url, run = _target()
    events = []
    connection = Connection(run, events)
    engine = Engine(connection, events)

    def failure():
        events.append(stage)
        raise RuntimeError(f"cleanup exposed {url}")

    if stage == "close":
        connection.close = failure
    else:
        engine.dispose = failure
    with pytest.raises(RuntimeError, match="cleanup failed") as error:
        with verified_snapshot_connection(url, run, engine_factory=lambda *_a, **_kw: engine):
            pass
    assert events[-2:] == ["close", "dispose"]
    assert "synthetic-password" not in str(error.value)
    assert error.value.__context__ is None


def test_wrong_dialect_never_begins_a_verification_query():
    url, run = _target()
    events = []
    connection = Connection(run, events)
    connection.dialect.name = "sqlite"
    with pytest.raises(RuntimeError, match="verification failed"):
        with verified_snapshot_connection(url, run, engine_factory=lambda *_a, **_kw: Engine(connection, events)):
            pytest.fail("Wrong dialect must fail")
    assert events == ["connect", "close", "dispose"]


def test_invalidated_connection_cannot_reconnect_without_fresh_identity_proof():
    url, run = _target()
    events = []
    connection = Connection(run, events)
    engine = Engine(connection, events)
    with verified_snapshot_connection(url, run, engine_factory=lambda *_a, **_kw: engine) as actual:
        actual.invalidate()
        actual.rollback()
        with pytest.raises(RuntimeError, match="physical connection"):
            actual.execute(support._IDENTITY_SQL)
    assert events.count("connect") == events.count("identity-read") == 1


def test_real_sqlalchemy_reconnect_is_denied_offline():
    engine = create_engine("sqlite://", poolclass=NullPool)
    physical_connections = []
    _REAL_LISTEN(engine, "connect", lambda connection, _record: physical_connections.append(connection))
    support._limit_physical_connections(engine)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
            connection.invalidate()
            connection.rollback()
            with pytest.raises(StatementError, match="physical connection") as error:
                connection.scalar(text("SELECT 1"))
            assert isinstance(error.value.orig, RuntimeError)
        with pytest.raises(RuntimeError, match="physical connection"):
            engine.connect()
        assert len(physical_connections) == 1
        engine.dispose()
        with pytest.raises(RuntimeError, match="physical connection"):
            engine.connect()
    finally:
        engine.dispose()


@pytest.mark.parametrize("stage", ["close", "dispose"])
def test_combined_body_and_cleanup_error_has_no_sensitive_context(stage):
    url, run = _target()
    events = []
    connection = Connection(run, events)
    engine = Engine(connection, events)

    def failure():
        events.append(stage)
        raise RuntimeError(f"cleanup exposed {url}")

    if stage == "close":
        connection.close = failure
    else:
        engine.dispose = failure
    with pytest.raises(RuntimeError, match="cleanup failed") as error:
        with verified_snapshot_connection(url, run, engine_factory=lambda *_a, **_kw: engine):
            raise AssertionError(f"sensitive body {url}")
    assert error.value.__context__ is None
    assert "synthetic-password" not in str(error.value)
    assert events[-2:] == ["close", "dispose"]
