"""Add evidence-backed brand party fingerprints.

Revision ID: 20260808_0001
Revises: 20260726_0001
Create Date: 2026-08-08
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260808_0001"
down_revision: Union[str, None] = "20260726_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brand_party_fingerprints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "brand_id",
            sa.String(36),
            sa.ForeignKey("brand_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("party_type", sa.String(100), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("state", sa.String(50), server_default="", nullable=False),
        sa.Column("evidence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_match_ids", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "last_verified_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "organization_id",
            "brand_id",
            "party_type",
            "normalized_name",
            "state",
            name="uq_brand_party_fingerprint_identity",
        ),
    )
    op.create_index(
        "ix_brand_party_fingerprints_organization_id",
        "brand_party_fingerprints",
        ["organization_id"],
    )
    op.create_index(
        "ix_brand_party_fingerprint_brand_type_active",
        "brand_party_fingerprints",
        ["brand_id", "party_type", "is_active"],
    )
    op.create_index(
        "ix_brand_party_fingerprint_org_name_state",
        "brand_party_fingerprints",
        ["organization_id", "normalized_name", "state"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "brand_party_fingerprints" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "brand_party_fingerprints" FORCE ROW LEVEL SECURITY')
        op.execute(
            """CREATE POLICY tenant_isolation ON "brand_party_fingerprints"
            USING (organization_id = current_setting('app.current_org', true))
            WITH CHECK (organization_id = current_setting('app.current_org', true))"""
        )


def downgrade() -> None:
    op.drop_index(
        "ix_brand_party_fingerprint_org_name_state",
        table_name="brand_party_fingerprints",
    )
    op.drop_index(
        "ix_brand_party_fingerprint_brand_type_active",
        table_name="brand_party_fingerprints",
    )
    op.drop_index(
        "ix_brand_party_fingerprints_organization_id",
        table_name="brand_party_fingerprints",
    )
    op.drop_table("brand_party_fingerprints")
