"""Add organization API key usage metering."""

import sqlalchemy as sa

from alembic import op

revision = "20260928_0002"
down_revision = "20260928_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_api_key_usage_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("api_key_id", sa.String(36), sa.ForeignKey("organization_api_keys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("method", sa.String(12), nullable=False),
        sa.Column("path", sa.String(240), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_items", sa.Integer()),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_organization_api_key_usage_events_organization_id", "organization_api_key_usage_events", ["organization_id"])
    op.create_index("ix_organization_api_key_usage_events_api_key_id", "organization_api_key_usage_events", ["api_key_id"])
    op.create_index("ix_api_key_usage_org_created", "organization_api_key_usage_events", ["organization_id", "created_at"])
    op.create_index("ix_api_key_usage_key_created", "organization_api_key_usage_events", ["api_key_id", "created_at"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "organization_api_key_usage_events" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "organization_api_key_usage_events" FORCE ROW LEVEL SECURITY')
        op.execute(
            'CREATE POLICY tenant_isolation ON "organization_api_key_usage_events" '
            "USING (organization_id = current_setting('app.current_org', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org', true))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation ON "organization_api_key_usage_events"')
    op.drop_index("ix_api_key_usage_key_created", table_name="organization_api_key_usage_events")
    op.drop_index("ix_api_key_usage_org_created", table_name="organization_api_key_usage_events")
    op.drop_index("ix_organization_api_key_usage_events_api_key_id", table_name="organization_api_key_usage_events")
    op.drop_index("ix_organization_api_key_usage_events_organization_id", table_name="organization_api_key_usage_events")
    op.drop_table("organization_api_key_usage_events")
