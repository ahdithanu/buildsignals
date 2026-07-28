"""Add permit snapshot reconciliation state.

Revision ID: 20260716_0005
Revises: 20260716_0004
Create Date: 2026-07-16
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0005"
down_revision: Union[str, None] = "20260716_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("permit_records", sa.Column("last_seen_snapshot_id", sa.String(36)))
    op.add_column(
        "permit_records",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column("permit_records", sa.Column("retired_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_permit_record_source_active",
        "permit_records",
        ["source_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_permit_record_source_active", table_name="permit_records")
    op.drop_column("permit_records", "retired_at")
    op.drop_column("permit_records", "is_active")
    op.drop_column("permit_records", "last_seen_snapshot_id")
