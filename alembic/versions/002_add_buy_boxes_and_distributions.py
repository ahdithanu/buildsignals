"""Add buy_boxes and deal_distributions tables.

Revision ID: 002
Revises: 001
Create Date: 2026-04-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Buy Boxes ─────────────────────────────────────────────────────────
    op.create_table(
        "buy_boxes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("asset_type", sa.String(100), nullable=True),
        sa.Column("locations", sa.Text(), nullable=True),
        sa.Column("min_price", sa.Float(), nullable=True),
        sa.Column("max_price", sa.Float(), nullable=True),
        sa.Column("min_irr", sa.Float(), nullable=True),
        sa.Column("deal_type", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_buy_boxes_org_id", "buy_boxes", ["organization_id"])
    op.create_index("ix_buy_boxes_user_id", "buy_boxes", ["user_id"])

    # ── Deal Distributions ────────────────────────────────────────────────
    op.create_table(
        "deal_distributions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_name", sa.String(255), nullable=False),
        sa.Column("recipient_email", sa.String(255), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_deal_distributions_org_id", "deal_distributions", ["organization_id"])
    op.create_index("ix_deal_distributions_deal_id", "deal_distributions", ["deal_id"])


def downgrade() -> None:
    op.drop_table("deal_distributions")
    op.drop_table("buy_boxes")
