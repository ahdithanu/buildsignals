import sqlite3

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATABASE_URL


def configure_sqlite_foreign_keys(target_engine: Engine) -> None:
    @event.listens_for(target_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        if not isinstance(dbapi_connection, sqlite3.Connection):
            return
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()


# Only use check_same_thread for SQLite
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args)
if engine.dialect.name == "sqlite":
    configure_sqlite_foreign_keys(engine)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


@event.listens_for(Session, "after_begin")
def _demo_read_only_transaction(session, transaction, connection):
    from app.services.demo_access import demo_read_only

    if demo_read_only.get() and connection.dialect.name == "postgresql":
        connection.execute(text("SET TRANSACTION READ ONLY"))


@event.listens_for(Session, "before_flush")
def _demo_reject_orm_mutations(session, flush_context, instances):
    from app.services.demo_access import demo_read_only

    if demo_read_only.get() and (session.new or session.dirty or session.deleted):
        raise PermissionError("Demo sessions cannot mutate stored data")


# ── Postgres RLS glue ─────────────────────────────────────────────────────
#
# Migration 003 enables row-level security on every tenant table with a
# policy of the form:
#     organization_id = current_setting('app.current_org', true)
#
# For that to allow any rows through, every transaction must set
# `app.current_org` first. We hook `after_begin` so the setting is applied
# at the start of every transaction the ORM opens, including new
# transactions that start after an explicit commit() mid-request.
#
# `set_config(..., is_local=true)` scopes the setting to the transaction,
# so it is automatically cleared on commit/rollback and can never leak
# across connections in the pool.
#
# On SQLite (dev/test) this is a no-op.

@event.listens_for(SessionLocal, "after_begin")
def _set_rls_org(session, transaction, connection):  # noqa: ARG001
    if connection.dialect.name != "postgresql":
        return
    from app.utils.org_scope import get_org_id

    connection.execute(
        text("SELECT set_config('app.current_org', :org, true)"),
        {"org": get_org_id()},
    )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    import app.models  # noqa: F401 – ensure all models are registered
    Base.metadata.create_all(bind=engine)
