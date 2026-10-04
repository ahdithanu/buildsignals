"""Persist exact acquisition export snapshots with forced tenant isolation."""
import sqlalchemy as sa

from alembic import op

revision = "20260921_0001"
down_revision = "20260920_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "acquisition_screen_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_acquisition_screen_snapshots_organization_id", "acquisition_screen_snapshots", ["organization_id"])
    op.create_index("ix_acquisition_screen_history", "acquisition_screen_snapshots", ["organization_id", "deal_id", "created_at", "id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE acquisition_screen_snapshots ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE acquisition_screen_snapshots FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_isolation ON acquisition_screen_snapshots "
            "USING (organization_id = current_setting('app.current_org', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org', true))"
        )


def downgrade():
    op.drop_table("acquisition_screen_snapshots")
