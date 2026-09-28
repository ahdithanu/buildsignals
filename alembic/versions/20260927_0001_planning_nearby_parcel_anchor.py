"""Allow nearby parcel searches to anchor on planning records."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260927_0001"
down_revision = "20260923_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("nearby_parcel_searches") as batch:
        batch.add_column(sa.Column("anchor_planning_id", sa.String(36), nullable=True))
        batch.alter_column("anchor_permit_id", existing_type=sa.String(36), nullable=True)
        batch.create_foreign_key(
            "fk_nearby_parcel_searches_anchor_planning_id",
            "planning_records",
            ["anchor_planning_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            "ck_nearby_parcel_search_one_anchor",
            "(anchor_permit_id IS NOT NULL AND anchor_planning_id IS NULL) "
            "OR (anchor_permit_id IS NULL AND anchor_planning_id IS NOT NULL)",
        )
    op.create_index(
        "ix_nearby_parcel_search_planning",
        "nearby_parcel_searches",
        ["anchor_planning_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_nearby_parcel_search_planning", table_name="nearby_parcel_searches")
    with op.batch_alter_table("nearby_parcel_searches") as batch:
        batch.drop_constraint("ck_nearby_parcel_search_one_anchor", type_="check")
        batch.drop_constraint("fk_nearby_parcel_searches_anchor_planning_id", type_="foreignkey")
        batch.alter_column("anchor_permit_id", existing_type=sa.String(36), nullable=False)
        batch.drop_column("anchor_planning_id")
