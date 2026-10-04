"""Append-only application records connecting excerpts to screening criteria."""
import sqlalchemy as sa

from alembic import op

revision = "20260921_0003"
down_revision = "20260921_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "diligence_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("criterion", sa.String(40), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("organization_id", "deal_id", "document_id"):
        op.create_index(f"ix_diligence_reviews_{column}", "diligence_reviews", [column])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE diligence_reviews ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE diligence_reviews FORCE ROW LEVEL SECURITY")
        op.execute("CREATE POLICY tenant_isolation ON diligence_reviews "
                   "USING (organization_id = current_setting('app.current_org', true)) "
                   "WITH CHECK (organization_id = current_setting('app.current_org', true))")


def downgrade():
    op.drop_table("diligence_reviews")
