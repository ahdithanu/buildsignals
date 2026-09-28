"""Add organization-scoped API key lifecycle table."""

import sqlalchemy as sa

from alembic import op

revision = "20260928_0001"
down_revision = "20260924_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("key_prefix", sa.String(24), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("key_hash", name="uq_organization_api_keys_key_hash"),
    )
    op.create_index("ix_organization_api_keys_organization_id", "organization_api_keys", ["organization_id"])
    op.create_index("ix_organization_api_keys_key_prefix", "organization_api_keys", ["key_prefix"])
    op.create_index("ix_organization_api_keys_active", "organization_api_keys", ["organization_id", "revoked_at"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "organization_api_keys" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "organization_api_keys" FORCE ROW LEVEL SECURITY')
        op.execute(
            'CREATE POLICY tenant_isolation ON "organization_api_keys" '
            "USING (organization_id = current_setting('app.current_org', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org', true))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation ON "organization_api_keys"')
    op.drop_index("ix_organization_api_keys_active", table_name="organization_api_keys")
    op.drop_index("ix_organization_api_keys_key_prefix", table_name="organization_api_keys")
    op.drop_index("ix_organization_api_keys_organization_id", table_name="organization_api_keys")
    op.drop_table("organization_api_keys")
