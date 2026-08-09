"""Enforce raw source record immutability in the database.

Revision ID: 20260809_0002
Revises: 20260809_0001
Create Date: 2026-08-09
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260809_0002"
down_revision: Union[str, None] = "20260809_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """CREATE FUNCTION prevent_raw_source_record_mutation()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' AND NOT EXISTS (
                    SELECT 1 FROM public.organizations
                    WHERE id = OLD.organization_id
                ) THEN
                    RETURN OLD;
                END IF;
                RAISE EXCEPTION 'raw_source_records are immutable';
            END;
            $$ LANGUAGE plpgsql
            SET search_path = pg_catalog, public"""
        )
        op.execute(
            """CREATE TRIGGER trg_raw_source_records_immutable
            BEFORE UPDATE OR DELETE ON raw_source_records
            FOR EACH ROW EXECUTE FUNCTION prevent_raw_source_record_mutation()"""
        )
        op.execute(
            """CREATE TRIGGER trg_raw_source_records_no_truncate
            BEFORE TRUNCATE ON raw_source_records
            FOR EACH STATEMENT EXECUTE FUNCTION prevent_raw_source_record_mutation()"""
        )
    elif dialect == "sqlite":
        op.execute(
            """CREATE TRIGGER trg_raw_source_records_no_update
            BEFORE UPDATE ON raw_source_records
            BEGIN
                SELECT RAISE(ABORT, 'raw_source_records are immutable');
            END"""
        )
        op.execute(
            """CREATE TRIGGER trg_raw_source_records_no_delete
            BEFORE DELETE ON raw_source_records
            WHEN EXISTS (
                SELECT 1 FROM organizations WHERE id = OLD.organization_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'raw_source_records are immutable');
            END"""
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_raw_source_records_no_truncate "
            "ON raw_source_records"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_raw_source_records_immutable "
            "ON raw_source_records"
        )
        op.execute("DROP FUNCTION IF EXISTS prevent_raw_source_record_mutation()")
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_raw_source_records_no_update")
        op.execute("DROP TRIGGER IF EXISTS trg_raw_source_records_no_delete")
