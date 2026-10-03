"""Add tenant-isolated AI evaluation datasets and execution history."""
import sqlalchemy as sa

from alembic import op

revision = "20260920_0001"
down_revision = "20260915_0001"
branch_labels = None
depends_on = None

_TABLES = ("eval_dataset", "eval_case", "eval_run", "eval_result", "eval_metric")


def _identity_columns():
    return (
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        ),
    )


def _parent_fk(table, column, parent):
    return sa.ForeignKeyConstraint(
        ["organization_id", column],
        [f"{parent}.organization_id", f"{parent}.id"],
        name=f"fk_{table}_{column.removesuffix('_id')}_org",
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "eval_dataset",
        *_identity_columns(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("workflow", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_eval_dataset_org_name"),
        sa.UniqueConstraint("organization_id", "id", name="uq_eval_dataset_org_id"),
        sa.CheckConstraint(
            "workflow IN ('copilot_answer', 'opportunity_memo', "
            "'multi_agent_research', 'score_explanation')",
            name="ck_eval_dataset_workflow",
        ),
    )
    op.create_table(
        "eval_case",
        *_identity_columns(),
        sa.Column("dataset_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("expected_output", sa.JSON(), nullable=False),
        sa.Column("retrieved_context", sa.JSON(), nullable=False),
        sa.Column("critical", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "id", name="uq_eval_case_org_id"),
        _parent_fk("eval_case", "dataset_id", "eval_dataset"),
    )
    op.create_table(
        "eval_run",
        *_identity_columns(),
        sa.Column("dataset_id", sa.String(36), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("dataset_fingerprint", sa.String(64), nullable=False),
        sa.Column("thresholds", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("gate_passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organization_id", "id", name="uq_eval_run_org_id"),
        _parent_fk("eval_run", "dataset_id", "eval_dataset"),
        sa.CheckConstraint("mode IN ('live', 'replay')", name="ck_eval_run_mode"),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_eval_run_status"),
    )
    op.create_table(
        "eval_result",
        *_identity_columns(),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("case_snapshot", sa.JSON(), nullable=False),
        sa.Column("actual_output", sa.JSON(none_as_null=True)),
        sa.Column("retrieved_context", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(200)),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(200), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("tokens_input", sa.Integer()),
        sa.Column("tokens_output", sa.Integer()),
        sa.Column("cost_usd", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "id", name="uq_eval_result_org_id"),
        sa.UniqueConstraint("run_id", "case_id", name="uq_eval_result_run_case"),
        _parent_fk("eval_result", "run_id", "eval_run"),
        _parent_fk("eval_result", "case_id", "eval_case"),
        sa.CheckConstraint("status IN ('passed', 'failed', 'error')", name="ck_eval_result_status"),
    )
    op.create_table(
        "eval_metric",
        *_identity_columns(),
        sa.Column("result_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.UniqueConstraint("result_id", "name", name="uq_eval_metric_result_name"),
        _parent_fk("eval_metric", "result_id", "eval_result"),
        sa.CheckConstraint("value >= 0 AND value <= 1", name="ck_eval_metric_normalized"),
    )
    for table in _TABLES:
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
    for table, column in (
        ("eval_case", "dataset_id"),
        ("eval_run", "dataset_id"),
        ("eval_run", "started_at"),
        ("eval_result", "run_id"),
        ("eval_result", "case_id"),
        ("eval_metric", "result_id"),
    ):
        op.create_index(
            f"ix_{table}_org_{column.removesuffix('_id')}", table, ["organization_id", column]
        )
    if op.get_bind().dialect.name == "postgresql":
        for table in _TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(
                f'CREATE POLICY tenant_isolation ON "{table}" '
                "USING (organization_id = current_setting('app.current_org', true)) "
                "WITH CHECK (organization_id = current_setting('app.current_org', true))"
            )


def downgrade() -> None:
    # Dropping each table also removes its indexes, constraints, and RLS policy.
    for table in reversed(_TABLES):
        op.drop_table(table)
