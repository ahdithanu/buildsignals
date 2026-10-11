"""Add webhook delivery idempotency guard."""

from alembic import op

revision = "20260928_0007"
down_revision = "20260928_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM webhook_deliveries
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY organization_id, subscription_id, event_type, event_id
                        ORDER BY created_at ASC, id ASC
                    ) AS duplicate_rank
                FROM webhook_deliveries
            ) ranked
            WHERE duplicate_rank > 1
        )
        """
    )
    op.create_index(
        "uq_webhook_delivery_idempotency_key",
        "webhook_deliveries",
        ["organization_id", "subscription_id", "event_type", "event_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_webhook_delivery_idempotency_key", table_name="webhook_deliveries")
