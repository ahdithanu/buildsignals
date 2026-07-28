"""Add generic permit ingestion persistence.

Revision ID: 20260716_0001
Revises: 20260704_0001
Create Date: 2026-07-16
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0001"
down_revision: Union[str, None] = "20260704_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_TABLES: tuple[str, ...] = (
    "ingestion_sources",
    "source_field_mappings",
    "ingestion_runs",
    "raw_source_records",
    "permit_records",
    "permit_events",
)


def _tenant_column() -> sa.Column:
    return sa.Column(
        "organization_id",
        sa.String(length=36),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )


def _timestamps(*, updated: bool = False) -> list[sa.Column]:
    columns = [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
    ]
    if updated:
        columns.append(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
    return columns


def upgrade() -> None:
    op.create_table(
        "ingestion_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("adapter", sa.String(length=100), nullable=False),
        sa.Column("record_type", sa.String(length=100), nullable=False, server_default="permit"),
        sa.Column("jurisdiction", sa.String(length=255), nullable=True),
        sa.Column("base_url", sa.String(length=1000), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(updated=True),
        _tenant_column(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "key", name="uq_ingestion_source_org_key"),
    )
    op.create_index("ix_ingestion_sources_organization_id", "ingestion_sources", ["organization_id"])
    op.create_index(
        "ix_ingestion_source_org_active", "ingestion_sources", ["organization_id", "is_active"]
    )

    op.create_table(
        "source_field_mappings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("source_field", sa.String(length=255), nullable=False),
        sa.Column("canonical_field", sa.String(length=255), nullable=False),
        sa.Column("transform", sa.String(length=100), nullable=True),
        sa.Column("transform_options", sa.JSON(), nullable=True),
        sa.Column("default_value", sa.JSON(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(updated=True),
        _tenant_column(),
        sa.ForeignKeyConstraint(["source_id"], ["ingestion_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "source_field", name="uq_source_field_mapping"),
    )
    op.create_index(
        "ix_source_field_mappings_organization_id", "source_field_mappings", ["organization_id"]
    )
    op.create_index(
        "ix_source_field_mapping_canonical",
        "source_field_mappings",
        ["source_id", "canonical_field"],
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("trigger", sa.String(length=50), nullable=False, server_default="scheduled"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checkpoint", sa.JSON(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("records_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_timestamps(),
        _tenant_column(),
        sa.ForeignKeyConstraint(["source_id"], ["ingestion_sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_runs_organization_id", "ingestion_runs", ["organization_id"])
    op.create_index(
        "ix_ingestion_run_source_started", "ingestion_runs", ["source_id", "started_at"]
    )
    op.create_index(
        "ix_ingestion_run_org_status", "ingestion_runs", ["organization_id", "status"]
    )

    op.create_table(
        "raw_source_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("external_record_id", sa.String(length=500), nullable=False),
        sa.Column("record_type", sa.String(length=100), nullable=False, server_default="permit"),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        _tenant_column(),
        sa.ForeignKeyConstraint(["run_id"], ["ingestion_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_id"], ["ingestion_sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "external_record_id",
            "content_hash",
            name="uq_raw_source_record_version",
        ),
    )
    op.create_index("ix_raw_source_records_organization_id", "raw_source_records", ["organization_id"])
    op.create_index(
        "ix_raw_source_record_lookup",
        "raw_source_records",
        ["source_id", "external_record_id", "received_at"],
    )
    op.create_index(
        "ix_raw_source_record_run", "raw_source_records", ["run_id", "received_at"]
    )

    op.create_table(
        "permit_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("latest_raw_record_id", sa.String(length=36), nullable=False),
        sa.Column("external_record_id", sa.String(length=500), nullable=False),
        sa.Column("normalization_hash", sa.String(length=64), nullable=False),
        sa.Column("permit_number", sa.String(length=255), nullable=True),
        sa.Column("permit_type", sa.String(length=255), nullable=True),
        sa.Column("permit_subtype", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_name", sa.String(length=500), nullable=True),
        sa.Column("address", sa.String(length=1000), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=50), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("parcel_id", sa.String(length=255), nullable=True),
        sa.Column("jurisdiction", sa.String(length=255), nullable=True),
        sa.Column("applicant_name", sa.String(length=500), nullable=True),
        sa.Column("owner_name", sa.String(length=500), nullable=True),
        sa.Column("developer_name", sa.String(length=500), nullable=True),
        sa.Column("contractor_name", sa.String(length=500), nullable=True),
        sa.Column("contractor_license", sa.String(length=255), nullable=True),
        sa.Column("architect_name", sa.String(length=500), nullable=True),
        sa.Column("engineer_name", sa.String(length=500), nullable=True),
        sa.Column("valuation", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("square_feet", sa.Integer(), nullable=True),
        sa.Column("units", sa.Integer(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_url", sa.String(length=2000), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        *_timestamps(updated=True),
        _tenant_column(),
        sa.ForeignKeyConstraint(
            ["latest_raw_record_id"], ["raw_source_records.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["ingestion_sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id", "external_record_id", name="uq_permit_record_source_external"
        ),
    )
    op.create_index("ix_permit_records_organization_id", "permit_records", ["organization_id"])
    op.create_index(
        "ix_permit_record_org_number", "permit_records", ["organization_id", "permit_number"]
    )
    op.create_index(
        "ix_permit_record_org_status", "permit_records", ["organization_id", "status"]
    )
    op.create_index(
        "ix_permit_record_location",
        "permit_records",
        ["organization_id", "state", "city", "postal_code"],
    )
    op.create_index(
        "ix_permit_record_parcel", "permit_records", ["organization_id", "parcel_id"]
    )

    op.create_table(
        "permit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("permit_id", sa.String(length=36), nullable=False),
        sa.Column("raw_source_record_id", sa.String(length=36), nullable=False),
        sa.Column("source_event_id", sa.String(length=500), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=100), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=True),
        *_timestamps(),
        _tenant_column(),
        sa.ForeignKeyConstraint(["permit_id"], ["permit_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["raw_source_record_id"], ["raw_source_records.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("permit_id", "source_event_id", name="uq_permit_event_source_event"),
    )
    op.create_index("ix_permit_events_organization_id", "permit_events", ["organization_id"])
    op.create_index(
        "ix_permit_event_timeline", "permit_events", ["permit_id", "occurred_at"]
    )
    op.create_index(
        "ix_permit_event_org_type", "permit_events", ["organization_id", "event_type"]
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in TENANT_TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(
                f"""
                CREATE POLICY tenant_isolation ON "{table}"
                    USING (organization_id = current_setting('app.current_org', true))
                    WITH CHECK (organization_id = current_setting('app.current_org', true))
                """
            )


def downgrade() -> None:
    op.drop_index("ix_permit_event_org_type", table_name="permit_events")
    op.drop_index("ix_permit_event_timeline", table_name="permit_events")
    op.drop_index("ix_permit_events_organization_id", table_name="permit_events")
    op.drop_table("permit_events")

    op.drop_index("ix_permit_record_parcel", table_name="permit_records")
    op.drop_index("ix_permit_record_location", table_name="permit_records")
    op.drop_index("ix_permit_record_org_status", table_name="permit_records")
    op.drop_index("ix_permit_record_org_number", table_name="permit_records")
    op.drop_index("ix_permit_records_organization_id", table_name="permit_records")
    op.drop_table("permit_records")

    op.drop_index("ix_raw_source_record_run", table_name="raw_source_records")
    op.drop_index("ix_raw_source_record_lookup", table_name="raw_source_records")
    op.drop_index("ix_raw_source_records_organization_id", table_name="raw_source_records")
    op.drop_table("raw_source_records")

    op.drop_index("ix_ingestion_run_org_status", table_name="ingestion_runs")
    op.drop_index("ix_ingestion_run_source_started", table_name="ingestion_runs")
    op.drop_index("ix_ingestion_runs_organization_id", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")

    op.drop_index("ix_source_field_mapping_canonical", table_name="source_field_mappings")
    op.drop_index("ix_source_field_mappings_organization_id", table_name="source_field_mappings")
    op.drop_table("source_field_mappings")

    op.drop_index("ix_ingestion_source_org_active", table_name="ingestion_sources")
    op.drop_index("ix_ingestion_sources_organization_id", table_name="ingestion_sources")
    op.drop_table("ingestion_sources")
