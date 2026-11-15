"""Verified connections for explicitly provisioned disposable snapshot tests.

This is an accidental-target safeguard, not proof against tunnels or a malicious
operator. Provision a fresh, nonce-marked local database independently first.
Never use production credentials, and keep process environment stable during use.
"""
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import NoReturn

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

from tests.postgres_target_guard import validate_snapshot_test_target

_IDENTITY_SQL = text("""
SELECT pg_catalog.current_database() AS database_name,
       current_user AS role_name, session_user AS session_role,
       r.rolsuper, r.rolbypassrls,
       pg_catalog.shobj_description(d.oid, 'pg_database') AS marker
FROM pg_catalog.pg_database AS d
JOIN pg_catalog.pg_roles AS r ON r.rolname = current_user
WHERE d.datname = pg_catalog.current_database()
""")


def _raise_sanitized(message: str) -> NoReturn:
    failure = RuntimeError(message)
    try:
        raise failure from None
    finally:
        # contextlib may still be unwinding the caller's sensitive body error.
        failure.__context__ = None


def _release(connection: Connection | None, engine: Engine | None) -> None:
    failed = False
    if connection is not None:
        try:
            connection.close()
        except Exception:
            failed = True
    if engine is not None:
        try:
            engine.dispose()
        except Exception:
            failed = True
    if failed:
        _raise_sanitized("Snapshot PostgreSQL cleanup failed")


def _limit_physical_connections(engine: Engine) -> None:
    attempted = False

    def before_connect(_dialect, _record, _args, _kwargs):
        nonlocal attempted
        if attempted:
            _raise_sanitized("A replacement physical connection requires fresh verification")
        attempted = True

    # Retain this on the owned engine even after dispose: reconnection is unsafe.
    event.listen(engine, "do_connect", before_connect)


@contextmanager
def verified_snapshot_connection(
    url: str, run_id: str, *, engine_factory: Callable[..., Engine] | None = None,
) -> Iterator[Connection]:
    """Verify each physical connection read-only before yielding it to test code.

    Does not create a database, marker, role, extension, schema or migration.
    Environment cannot be overridden independently of the driver's environment.
    engine_factory is an offline-test hook; real tests must use the default.
    """
    target = validate_snapshot_test_target(url, run_id, os.environ)
    engine = connection = None
    preflight_error = None
    try:
        factory = engine_factory if engine_factory is not None else create_engine
        engine = factory(target.url, poolclass=NullPool, echo=False, connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=10000 -c lock_timeout=5000",
        })
        _limit_physical_connections(engine)
        connection = engine.connect()
        if connection.dialect.name != "postgresql":
            raise ValueError("Unexpected test dialect")
        with connection.begin():
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            identity = connection.execute(_IDENTITY_SQL).mappings().one()
            if (identity["database_name"] != target.database
                    or identity["role_name"] != target.username
                    or identity["session_role"] != target.username
                    or identity["rolsuper"] is not False
                    or identity["rolbypassrls"] is not False
                    or identity["marker"] != target.marker):
                raise ValueError("Unverified disposable target")
    except BaseException as error:
        preflight_error = error
    if preflight_error is not None:
        _release(connection, engine)
        if isinstance(preflight_error, Exception):
            _raise_sanitized("Snapshot PostgreSQL target verification failed")
        raise preflight_error

    body_error = None
    try:
        yield connection
    except BaseException as error:
        body_error = error
    # Finish outside exception unwinding so cleanup errors cannot chain secrets.
    _release(connection, engine)
    if body_error is not None:
        raise body_error
