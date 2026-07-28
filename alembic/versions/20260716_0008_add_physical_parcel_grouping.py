"""Add physical parcel grouping for condo and multi-account records.

Revision ID: 20260716_0008
Revises: 20260716_0007
Create Date: 2026-07-16
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0008"
down_revision: Union[str, None] = "20260716_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("parcel_records") as batch:
        batch.add_column(sa.Column("parcel_group_id", sa.String(500)))
        batch.create_index(
            "ix_parcel_record_physical_group",
            ["organization_id", "source_id", "parcel_group_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("parcel_records") as batch:
        batch.drop_index("ix_parcel_record_physical_group")
        batch.drop_column("parcel_group_id")
