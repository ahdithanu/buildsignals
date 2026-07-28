"""Add nearby parcel discovery persistence.

Revision ID: 20260716_0006
Revises: 20260716_0005
Create Date: 2026-07-16
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0006"
down_revision: Union[str, None] = "20260716_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_TABLES: tuple[str, ...] = (
    "parcel_records",
    "parcel_facts",
    "nearby_parcel_searches",
    "nearby_parcel_candidates",
)


def _tenant_column() -> sa.Column:
    return sa.Column(
        "organization_id",
        sa.String(36),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "parcel_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("ingestion_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("latest_raw_record_id", sa.String(36), sa.ForeignKey("raw_source_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_parcel_id", sa.String(500), nullable=False),
        sa.Column("jurisdiction", sa.String(255)),
        sa.Column("county", sa.String(255)),
        sa.Column("state", sa.String(50)),
        sa.Column("address", sa.String(1000)),
        sa.Column("city", sa.String(100)),
        sa.Column("postal_code", sa.String(20)),
        sa.Column("normalized_address", sa.String(1000)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("land_area_sq_ft", sa.Numeric(18, 2)),
        sa.Column("improvement_area_sq_ft", sa.Numeric(18, 2)),
        sa.Column("land_value", sa.Numeric(18, 2)),
        sa.Column("improvement_value", sa.Numeric(18, 2)),
        sa.Column("total_assessed_value", sa.Numeric(18, 2)),
        sa.Column("land_use", sa.String(255)),
        sa.Column("zoning_code", sa.String(255)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        _created_at(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        _tenant_column(),
        sa.UniqueConstraint("source_id", "external_parcel_id", name="uq_parcel_record_source_external"),
    )
    op.create_index("ix_parcel_records_organization_id", "parcel_records", ["organization_id"])
    op.create_index("ix_parcel_record_org_active", "parcel_records", ["organization_id", "is_active"])
    op.create_index("ix_parcel_record_location", "parcel_records", ["organization_id", "state", "county", "jurisdiction"])
    op.create_index("ix_parcel_record_normalized_address", "parcel_records", ["organization_id", "normalized_address"])
    op.create_index("ix_parcel_record_coordinates", "parcel_records", ["latitude", "longitude"])

    op.create_table(
        "parcel_facts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("parcel_id", sa.String(36), sa.ForeignKey("parcel_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_source_record_id", sa.String(36), sa.ForeignKey("raw_source_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("fact_type", sa.String(100), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("source_system", sa.String(100), nullable=False),
        sa.Column("source_url", sa.String(2000)),
        sa.Column("field_path", sa.String(1000)),
        sa.Column("excerpt", sa.Text()),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("is_current", sa.Boolean(), server_default=sa.true(), nullable=False),
        _created_at(),
        _tenant_column(),
        sa.UniqueConstraint("parcel_id", "fact_type", "raw_source_record_id", name="uq_parcel_fact_source_version"),
    )
    op.create_index("ix_parcel_facts_organization_id", "parcel_facts", ["organization_id"])
    op.create_index("ix_parcel_fact_current", "parcel_facts", ["organization_id", "parcel_id", "fact_type", "is_current"])
    op.create_index("ix_parcel_fact_observed", "parcel_facts", ["parcel_id", "observed_at"])

    op.create_table(
        "nearby_parcel_searches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("anchor_brand_match_id", sa.String(36), sa.ForeignKey("permit_brand_matches.id", ondelete="SET NULL")),
        sa.Column("anchor_permit_id", sa.String(36), sa.ForeignKey("permit_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("anchor_latitude", sa.Float(), nullable=False),
        sa.Column("anchor_longitude", sa.Float(), nullable=False),
        sa.Column("radius_miles", sa.Float(), server_default="2.0", nullable=False),
        sa.Column("persona", sa.String(50), nullable=False),
        sa.Column("filters", sa.JSON()),
        sa.Column("result_limit", sa.Integer(), server_default="100", nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ranker_version", sa.String(50), nullable=False),
        _created_at(),
        _tenant_column(),
        sa.CheckConstraint("radius_miles >= 0.25 AND radius_miles <= 5.0", name="ck_nearby_parcel_search_radius"),
        sa.CheckConstraint("result_limit > 0", name="ck_nearby_parcel_search_result_limit"),
    )
    op.create_index("ix_nearby_parcel_searches_organization_id", "nearby_parcel_searches", ["organization_id"])
    op.create_index("ix_nearby_parcel_search_deal_created", "nearby_parcel_searches", ["organization_id", "deal_id", "created_at"])
    op.create_index("ix_nearby_parcel_search_permit", "nearby_parcel_searches", ["anchor_permit_id"])

    op.create_table(
        "nearby_parcel_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("search_id", sa.String(36), sa.ForeignKey("nearby_parcel_searches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parcel_id", sa.String(36), sa.ForeignKey("parcel_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("distance_miles", sa.Float(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("score_confidence", sa.Float(), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(32), server_default="candidate", nullable=False),
        sa.Column("ranker_version", sa.String(50), nullable=False),
        _created_at(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        _tenant_column(),
        sa.UniqueConstraint("search_id", "parcel_id", name="uq_nearby_parcel_candidate_search_parcel"),
    )
    op.create_index("ix_nearby_parcel_candidates_organization_id", "nearby_parcel_candidates", ["organization_id"])
    op.create_index("ix_nearby_parcel_candidate_search_rank", "nearby_parcel_candidates", ["search_id", "rank"])
    op.create_index("ix_nearby_parcel_candidate_org_status", "nearby_parcel_candidates", ["organization_id", "review_status"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        op.execute(
            """ALTER TABLE parcel_records
            ADD COLUMN centroid geography(Point, 4326)
            GENERATED ALWAYS AS (
                CASE
                    WHEN latitude IS NULL OR longitude IS NULL THEN NULL
                    ELSE ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
                END
            ) STORED"""
        )
        op.execute("CREATE INDEX ix_parcel_record_centroid_gist ON parcel_records USING GIST (centroid)")

        for table in TENANT_TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            op.execute(
                f"""CREATE POLICY tenant_isolation ON "{table}"
                USING (organization_id = current_setting('app.current_org', true))
                WITH CHECK (organization_id = current_setting('app.current_org', true))"""
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in reversed(TENANT_TABLES):
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        op.execute("DROP INDEX IF EXISTS ix_parcel_record_centroid_gist")
        op.execute("ALTER TABLE parcel_records DROP COLUMN IF EXISTS centroid")

    op.drop_index("ix_nearby_parcel_candidate_org_status", table_name="nearby_parcel_candidates")
    op.drop_index("ix_nearby_parcel_candidate_search_rank", table_name="nearby_parcel_candidates")
    op.drop_index("ix_nearby_parcel_candidates_organization_id", table_name="nearby_parcel_candidates")
    op.drop_table("nearby_parcel_candidates")
    op.drop_index("ix_nearby_parcel_search_permit", table_name="nearby_parcel_searches")
    op.drop_index("ix_nearby_parcel_search_deal_created", table_name="nearby_parcel_searches")
    op.drop_index("ix_nearby_parcel_searches_organization_id", table_name="nearby_parcel_searches")
    op.drop_table("nearby_parcel_searches")
    op.drop_index("ix_parcel_fact_observed", table_name="parcel_facts")
    op.drop_index("ix_parcel_fact_current", table_name="parcel_facts")
    op.drop_index("ix_parcel_facts_organization_id", table_name="parcel_facts")
    op.drop_table("parcel_facts")
    op.drop_index("ix_parcel_record_coordinates", table_name="parcel_records")
    op.drop_index("ix_parcel_record_normalized_address", table_name="parcel_records")
    op.drop_index("ix_parcel_record_location", table_name="parcel_records")
    op.drop_index("ix_parcel_record_org_active", table_name="parcel_records")
    op.drop_index("ix_parcel_records_organization_id", table_name="parcel_records")
    op.drop_table("parcel_records")
