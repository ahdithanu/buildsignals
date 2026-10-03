"""Add optional structured acquisition criteria to tenant-scoped buy boxes."""
import sqlalchemy as sa

from alembic import op

revision = "20260920_0001"
down_revision = "20260919_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("buy_boxes", sa.Column("acquisition_criteria", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("buy_boxes", "acquisition_criteria")
