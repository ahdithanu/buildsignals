"""Add tenant-scoped temporal observation snapshots and events.

Revision ID: 20260919_0001
Revises: 20260915_0001
Create Date: 2026-09-19
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "20260919_0001"
down_revision: str = "20260915_0001"
branch_labels = None
depends_on = None

_TABLES = ("temporal_observations", "temporal_events")


def upgrade() -> None:
    op.create_table(
        "temporal_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("raw_source_record_id", sa.String(36), nullable=False),
        sa.Column(
            "source_id", sa.String(36),
            sa.ForeignKey("ingestion_sources.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("observation_key", sa.String(64), nullable=False),
        sa.Column("series_key", sa.String(64), nullable=False),
        sa.Column("attribute", sa.String(100), nullable=False),
        sa.Column("value", sa.JSON(none_as_null=False), nullable=False),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_system", sa.String(100), nullable=False),
        sa.Column("source_type", sa.String(100), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("geography", sa.JSON(), nullable=True),
        sa.Column("methodology_version", sa.String(100), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["raw_source_record_id", "organization_id"],
            ["raw_source_records.id", "raw_source_records.organization_id"],
            ondelete="RESTRICT",
            name="fk_temporal_observation_raw_record_org",
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_temporal_observation_id_org"),
        sa.UniqueConstraint(
            "organization_id", "observation_key", name="uq_temporal_observation_org_key"
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_temporal_observation_confidence"
        ),
    )
    op.create_index(
        "ix_temporal_observation_org_series_recorded", "temporal_observations",
        ["organization_id", "series_key", "recorded_at"],
    )
    op.create_index(
        "ix_temporal_observation_org_entity_attribute_recorded", "temporal_observations",
        ["organization_id", "entity_id", "attribute", "recorded_at"],
    )
    op.create_index(
        "ix_temporal_observation_org_effective", "temporal_observations",
        ["organization_id", "effective_at"],
    )
    op.create_index(
        "ix_temporal_observation_cohort_known", "temporal_observations",
        ["organization_id", "source_id", "attribute", "methodology_version", "recorded_at"],
    )
    op.create_index(
        "ix_temporal_observation_raw_attribute_method", "temporal_observations",
        ["organization_id", "raw_source_record_id", "attribute", "methodology_version", "recorded_at"],
    )

    op.create_table(
        "temporal_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("observation_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["observation_id", "organization_id"],
            ["temporal_observations.id", "temporal_observations.organization_id"],
            ondelete="RESTRICT",
            name="fk_temporal_event_observation_org",
        ),
        sa.UniqueConstraint(
            "organization_id", "observation_id", "event_type",
            name="uq_temporal_event_org_observation_type",
        ),
    )
    for table in _TABLES:
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(
                f'CREATE POLICY tenant_isolation ON "{table}" '
                "USING (organization_id = current_setting('app.current_org', true)) "
                "WITH CHECK (organization_id = current_setting('app.current_org', true))"
            )

    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """CREATE FUNCTION prevent_temporal_record_mutation()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' AND NOT EXISTS (
                    SELECT 1 FROM public.organizations
                    WHERE id = OLD.organization_id
                ) THEN
                    RETURN OLD;
                END IF;
                RAISE EXCEPTION '% are immutable', TG_TABLE_NAME;
            END;
            $$ LANGUAGE plpgsql
            SET search_path = pg_catalog, public"""
        )
        for table in _TABLES:
            op.execute(
                f'CREATE TRIGGER trg_{table}_immutable '
                f'BEFORE UPDATE OR DELETE ON "{table}" '
                "FOR EACH ROW EXECUTE FUNCTION prevent_temporal_record_mutation()"
            )
            op.execute(
                f'CREATE TRIGGER trg_{table}_no_truncate '
                f'BEFORE TRUNCATE ON "{table}" '
                "FOR EACH STATEMENT EXECUTE FUNCTION prevent_temporal_record_mutation()"
            )
    elif dialect == "sqlite":
        for table in _TABLES:
            op.execute(
                f"""CREATE TRIGGER trg_{table}_no_update
                BEFORE UPDATE ON "{table}"
                BEGIN
                    SELECT RAISE(ABORT, '{table} are immutable');
                END"""
            )
            op.execute(
                f"""CREATE TRIGGER trg_{table}_no_delete
                BEFORE DELETE ON "{table}"
                WHEN EXISTS (
                    SELECT 1 FROM organizations WHERE id = OLD.organization_id
                )
                BEGIN
                    SELECT RAISE(ABORT, '{table} are immutable');
                END"""
            )


def downgrade() -> None:
    op.drop_table("temporal_events")
    op.drop_table("temporal_observations")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS prevent_temporal_record_mutation()")
