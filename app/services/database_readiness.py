"""Read-only schema readiness, without fetching application records."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from time import monotonic

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import column, false, select, table, text
from sqlalchemy.orm import Session

import app.models  # noqa: F401 - register every mapped table before probing
from app.db import Base

_ALEMBIC_CONFIG = Path(__file__).resolve().parents[2] / "alembic.ini"
_SCHEMA_BUDGET_SECONDS = 5.0


@lru_cache(maxsize=1)
def _expected_heads(config_path: Path) -> frozenset[str]:
    """Read the release's migration graph, never execute its env or migrations."""
    if not config_path.is_file():
        raise ValueError("Migration configuration unavailable")
    config = Config(str(config_path))
    location = config.get_main_option("script_location")
    if not location:
        raise ValueError("Migration scripts unavailable")
    # Alembic normally resolves relative script paths against the process CWD.
    # Preserve configured package resources/absolute paths; anchor relative paths
    # to the repository's configuration file instead.
    if ":" not in location and not Path(location).is_absolute():
        location = str(config_path.parent / location)
        config.set_main_option("script_location", location.replace("%", "%%"))
    config.set_main_option("prepend_sys_path", str(config_path.parent).replace("%", "%%"))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


def is_database_ready(db: Session) -> bool:
    """Require all mapped columns and exact Alembic heads; fail closed.

    One zero-row projection per mapped table checks name resolution and SELECT
    permission without reading tenant rows. Only Alembic's version identifiers
    are fetched, capped at the expected head count plus one. No ORM flush,
    migration, schema creation, or commit is performed.
    """
    deadline = monotonic() + _SCHEMA_BUDGET_SECONDS
    try:
        heads = _expected_heads(_ALEMBIC_CONFIG)
        if not heads or not Base.metadata.tables or monotonic() >= deadline:
            return False

        # Own the connection so read-only/timeout settings are rolled back on
        # every outcome, without flushing or altering the caller's ORM session.
        with db.get_bind().connect() as connection:
            if monotonic() >= deadline:
                return False
            if connection.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION READ ONLY")).close()
                connection.execute(text("SET LOCAL statement_timeout = '1000ms'")).close()
                connection.execute(text("SET LOCAL lock_timeout = '250ms'")).close()

            for mapped_table in Base.metadata.tables.values():
                if monotonic() >= deadline:
                    return False
                statement = select(*mapped_table.columns).where(false()).limit(0)
                connection.execute(statement).close()

            if monotonic() >= deadline:
                return False
            versions = table("alembic_version", column("version_num"))
            with connection.execute(
                select(versions.c.version_num).limit(len(heads) + 1)
            ) as result:
                current_heads = result.scalars().all()
            return (
                monotonic() < deadline
                and len(current_heads) == len(heads)
                and frozenset(current_heads) == heads
            )
    except Exception:
        # Driver and migration-configuration failures also stay generic on this
        # public endpoint. Never include exception text, SQL, or schema names.
        return False
