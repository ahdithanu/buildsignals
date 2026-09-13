"""Add encrypted MFA storage without rewriting secrets during schema migration."""
import sqlalchemy as sa

from alembic import op

revision = "20260909_0001"
down_revision = "20260908_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("totp_secret_ciphertext", sa.Text(), nullable=True))


def downgrade():
    count = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM users WHERE totp_secret_ciphertext IS NOT NULL"
    )).scalar_one()
    if count:
        raise RuntimeError("Encrypted MFA enrollments exist; refusing destructive downgrade")
    op.drop_column("users", "totp_secret_ciphertext")
