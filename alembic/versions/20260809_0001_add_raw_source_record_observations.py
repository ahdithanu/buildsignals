"""Track observations of immutable raw source record versions.

Revision ID: 20260809_0001
Revises: 20260808_0002
Create Date: 2026-08-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260809_0001"
down_revision: Union[str, None] = "20260808_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("parcel_facts") as batch_op:
        batch_op.drop_constraint("uq_parcel_fact_source_version", type_="unique")
        batch_op.create_unique_constraint(
            "uq_parcel_fact_source_occurrence",
            ["parcel_id", "fact_type", "raw_source_record_id", "valid_from"],
        )
    op.create_index(
        "uq_raw_source_record_id_org",
        "raw_source_records",
        ["id", "organization_id"],
        unique=True,
    )
    op.create_table(
        "raw_source_record_observations",
        sa.Column("raw_source_record_id", sa.String(length=36), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["raw_source_record_id", "organization_id"],
            ["raw_source_records.id", "raw_source_records.organization_id"],
            ondelete="CASCADE",
            name="fk_raw_observation_record_org",
        ),
        sa.PrimaryKeyConstraint("raw_source_record_id"),
    )
    op.create_index(
        "ix_raw_source_record_observations_organization_id",
        "raw_source_record_observations",
        ["organization_id"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "raw_source_records" NO FORCE ROW LEVEL SECURITY')
    op.execute(
        sa.text(
            """INSERT INTO raw_source_record_observations
            (raw_source_record_id, last_observed_at, organization_id)
            SELECT id, received_at, organization_id FROM raw_source_records"""
        )
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "raw_source_records" FORCE ROW LEVEL SECURITY')
        op.execute(
            'ALTER TABLE "raw_source_record_observations" ENABLE ROW LEVEL SECURITY'
        )
        op.execute(
            'ALTER TABLE "raw_source_record_observations" FORCE ROW LEVEL SECURITY'
        )
        op.execute(
            """CREATE POLICY tenant_isolation ON "raw_source_record_observations"
            USING (organization_id = current_setting('app.current_org', true))
            WITH CHECK (organization_id = current_setting('app.current_org', true))"""
        )


def downgrade() -> None:
    op.drop_index(
        "ix_raw_source_record_observations_organization_id",
        table_name="raw_source_record_observations",
    )
    op.drop_table("raw_source_record_observations")
    op.drop_index(
        "uq_raw_source_record_id_org",
        table_name="raw_source_records",
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "parcel_facts" NO FORCE ROW LEVEL SECURITY')
    op.execute(
        sa.text(
            """DELETE FROM parcel_facts WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY parcel_id, fact_type, raw_source_record_id
                    ORDER BY valid_from DESC, created_at DESC, id DESC
                ) AS occurrence_rank
                FROM parcel_facts
            ) ranked WHERE occurrence_rank > 1
            )"""
        )
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "parcel_facts" FORCE ROW LEVEL SECURITY')
    with op.batch_alter_table("parcel_facts") as batch_op:
        batch_op.drop_constraint("uq_parcel_fact_source_occurrence", type_="unique")
        batch_op.create_unique_constraint(
            "uq_parcel_fact_source_version",
            ["parcel_id", "fact_type", "raw_source_record_id"],
        )
