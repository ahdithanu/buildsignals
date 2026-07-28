"""Add pre-approval lifecycle and filing context.

Revision ID: 20260716_0002
Revises: 20260716_0001
Create Date: 2026-07-16
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0002"
down_revision: Union[str, None] = "20260716_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("permit_records", sa.Column("application_number", sa.String(255)))
    op.add_column("permit_records", sa.Column("approval_stage", sa.String(32)))
    op.add_column("permit_records", sa.Column("work_class", sa.String(255)))
    op.add_column("permit_records", sa.Column("review_type", sa.String(255)))
    op.add_column("permit_records", sa.Column("proposed_use", sa.String(255)))
    op.add_column("permit_records", sa.Column("occupancy_type", sa.String(255)))
    op.add_column("permit_records", sa.Column("status_updated_at", sa.DateTime(timezone=True)))
    op.add_column("permit_records", sa.Column("approved_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_permit_record_org_approval_stage",
        "permit_records",
        ["organization_id", "approval_stage"],
    )
    op.add_column("permit_events", sa.Column("approval_stage", sa.String(32)))


def downgrade() -> None:
    op.drop_column("permit_events", "approval_stage")
    op.drop_index("ix_permit_record_org_approval_stage", table_name="permit_records")
    op.drop_column("permit_records", "approved_at")
    op.drop_column("permit_records", "status_updated_at")
    op.drop_column("permit_records", "occupancy_type")
    op.drop_column("permit_records", "proposed_use")
    op.drop_column("permit_records", "review_type")
    op.drop_column("permit_records", "work_class")
    op.drop_column("permit_records", "approval_stage")
    op.drop_column("permit_records", "application_number")
