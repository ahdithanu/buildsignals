"""Add assignment tracking to nearby parcel candidates.

Revision ID: 20260726_0001
Revises: 20260723_0001
Create Date: 2026-07-26
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260726_0001"
down_revision: Union[str, None] = "20260723_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "nearby_parcel_candidates",
        sa.Column("assigned_to_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "nearby_parcel_candidates",
        sa.Column("assigned_to_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "nearby_parcel_candidates",
        sa.Column("assigned_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "nearby_parcel_candidates",
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_nearby_parcel_candidate_assigned_to",
        "nearby_parcel_candidates",
        ["organization_id", "assigned_to_user_id", "review_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_nearby_parcel_candidate_assigned_to",
        table_name="nearby_parcel_candidates",
    )
    op.drop_column("nearby_parcel_candidates", "assigned_at")
    op.drop_column("nearby_parcel_candidates", "assigned_by_user_id")
    op.drop_column("nearby_parcel_candidates", "assigned_to_name")
    op.drop_column("nearby_parcel_candidates", "assigned_to_user_id")
