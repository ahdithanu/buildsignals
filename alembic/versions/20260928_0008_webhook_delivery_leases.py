"""Add webhook delivery worker leases."""

import sqlalchemy as sa
from alembic import op

revision = "20260928_0008"
down_revision = "20260928_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("webhook_deliveries", sa.Column("lease_owner", sa.String(length=120), nullable=True))
    op.add_column("webhook_deliveries", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_webhook_deliveries_lease",
        "webhook_deliveries",
        ["organization_id", "status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_deliveries_lease", table_name="webhook_deliveries")
    op.drop_column("webhook_deliveries", "lease_expires_at")
    op.drop_column("webhook_deliveries", "lease_owner")
