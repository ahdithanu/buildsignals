"""Add daily rollups for AI workflow usage."""

import sqlalchemy as sa

from alembic import op

revision = "20260928_0006"
down_revision = "20260928_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_workflow_usage_daily_rollups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("workflow", sa.String(32), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(200), nullable=False),
        sa.Column("total_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_results", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("known_cost_results", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("known_token_results", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("known_latency_results", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens_input", sa.Integer()),
        sa.Column("total_tokens_output", sa.Integer()),
        sa.Column("total_latency_ms", sa.Float()),
        sa.Column("total_cost_usd", sa.Float()),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "organization_id",
            "usage_date",
            "workflow",
            "model",
            "prompt_version",
            name="uq_ai_workflow_usage_daily_rollup_bucket",
        ),
    )
    op.create_index(
        "ix_ai_workflow_usage_daily_rollups_organization_id",
        "ai_workflow_usage_daily_rollups",
        ["organization_id"],
    )
    op.create_index(
        "ix_ai_workflow_usage_daily_org_date",
        "ai_workflow_usage_daily_rollups",
        ["organization_id", "usage_date"],
    )
    op.create_index(
        "ix_ai_workflow_usage_daily_org_workflow",
        "ai_workflow_usage_daily_rollups",
        ["organization_id", "workflow"],
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('ALTER TABLE "ai_workflow_usage_daily_rollups" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "ai_workflow_usage_daily_rollups" FORCE ROW LEVEL SECURITY')
        op.execute(
            'CREATE POLICY tenant_isolation ON "ai_workflow_usage_daily_rollups" '
            "USING (organization_id = current_setting('app.current_org', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org', true))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation ON "ai_workflow_usage_daily_rollups"')
    op.drop_index("ix_ai_workflow_usage_daily_org_workflow", table_name="ai_workflow_usage_daily_rollups")
    op.drop_index("ix_ai_workflow_usage_daily_org_date", table_name="ai_workflow_usage_daily_rollups")
    op.drop_index(
        "ix_ai_workflow_usage_daily_rollups_organization_id",
        table_name="ai_workflow_usage_daily_rollups",
    )
    op.drop_table("ai_workflow_usage_daily_rollups")
