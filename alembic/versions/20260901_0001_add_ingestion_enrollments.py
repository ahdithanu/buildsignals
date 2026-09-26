"""Add organization ingestion enrollments.

Revision ID: 20260901_0001
Revises: 20260825_0001
Create Date: 2026-09-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260901_0001"
down_revision: Union[str, None] = "20260825_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_TABLES = (
    "organization_ingestion_enrollments",
    "organization_ingestion_enrollment_sources",
)
POLICY_NAME = "tenant_isolation"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls() -> None:
    if not _is_postgres():
        return
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}"')
        op.execute(
            f"""
            CREATE POLICY {POLICY_NAME} ON "{table}"
                USING (organization_id = current_setting('app.current_org', true))
                WITH CHECK (organization_id = current_setting('app.current_org', true))
            """
        )


def _disable_rls() -> None:
    if not _is_postgres():
        return
    for table in reversed(TENANT_TABLES):
        op.execute(f'DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


def upgrade() -> None:
    op.create_table(
        "organization_ingestion_enrollments",
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "coverage_mode",
            sa.String(32),
            nullable=False,
            server_default="nationwide",
        ),
        sa.Column("state_codes", sa.JSON()),
        sa.Column("record_types", sa.JSON(), nullable=False),
        sa.Column("rollout_waves", sa.JSON(), nullable=False),
        sa.Column("shard_count", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("catalog_manifest_digest", sa.String(64), nullable=False),
        sa.Column("last_catalog_sync_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_dispatch_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ingestion_enrollments_enabled",
        "organization_ingestion_enrollments",
        ["enabled", "organization_id"],
    )
    op.create_table(
        "organization_ingestion_enrollment_sources",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey(
                "organization_ingestion_enrollments.organization_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "ingestion_source_id",
            sa.String(36),
            sa.ForeignKey("ingestion_sources.id", ondelete="SET NULL"),
        ),
        sa.Column("source_key", sa.String(100), nullable=False),
        sa.Column("state_code", sa.String(2), nullable=False),
        sa.Column("record_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("cadence_minutes", sa.Integer(), nullable=False),
        sa.Column("max_pages_per_run", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.String(64)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("last_completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("cadence_minutes > 0", name="ck_enrollment_source_cadence"),
        sa.CheckConstraint(
            "max_pages_per_run BETWEEN 1 AND 100",
            name="ck_enrollment_source_max_pages",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "source_key",
            name="uq_ingestion_enrollment_source_org_key",
        ),
    )
    op.create_index(
        "ix_ingestion_enrollment_sources_due",
        "organization_ingestion_enrollment_sources",
        ["status", "next_run_at", "organization_id"],
    )
    op.create_index(
        "ix_ingestion_enrollment_sources_org_status",
        "organization_ingestion_enrollment_sources",
        ["organization_id", "status"],
    )
    _enable_rls()


def downgrade() -> None:
    _disable_rls()
    op.drop_index(
        "ix_ingestion_enrollment_sources_org_status",
        table_name="organization_ingestion_enrollment_sources",
    )
    op.drop_index(
        "ix_ingestion_enrollment_sources_due",
        table_name="organization_ingestion_enrollment_sources",
    )
    op.drop_table("organization_ingestion_enrollment_sources")
    op.drop_index(
        "ix_ingestion_enrollments_enabled",
        table_name="organization_ingestion_enrollments",
    )
    op.drop_table("organization_ingestion_enrollments")
