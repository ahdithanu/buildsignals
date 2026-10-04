"""Store bounded analyst-provided excerpts separately from document metadata."""
import sqlalchemy as sa

from alembic import op

revision = "20260921_0002"
down_revision = "20260921_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("evidence_excerpt", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("documents", "evidence_excerpt")
