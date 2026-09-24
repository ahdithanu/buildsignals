"""Alembic environment configuration.

Reads DATABASE_URL from app.config so migrations use the same DB as the app.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

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


def include_postgres_object(obj, name, type_, reflected, compare_to):
    """Retain backend-only PostGIS objects created by 20260716_0006.

    Only unmatched reflected objects are excluded. If a model later declares
    one of these objects, Alembic must compare it normally.
    """
    if reflected and compare_to is None:
        if type_ == "table" and name == "spatial_ref_sys" and obj.schema in (None, "public"):
            return False
        if type_ == "column" and obj.table.name == "parcel_records" and name == "centroid":
            return False
        if type_ == "index" and obj.table.name == "parcel_records" and name == "ix_parcel_record_centroid_gist":
            return False
    return True


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
            include_object=include_postgres_object if connection.dialect.name == "postgresql" else None,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
