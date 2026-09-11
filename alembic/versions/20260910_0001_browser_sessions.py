"""Persist independently revocable browser authentication families."""
import sqlalchemy as sa

from alembic import op

revision = "20260910_0001"
down_revision = "20260909_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "browser_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("browser_id", sa.String(36), nullable=False, unique=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("client_epoch", sa.BigInteger(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("user_id", "organization_id", "expires_at"):
        op.create_index(f"ix_browser_sessions_{column}", "browser_sessions", [column])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM browser_sessions")).scalar():
        raise RuntimeError("Refusing to discard browser revocation history; plan an explicit authentication rollback")
    op.drop_table("browser_sessions")
