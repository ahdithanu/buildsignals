"""Add durable ingestion run leases and heartbeats.

Revision ID: 20260716_0004
Revises: 20260716_0003
Create Date: 2026-07-16
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0004"
down_revision: Union[str, None] = "20260716_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ingestion_runs",
        sa.Column(
            "heartbeat_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY source_id ORDER BY started_at DESC, id DESC
                   ) AS row_number
            FROM ingestion_runs
            WHERE status = 'running'
        )
        UPDATE ingestion_runs
        SET status = 'failed',
            completed_at = CURRENT_TIMESTAMP,
            error_message = 'Superseded while adding ingestion run lease enforcement'
        WHERE id IN (SELECT id FROM ranked WHERE row_number > 1)
        """
    )
    op.create_index(
        "uq_ingestion_run_source_running",
        "ingestion_runs",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
        sqlite_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("uq_ingestion_run_source_running", table_name="ingestion_runs")
    op.drop_column("ingestion_runs", "heartbeat_at")
