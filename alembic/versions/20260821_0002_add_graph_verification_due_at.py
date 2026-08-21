"""Add indexed relationship verification due dates.

Revision ID: 20260821_0002
Revises: 20260821_0001
Create Date: 2026-08-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0002"
down_revision: Union[str, None] = "20260821_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "graph_relationships",
        sa.Column("verification_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "UPDATE graph_relationships "
            "SET verification_due_at = datetime(last_verified_at, '+90 days')"
        )
    else:
        op.execute(
            "UPDATE graph_relationships "
            "SET verification_due_at = last_verified_at + INTERVAL '90 days'"
        )
    with op.batch_alter_table("graph_relationships") as batch_op:
        batch_op.alter_column("verification_due_at", nullable=False)
    op.create_index(
        "ix_graph_relationship_verification_queue",
        "graph_relationships",
        ["organization_id", "is_current", "verification_due_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_graph_relationship_verification_queue",
        table_name="graph_relationships",
    )
    with op.batch_alter_table("graph_relationships") as batch_op:
        batch_op.drop_column("verification_due_at")
