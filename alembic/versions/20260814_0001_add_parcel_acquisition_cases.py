"""Add canonical parcel acquisition cases and outreach provenance.

Revision ID: 20260814_0001
Revises: 20260809_0002
Create Date: 2026-08-14
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0001"
down_revision: Union[str, None] = "20260809_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "parcel_acquisition_cases",
    "parcel_acquisition_sources",
    "parcel_acquisition_activities",
)


def upgrade() -> None:
    op.create_table(
        "parcel_acquisition_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parcel_id",
            sa.String(36),
            sa.ForeignKey("parcel_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), server_default="candidate", nullable=False),
        sa.Column(
            "assigned_to_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("assigned_to_name", sa.String(255)),
        sa.Column(
            "assigned_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True)),
        sa.Column("contacted_at", sa.DateTime(timezone=True)),
        sa.Column("follow_up_at", sa.DateTime(timezone=True)),
        sa.Column(
            "promoted_deal_id",
            sa.String(36),
            sa.ForeignKey("deals.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "parcel_id", name="uq_parcel_acquisition_case_org_parcel"
        ),
    )
    op.create_index(
        "ix_parcel_acquisition_cases_organization_id",
        "parcel_acquisition_cases",
        ["organization_id"],
    )
    op.create_index(
        "ix_parcel_acquisition_case_org_status",
        "parcel_acquisition_cases",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_parcel_acquisition_case_org_assignee",
        "parcel_acquisition_cases",
        ["organization_id", "assigned_to_user_id"],
    )

    op.create_table(
        "parcel_acquisition_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            sa.String(36),
            sa.ForeignKey("parcel_acquisition_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("nearby_parcel_candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "search_id",
            sa.String(36),
            sa.ForeignKey("nearby_parcel_searches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "case_id",
            "candidate_id",
            name="uq_parcel_acquisition_source_candidate",
        ),
    )
    op.create_index(
        "ix_parcel_acquisition_sources_organization_id",
        "parcel_acquisition_sources",
        ["organization_id"],
    )
    op.create_index(
        "ix_parcel_acquisition_source_case",
        "parcel_acquisition_sources",
        ["organization_id", "case_id"],
    )

    op.create_table(
        "parcel_acquisition_activities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            sa.String(36),
            sa.ForeignKey("parcel_acquisition_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("activity_type", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "actor_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("follow_up_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_parcel_acquisition_activities_organization_id",
        "parcel_acquisition_activities",
        ["organization_id"],
    )
    op.create_index(
        "ix_parcel_acquisition_activity_case_occurred",
        "parcel_acquisition_activities",
        ["organization_id", "case_id", "occurred_at"],
    )

    _backfill_cases()
    if op.get_bind().dialect.name == "postgresql":
        for table in _TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(
                f"""
                CREATE POLICY tenant_isolation ON "{table}"
                    USING (organization_id = current_setting('app.current_org', true))
                    WITH CHECK (organization_id = current_setting('app.current_org', true))
                """
            )


def _backfill_cases() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("""
        SELECT c.organization_id, c.parcel_id, c.id AS candidate_id,
               c.search_id, c.review_status, c.assigned_to_user_id,
               c.assigned_to_name, c.assigned_by_user_id, c.assigned_at, c.created_at
        FROM nearby_parcel_candidates c
        ORDER BY c.created_at, c.id
    """)).mappings().all()
    cases: dict[tuple[str, str], tuple[str, str]] = {}
    status_priority = {
        "dismissed": 0,
        "candidate": 1,
        "shortlisted": 2,
        "contacted": 3,
        "promoted": 4,
    }
    now = datetime.now(timezone.utc)
    for row in rows:
        key = (row["organization_id"], row["parcel_id"])
        existing_case = cases.get(key)
        if existing_case is None:
            case_id = str(uuid4())
            cases[key] = (case_id, row["review_status"])
            bind.execute(sa.text("""
                INSERT INTO parcel_acquisition_cases (
                    id, organization_id, parcel_id, status,
                    assigned_to_user_id, assigned_to_name, assigned_by_user_id,
                    assigned_at, created_at, updated_at
                ) VALUES (
                    :id, :organization_id, :parcel_id, :status,
                    :assigned_to_user_id, :assigned_to_name, :assigned_by_user_id,
                    :assigned_at, :created_at, :updated_at
                )
            """), {
                "id": case_id,
                "organization_id": row["organization_id"],
                "parcel_id": row["parcel_id"],
                "status": row["review_status"],
                "assigned_to_user_id": row["assigned_to_user_id"],
                "assigned_to_name": row["assigned_to_name"],
                "assigned_by_user_id": row["assigned_by_user_id"],
                "assigned_at": row["assigned_at"],
                "created_at": row["created_at"] or now,
                "updated_at": now,
            })
        else:
            case_id, current_status = existing_case
            if status_priority.get(row["review_status"], 0) > status_priority.get(
                current_status, 0
            ):
                bind.execute(sa.text("""
                    UPDATE parcel_acquisition_cases
                    SET status = :status, updated_at = :updated_at
                    WHERE id = :case_id
                """), {
                    "status": row["review_status"],
                    "updated_at": now,
                    "case_id": case_id,
                })
                cases[key] = (case_id, row["review_status"])
        bind.execute(sa.text("""
            INSERT INTO parcel_acquisition_sources (
                id, organization_id, case_id, candidate_id, search_id, created_at
            ) VALUES (
                :id, :organization_id, :case_id, :candidate_id, :search_id, :created_at
            )
        """), {
            "id": str(uuid4()),
            "organization_id": row["organization_id"],
            "case_id": case_id,
            "candidate_id": row["candidate_id"],
            "search_id": row["search_id"],
            "created_at": row["created_at"] or now,
        })


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in _TABLES:
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
    op.drop_table("parcel_acquisition_activities")
    op.drop_table("parcel_acquisition_sources")
    op.drop_table("parcel_acquisition_cases")
