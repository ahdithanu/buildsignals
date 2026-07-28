from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

# Only use check_same_thread for SQLite
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


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

if engine.dialect.name == "postgresql":

    @event.listens_for(SessionLocal, "after_begin")
    def _set_rls_org(session, transaction, connection):  # noqa: ARG001
        # Imported lazily to avoid a circular import (org_scope → nothing, but
        # keeps db.py import-light at module load).
        from app.utils.org_scope import get_org_id

        org_id = get_org_id()
        connection.execute(
            text("SELECT set_config('app.current_org', :org, true)"),
            {"org": org_id},
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
