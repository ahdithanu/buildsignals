"""Persist assessment snapshots and revision-specific reviews."""
import sqlalchemy as sa

from alembic import op

revision = "20260907_0001"
down_revision = "20260901_0001"
branch_labels = None
depends_on = None


def upgrade():
    for table, parent, reference, actor, extra in (
        ("buildsignal_revisions", "signals", "signal_id", "author_id",
         [sa.Column("snapshot", sa.JSON(), nullable=False)]),
        ("buildsignal_reviews", "buildsignal_revisions", "revision_id", "reviewer_id",
         [sa.Column("decision", sa.String(32), nullable=False),
          sa.Column("rationale", sa.Text(), nullable=False)]),
    ):
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column(reference, sa.String(36), sa.ForeignKey(f"{parent}.id", ondelete="CASCADE"), nullable=False),
            sa.Column(actor, sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            *extra,
        )
        for column in ("organization_id", reference):
            op.create_index(f"ix_{table}_{column}", table, [column])
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(
                f'CREATE POLICY tenant_isolation ON "{table}" '
                "USING (organization_id = current_setting('app.current_org', true)) "
                "WITH CHECK (organization_id = current_setting('app.current_org', true))"
            )


def downgrade():
    op.drop_table("buildsignal_reviews")
    op.drop_table("buildsignal_revisions")
