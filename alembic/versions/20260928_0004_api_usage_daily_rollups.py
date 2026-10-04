"""Add daily rollups for organization API key usage."""

import sqlalchemy as sa

from alembic import op

revision = "20260928_0004"
down_revision = "20260928_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_api_key_usage_daily_rollups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("api_key_id", sa.String(36), sa.ForeignKey("organization_api_keys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("method", sa.String(12), nullable=False),
        sa.Column("path", sa.String(240), nullable=False),
        sa.Column("total_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_status_code", sa.Integer()),
        sa.Column("last_called_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "organization_id",
            "api_key_id",
            "usage_date",
            "method",
            "path",
            name="uq_api_key_usage_daily_rollup_bucket",
        ),
    )
    op.create_index(
        "ix_organization_api_key_usage_daily_rollups_organization_id",
        "organization_api_key_usage_daily_rollups",
        ["organization_id"],
    )
    op.create_index(
        "ix_organization_api_key_usage_daily_rollups_api_key_id",
        "organization_api_key_usage_daily_rollups",
        ["api_key_id"],
    )
    op.create_index(
        "ix_api_key_usage_daily_rollups_org_date",
        "organization_api_key_usage_daily_rollups",
        ["organization_id", "usage_date"],
    )
    op.create_index(
        "ix_api_key_usage_daily_rollups_key_date",
        "organization_api_key_usage_daily_rollups",
        ["api_key_id", "usage_date"],
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('ALTER TABLE "organization_api_key_usage_daily_rollups" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "organization_api_key_usage_daily_rollups" FORCE ROW LEVEL SECURITY')
        op.execute(
            'CREATE POLICY tenant_isolation ON "organization_api_key_usage_daily_rollups" '
            "USING (organization_id = current_setting('app.current_org', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org', true))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation ON "organization_api_key_usage_daily_rollups"')
    op.drop_index("ix_api_key_usage_daily_rollups_key_date", table_name="organization_api_key_usage_daily_rollups")
    op.drop_index("ix_api_key_usage_daily_rollups_org_date", table_name="organization_api_key_usage_daily_rollups")
    op.drop_index(
        "ix_organization_api_key_usage_daily_rollups_api_key_id",
        table_name="organization_api_key_usage_daily_rollups",
    )
    op.drop_index(
        "ix_organization_api_key_usage_daily_rollups_organization_id",
        table_name="organization_api_key_usage_daily_rollups",
    )
    op.drop_table("organization_api_key_usage_daily_rollups")
