"""Add evidence-backed brand intelligence.

Revision ID: 20260716_0003
Revises: 20260716_0002
Create Date: 2026-07-16
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0003"
down_revision: Union[str, None] = "20260716_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_TABLES = ("brand_profiles", "brand_aliases", "permit_brand_matches")


def _tenant_column() -> sa.Column:
    return sa.Column(
        "organization_id",
        sa.String(36),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "brand_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("scale", sa.String(50)),
        sa.Column("priority", sa.Integer(), server_default="3", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("attributes", sa.JSON()),
        *_timestamps(),
        _tenant_column(),
        sa.UniqueConstraint("organization_id", "key", name="uq_brand_profile_org_key"),
    )
    op.create_index("ix_brand_profiles_organization_id", "brand_profiles", ["organization_id"])
    op.create_index("ix_brand_profiles_normalized_name", "brand_profiles", ["normalized_name"])
    op.create_index("ix_brand_profile_org_active", "brand_profiles", ["organization_id", "is_active"])

    op.create_table(
        "brand_aliases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), sa.ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(255), nullable=False),
        sa.Column("normalized_alias", sa.String(255), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1", nullable=False),
        sa.Column("requires_context", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("minimum_field_matches", sa.Integer(), server_default="1", nullable=False),
        sa.Column("context_terms", sa.JSON()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        _tenant_column(),
        sa.UniqueConstraint("organization_id", "normalized_alias", name="uq_brand_alias_org_alias"),
    )
    op.create_index("ix_brand_aliases_organization_id", "brand_aliases", ["organization_id"])
    op.create_index("ix_brand_aliases_normalized_alias", "brand_aliases", ["normalized_alias"])
    op.create_index("ix_brand_alias_brand_active", "brand_aliases", ["brand_id", "is_active"])

    op.create_table(
        "permit_brand_matches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("permit_id", sa.String(36), sa.ForeignKey("permit_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", sa.String(36), sa.ForeignKey("brand_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("first_raw_record_id", sa.String(36), sa.ForeignKey("raw_source_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("latest_raw_record_id", sa.String(36), sa.ForeignKey("raw_source_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("review_status", sa.String(32), server_default="candidate", nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("matched_alias", sa.String(255), nullable=False),
        sa.Column("matched_field", sa.String(100), nullable=False),
        sa.Column("matched_fields", sa.JSON()),
        sa.Column("rule_ids", sa.JSON()),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("detector_version", sa.String(50), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        *_timestamps(),
        _tenant_column(),
        sa.UniqueConstraint("permit_id", "brand_id", name="uq_permit_brand_match"),
    )
    op.create_index("ix_permit_brand_matches_organization_id", "permit_brand_matches", ["organization_id"])
    op.create_index("ix_permit_brand_match_org_status", "permit_brand_matches", ["organization_id", "review_status"])
    op.create_index("ix_permit_brand_match_org_confidence", "permit_brand_matches", ["organization_id", "confidence"])

    if op.get_bind().dialect.name == "postgresql":
        for table in TENANT_TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(
                f"""CREATE POLICY tenant_isolation ON "{table}"
                USING (organization_id = current_setting('app.current_org', true))
                WITH CHECK (organization_id = current_setting('app.current_org', true))"""
            )


def downgrade() -> None:
    op.drop_index("ix_permit_brand_match_org_confidence", table_name="permit_brand_matches")
    op.drop_index("ix_permit_brand_match_org_status", table_name="permit_brand_matches")
    op.drop_index("ix_permit_brand_matches_organization_id", table_name="permit_brand_matches")
    op.drop_table("permit_brand_matches")
    op.drop_index("ix_brand_alias_brand_active", table_name="brand_aliases")
    op.drop_index("ix_brand_aliases_normalized_alias", table_name="brand_aliases")
    op.drop_index("ix_brand_aliases_organization_id", table_name="brand_aliases")
    op.drop_table("brand_aliases")
    op.drop_index("ix_brand_profile_org_active", table_name="brand_profiles")
    op.drop_index("ix_brand_profiles_normalized_name", table_name="brand_profiles")
    op.drop_index("ix_brand_profiles_organization_id", table_name="brand_profiles")
    op.drop_table("brand_profiles")
