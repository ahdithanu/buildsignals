"""Add expiration metadata for organization API keys."""

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from alembic import op

revision = "20260928_0003"
down_revision = "20260928_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organization_api_keys", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.create_index("ix_organization_api_keys_expires_at", "organization_api_keys", ["expires_at"])
    default_expiration = datetime.now(timezone.utc) + timedelta(days=90)
    op.execute(
        sa.text("UPDATE organization_api_keys SET expires_at = :expires_at WHERE expires_at IS NULL").bindparams(
            expires_at=default_expiration,
        )
    )


def downgrade() -> None:
    op.drop_index("ix_organization_api_keys_expires_at", table_name="organization_api_keys")
    op.drop_column("organization_api_keys", "expires_at")
