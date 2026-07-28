"""Add persisted candidate canary attempts.

Revision ID: 20260723_0001
Revises: 20260716_0008
Create Date: 2026-07-23
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260723_0001"
down_revision: Union[str, None] = "20260716_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_candidate_canary_attempts",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_key", sa.String(length=120), nullable=False),
        sa.Column("candidate_name", sa.String(length=255), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("records_fetched", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("records_valid", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("records_failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("approval_stages", sa.JSON(), nullable=False),
        sa.Column("sample_record_ids", sa.JSON(), nullable=False),
        sa.Column("next_checkpoint", sa.JSON(), nullable=True),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ingestion_candidate_canary_candidate_created",
        "ingestion_candidate_canary_attempts",
        ["candidate_key", "created_at"],
    )
    op.create_index(
        "ix_ingestion_candidate_canary_org_created",
        "ingestion_candidate_canary_attempts",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ingestion_candidate_canary_org_created",
        table_name="ingestion_candidate_canary_attempts",
    )
    op.drop_index(
        "ix_ingestion_candidate_canary_candidate_created",
        table_name="ingestion_candidate_canary_attempts",
    )
    op.drop_table("ingestion_candidate_canary_attempts")
