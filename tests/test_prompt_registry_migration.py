"""Prompt registry schema parity and database-enforced content immutability."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

from app.db import configure_sqlite_foreign_keys
from app.models.prompt_registry import PromptTemplate, PromptVersion


def test_migration_and_immutable_content():
    path = Path(__file__).resolve().parent.parent / "alembic/versions/20260924_0001_prompt_registry.py"
    spec = importlib.util.spec_from_file_location("prompt_registry_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    configure_sqlite_foreign_keys(engine)
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("CREATE TABLE organizations (id VARCHAR(36) NOT NULL PRIMARY KEY)"))
            conn.execute(sa.text("CREATE TABLE users (id VARCHAR(36) NOT NULL PRIMARY KEY)"))
            conn.execute(sa.text("INSERT INTO organizations VALUES ('org-a'), ('org-b')"))
            migration.op = Operations(MigrationContext.configure(conn))
            migration.upgrade()
            metadata = sa.MetaData()
            sa.Table("organizations", metadata, sa.Column("id", sa.String(36), primary_key=True))
            sa.Table("users", metadata, sa.Column("id", sa.String(36), primary_key=True))
            PromptTemplate.__table__.to_metadata(metadata)
            PromptVersion.__table__.to_metadata(metadata)
            assert compare_metadata(MigrationContext.configure(conn), metadata) == []
            now = datetime.now(timezone.utc)
            conn.execute(PromptTemplate.__table__.insert().values(
                id="template-a", organization_id="org-a", key="memo", name="Memo",
                workflow="opportunity_memo", description="", created_at=now,
            ))
            conn.execute(PromptVersion.__table__.insert().values(
                id="version-a", organization_id="org-a", template_id="template-a", version=1,
                body="Hello", variables=[], checksum="a" * 64, created_at=now,
            ))
            conn.execute(PromptVersion.__table__.update().where(PromptVersion.id == "version-a").values(activated_at=now))
            try:
                conn.execute(PromptVersion.__table__.update().where(PromptVersion.id == "version-a").values(body="Changed"))
            except IntegrityError:
                pass
            else:
                raise AssertionError("Prompt version body was mutable")
            assert conn.execute(sa.select(PromptVersion.body).where(PromptVersion.id == "version-a")).scalar_one() == "Hello"
            try:
                conn.execute(PromptVersion.__table__.insert().values(
                    id="cross-org", organization_id="org-b", template_id="template-a", version=2,
                    body="Cross", variables=[], checksum="b" * 64, created_at=now,
                ))
            except IntegrityError:
                pass
            else:
                raise AssertionError("Cross-organization version reference was accepted")
            migration.downgrade()
            assert "prompt_template" not in sa.inspect(conn).get_table_names()
    finally:
        engine.dispose()
