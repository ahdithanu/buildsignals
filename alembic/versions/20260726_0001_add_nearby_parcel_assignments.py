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
    with op.batch_alter_table("nearby_parcel_candidates") as batch:
        batch.add_column(
            sa.Column("assigned_to_user_id", sa.String(length=36), nullable=True),
        )
        batch.add_column(
            sa.Column("assigned_to_name", sa.String(length=255), nullable=True),
        )
        batch.add_column(
            sa.Column("assigned_by_user_id", sa.String(length=36), nullable=True),
        )
        batch.add_column(
            sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        )
        batch.create_foreign_key(
            "fk_nearby_parcel_candidates_assigned_to_user_id_users",
            "users",
            ["assigned_to_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_nearby_parcel_candidates_assigned_by_user_id_users",
            "users",
            ["assigned_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            "ix_nearby_parcel_candidate_assigned_to",
            ["organization_id", "assigned_to_user_id", "review_status"],
        )


def downgrade() -> None:
    with op.batch_alter_table("nearby_parcel_candidates") as batch:
        batch.drop_index("ix_nearby_parcel_candidate_assigned_to")
        batch.drop_column("assigned_at")
        batch.drop_column("assigned_by_user_id")
        batch.drop_column("assigned_to_name")
        batch.drop_column("assigned_to_user_id")
