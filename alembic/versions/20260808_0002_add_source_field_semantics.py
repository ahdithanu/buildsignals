"""Add semantic classifications to source field mappings.

Revision ID: 20260808_0002
Revises: 20260808_0001
Create Date: 2026-08-08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260808_0002"
down_revision: Union[str, None] = "20260808_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "source_field_mappings",
        sa.Column("value_semantics", sa.String(32), server_default="unknown", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("source_field_mappings", "value_semantics")
