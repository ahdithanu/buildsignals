"""Preserve long public agenda titles without narrowing their source evidence."""
import sqlalchemy as sa

from alembic import op

revision = "20260911_0001"
down_revision = "20260910_0001"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite does not enforce VARCHAR lengths; avoid rebuilding a referenced
    # table there. PostgreSQL needs the wider type before importing long titles.
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column(
            "planning_records", "title", existing_type=sa.String(1000),
            type_=sa.Text(), existing_nullable=False,
        )


def downgrade():
    count = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM planning_records WHERE length(title) > 1000"
    )).scalar_one()
    if count:
        raise RuntimeError("Long planning titles exist; refusing a data-losing downgrade")
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column(
            "planning_records", "title", existing_type=sa.Text(),
            type_=sa.String(1000), existing_nullable=False,
        )
