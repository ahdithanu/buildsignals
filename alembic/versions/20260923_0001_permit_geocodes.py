"""Store tenant-scoped derived permit geocodes without changing source snapshots."""
import sqlalchemy as sa
from alembic import op

revision = "20260923_0001"
down_revision = "20260921_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "permit_geocodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("permit_id", sa.String(36), sa.ForeignKey("permit_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("address_hash", sa.String(64), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("matched_address", sa.String(500), nullable=False),
        sa.Column("benchmark", sa.String(100), nullable=False),
        sa.Column("source_url", sa.String(2000), nullable=False),
        sa.Column("response_hash", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "permit_id", name="uq_permit_geocodes_org_permit"),
    )
    op.create_index("ix_permit_geocodes_organization_id", "permit_geocodes", ["organization_id"])
    op.create_index("ix_permit_geocodes_permit_id", "permit_geocodes", ["permit_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE permit_geocodes ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE permit_geocodes FORCE ROW LEVEL SECURITY")
        op.execute("CREATE POLICY tenant_isolation ON permit_geocodes "
                   "USING (organization_id = current_setting('app.current_org', true)) "
                   "WITH CHECK (organization_id = current_setting('app.current_org', true))")


def downgrade():
    op.drop_table("permit_geocodes")
