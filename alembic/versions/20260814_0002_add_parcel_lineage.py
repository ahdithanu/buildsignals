"""Add evidence-backed parcel lineage events.

Revision ID: 20260814_0002
Revises: 20260814_0001
Create Date: 2026-08-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0002"
down_revision: Union[str, None] = "20260814_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "parcel_lineage_events",
    "parcel_lineage_participants",
    "parcel_lineage_evidence",
)


def upgrade() -> None:
    op.create_table(
        "parcel_lineage_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("ingestion_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_event_id", sa.String(500), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attributes", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('split', 'merge', 'replat', 'correction')",
            name="ck_parcel_lineage_event_type",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_parcel_lineage_event_confidence",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "source_id",
            "external_event_id",
            name="uq_parcel_lineage_event_source_external",
        ),
    )
    op.create_index(
        "ix_parcel_lineage_events_organization_id",
        "parcel_lineage_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_parcel_lineage_event_org_observed",
        "parcel_lineage_events",
        ["organization_id", "observed_at"],
    )

    op.create_table(
        "parcel_lineage_participants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("parcel_lineage_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("ingestion_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "parcel_id",
            sa.String(36),
            sa.ForeignKey("parcel_records.id", ondelete="SET NULL"),
        ),
        sa.Column("external_parcel_id", sa.String(500), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('predecessor', 'successor')",
            name="ck_parcel_lineage_participant_role",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "event_id",
            "role",
            "external_parcel_id",
            name="uq_parcel_lineage_participant_identity",
        ),
    )
    op.create_index(
        "ix_parcel_lineage_participants_organization_id",
        "parcel_lineage_participants",
        ["organization_id"],
    )
    op.create_index(
        "ix_parcel_lineage_participant_parcel",
        "parcel_lineage_participants",
        ["organization_id", "parcel_id"],
    )
    op.create_index(
        "ix_parcel_lineage_participant_unresolved",
        "parcel_lineage_participants",
        ["organization_id", "source_id", "external_parcel_id", "parcel_id"],
    )

    op.create_table(
        "parcel_lineage_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("parcel_lineage_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "raw_source_record_id",
            sa.String(36),
            sa.ForeignKey("raw_source_records.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_url", sa.String(2000)),
        sa.Column("excerpt", sa.Text()),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_parcel_lineage_evidence_confidence",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "event_id",
            "raw_source_record_id",
            name="uq_parcel_lineage_evidence_raw",
        ),
    )
    op.create_index(
        "ix_parcel_lineage_evidence_organization_id",
        "parcel_lineage_evidence",
        ["organization_id"],
    )
    op.create_index(
        "ix_parcel_lineage_evidence_event",
        "parcel_lineage_evidence",
        ["organization_id", "event_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in _TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(
                f"""
                CREATE POLICY tenant_isolation ON "{table}"
                    USING (organization_id = current_setting('app.current_org', true))
                    WITH CHECK (organization_id = current_setting('app.current_org', true))
                """
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in _TABLES:
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
    op.drop_table("parcel_lineage_evidence")
    op.drop_table("parcel_lineage_participants")
    op.drop_table("parcel_lineage_events")
