"""Add source-neutral planning intelligence records and company matches.

Revision ID: 20260822_0001
Revises: 20260821_0002
Create Date: 2026-08-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260822_0001"
down_revision: Union[str, None] = "20260821_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planning_records",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.String(length=36),
            sa.ForeignKey("ingestion_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "latest_raw_record_id",
            sa.String(length=36),
            sa.ForeignKey("raw_source_records.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_record_id", sa.String(length=500), nullable=False),
        sa.Column("normalization_hash", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("stage", sa.String(length=50)),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("evidence_excerpt", sa.Text()),
        sa.Column("agenda_item_number", sa.String(length=100)),
        sa.Column("meeting_name", sa.String(length=500)),
        sa.Column("governing_body", sa.String(length=500)),
        sa.Column("project_name", sa.String(length=500)),
        sa.Column("address", sa.String(length=1000)),
        sa.Column("city", sa.String(length=100)),
        sa.Column("state", sa.String(length=50)),
        sa.Column("postal_code", sa.String(length=20)),
        sa.Column("parcel_id", sa.String(length=255)),
        sa.Column("jurisdiction", sa.String(length=255)),
        sa.Column("applicant_name", sa.String(length=500)),
        sa.Column("owner_name", sa.String(length=500)),
        sa.Column("developer_name", sa.String(length=500)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("meeting_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("decision_at", sa.DateTime(timezone=True)),
        sa.Column("source_url", sa.String(length=2000)),
        sa.Column("signal_categories", sa.JSON(), nullable=False),
        sa.Column("priority_reasons", sa.JSON(), nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1")),
        sa.Column("attributes", sa.JSON()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_id", "external_record_id", name="uq_planning_record_source_external"
        ),
    )
    op.create_index(
        "ix_planning_record_org_stage", "planning_records", ["organization_id", "stage"]
    )
    op.create_index(
        "ix_planning_record_org_meeting", "planning_records", ["organization_id", "meeting_at"]
    )
    op.create_index(
        "ix_planning_record_org_priority", "planning_records", ["organization_id", "priority_score"]
    )
    op.create_index(
        "ix_planning_record_location",
        "planning_records",
        ["organization_id", "state", "city", "postal_code"],
    )
    op.create_index(
        "ix_planning_record_parcel", "planning_records", ["organization_id", "parcel_id"]
    )

    op.create_table(
        "planning_company_matches",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "planning_record_id",
            sa.String(length=36),
            sa.ForeignKey("planning_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            sa.String(length=36),
            sa.ForeignKey("brand_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "raw_record_id",
            sa.String(length=36),
            sa.ForeignKey("raw_source_records.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "review_status", sa.String(length=32), nullable=False, server_default="candidate"
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("matched_alias", sa.String(length=255), nullable=False),
        sa.Column("matched_field", sa.String(length=100), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("detector_version", sa.String(length=50), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("planning_record_id", "brand_id", name="uq_planning_company_match"),
    )
    op.create_index(
        "ix_planning_company_match_org_status",
        "planning_company_matches",
        ["organization_id", "review_status"],
    )
    op.create_index(
        "ix_planning_company_match_org_confidence",
        "planning_company_matches",
        ["organization_id", "confidence"],
    )


def downgrade() -> None:
    op.drop_index("ix_planning_company_match_org_confidence", table_name="planning_company_matches")
    op.drop_index("ix_planning_company_match_org_status", table_name="planning_company_matches")
    op.drop_table("planning_company_matches")
    op.drop_index("ix_planning_record_parcel", table_name="planning_records")
    op.drop_index("ix_planning_record_location", table_name="planning_records")
    op.drop_index("ix_planning_record_org_priority", table_name="planning_records")
    op.drop_index("ix_planning_record_org_meeting", table_name="planning_records")
    op.drop_index("ix_planning_record_org_stage", table_name="planning_records")
    op.drop_table("planning_records")
