"""Track explicit assessment publication and withdrawal events."""
import sqlalchemy as sa

from alembic import op

revision = "20260908_0001"
down_revision = "20260907_0001"
branch_labels = None
depends_on = None


def upgrade():
    table = "buildsignal_publications"
    op.create_table(
        table,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("buildsignal_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("review_id", sa.String(36), sa.ForeignKey("buildsignal_reviews.id", ondelete="SET NULL")),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("revision_id", "version", name="uq_publication_revision_version"),
    )
    for column in ("organization_id", "revision_id"):
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
    op.drop_table("buildsignal_publications")
