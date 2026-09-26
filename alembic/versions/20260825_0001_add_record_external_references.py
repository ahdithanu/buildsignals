"""Add indexed external record references.

Revision ID: 20260825_0001
Revises: 20260822_0001
Create Date: 2026-08-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260825_0001"
down_revision: Union[str, None] = "20260822_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "record_external_references",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("record_type", sa.String(100), nullable=False),
        sa.Column("record_id", sa.String(36), nullable=False),
        sa.Column(
            "raw_source_record_id",
            sa.String(36),
            sa.ForeignKey("raw_source_records.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("namespace", sa.String(255), nullable=False),
        sa.Column("normalized_value", sa.String(500), nullable=False),
        sa.Column("source_field", sa.String(255), nullable=False),
        sa.Column("source_url", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "record_type",
            "record_id",
            "namespace",
            "normalized_value",
            name="uq_record_external_reference_identity",
        ),
    )
    op.create_index(
        "ix_record_external_references_organization_id",
        "record_external_references",
        ["organization_id"],
    )
    op.create_index(
        "ix_record_external_reference_lookup",
        "record_external_references",
        ["organization_id", "namespace", "normalized_value", "record_type"],
    )
    op.create_index(
        "ix_record_external_reference_record",
        "record_external_references",
        ["organization_id", "record_type", "record_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_record_external_reference_record",
        table_name="record_external_references",
    )
    op.drop_index(
        "ix_record_external_reference_lookup",
        table_name="record_external_references",
    )
    op.drop_index(
        "ix_record_external_references_organization_id",
        table_name="record_external_references",
    )
    op.drop_table("record_external_references")
