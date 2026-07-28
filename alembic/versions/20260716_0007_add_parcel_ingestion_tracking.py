"""Add parcel normalization and snapshot tracking.

Revision ID: 20260716_0007
Revises: 20260716_0006
Create Date: 2026-07-16
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0007"
down_revision: Union[str, None] = "20260716_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("parcel_records") as batch:
        batch.add_column(
            sa.Column("normalization_hash", sa.String(64), server_default="", nullable=False)
        )
        batch.add_column(sa.Column("last_seen_snapshot_id", sa.String(36)))
        batch.add_column(sa.Column("attributes", sa.JSON()))
        batch.create_index(
            "ix_parcel_records_last_seen_snapshot_id", ["last_seen_snapshot_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("parcel_records") as batch:
        batch.drop_index("ix_parcel_records_last_seen_snapshot_id")
        batch.drop_column("attributes")
        batch.drop_column("last_seen_snapshot_id")
        batch.drop_column("normalization_hash")
