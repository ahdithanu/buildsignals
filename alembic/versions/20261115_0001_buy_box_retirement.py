"""Retain structured acquisition criteria while retiring their active use."""

import sqlalchemy as sa

from alembic import op

revision = "20261115_0001"
down_revision = "20260928_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("buy_boxes", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("buy_boxes", "retired_at")
