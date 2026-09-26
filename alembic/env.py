"""Alembic environment configuration.

Reads DATABASE_URL from app.config so migrations use the same DB as the app.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text

from alembic import context

# Add project root to path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app.models  # noqa: F401 — register all models
from app.config import DATABASE_URL
from app.db import Base

# Alembic Config object
config = context.config

# Override sqlalchemy.url with our app's DATABASE_URL
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

# Setup logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate
target_metadata = Base.metadata


def postgres_object_filter(connection):
    """Exclude proven extension relations, not application namesakes.

    SQLAlchemy can reflect search-path-visible tables with schema=None even
    when they belong to the topology schema. Only map that unqualified key if
    PostgreSQL confirms the extension's actual relation is visible.
    """
    extension_relations = None

    def include_object(obj, name, type_, reflected, compare_to):
        nonlocal extension_relations
        if reflected and compare_to is None:
            if type_ == "table":
                if extension_relations is None:
                    # Query lazily: a catalog read before context.configure()
                    # would autobegin an external transaction and prevent
                    # Alembic from committing ordinary migration upgrades.
                    rows = connection.execute(text("""
                        SELECT n.nspname, c.relname,
                               pg_catalog.pg_table_is_visible(c.oid) AS visible
                        FROM pg_catalog.pg_depend AS d
                        JOIN pg_catalog.pg_extension AS e ON e.oid = d.refobjid
                        JOIN pg_catalog.pg_class AS c ON c.oid = d.objid
                        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                        WHERE d.classid = 'pg_catalog.pg_class'::regclass
                          AND d.refclassid = 'pg_catalog.pg_extension'::regclass
                          AND d.objsubid = 0 AND d.deptype = 'e'
                          AND e.extname IN ('postgis', 'postgis_topology')
                          AND c.relkind IN ('r', 'p', 'f', 'm')
                    """))
                    extension_relations = set()
                    for schema, relation, visible in rows:
                        extension_relations.add((schema, relation))
                        if visible:
                            extension_relations.add((None, relation))
                return (obj.schema, name) not in extension_relations
            # Backend-only objects intentionally created by 20260716_0006.
            if type_ == "column" and obj.table.name == "parcel_records" and name == "centroid":
                return False
            if type_ == "index" and obj.table.name == "parcel_records" and name == "ix_parcel_record_centroid_gist":
                return False
        return True

    return include_object


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=postgres_object_filter(connection) if connection.dialect.name == "postgresql" else None,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
