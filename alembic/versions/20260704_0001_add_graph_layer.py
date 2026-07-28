"""add graph layer

Revision ID: 20260704_0001
Revises:
Create Date: 2026-07-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260704_0001"
down_revision = "006_add_password_reset_tokens"
branch_labels = None
depends_on = None


ENTITY_TYPES = (
    "opportunity",
    "permit",
    "parcel",
    "property",
    "developer",
    "owner",
    "general_contractor",
    "architect",
    "engineer",
    "city",
    "lender",
    "broker",
    "company",
    "person",
    "source_record",
)

RELATIONSHIP_TYPES = (
    "located_on",
    "owns",
    "owned_by",
    "developed_by",
    "developer_of",
    "contracted_by",
    "contractor_for",
    "designed_by",
    "engineer_for",
    "permitted_by",
    "permit_for",
    "financed_by",
    "brokered_by",
    "related_to",
)


def _entity_type_enum(*, create_type: bool = True) -> sa.Enum:
    return sa.Enum(*ENTITY_TYPES, name="graphentitytype", create_type=create_type)


def _relationship_type_enum(*, create_type: bool = True) -> sa.Enum:
    return sa.Enum(*RELATIONSHIP_TYPES, name="graphrelationshiptype", create_type=create_type)


entity_type = _entity_type_enum()
relationship_type = _relationship_type_enum()

TENANT_TABLES = (
    "graph_entities",
    "graph_entity_aliases",
    "graph_entity_links",
    "graph_relationships",
    "graph_relationship_evidence",
)


def _enable_rls() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON "{table}"
                USING (organization_id = current_setting('app.current_org', true))
                WITH CHECK (organization_id = current_setting('app.current_org', true))
            """
        )


def upgrade() -> None:
    bind = op.get_bind()
    entity_type.create(bind, checkfirst=True)
    relationship_type.create(bind, checkfirst=True)
    entity_type_col = _entity_type_enum(create_type=False)
    relationship_type_col = _relationship_type_enum(create_type=False)

    op.create_table(
        "graph_entities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", entity_type_col, nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_address", sa.String(length=500), nullable=True),
        sa.Column("source_system", sa.String(length=100), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=50), nullable=True),
        sa.Column("zip_code", sa.String(length=20), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "entity_type",
            "source_system",
            "source_id",
            name="uq_graph_entity_source_identity",
        ),
    )
    op.create_index(op.f("ix_graph_entities_entity_type"), "graph_entities", ["entity_type"])
    op.create_index(op.f("ix_graph_entities_normalized_address"), "graph_entities", ["normalized_address"])
    op.create_index(op.f("ix_graph_entities_normalized_name"), "graph_entities", ["normalized_name"])
    op.create_index(op.f("ix_graph_entities_organization_id"), "graph_entities", ["organization_id"])
    op.create_index(op.f("ix_graph_entities_source_id"), "graph_entities", ["source_id"])
    op.create_index(op.f("ix_graph_entities_source_system"), "graph_entities", ["source_system"])

    op.create_table(
        "graph_entity_aliases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("source_system", sa.String(length=100), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["graph_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "entity_id", "normalized_alias", name="uq_graph_alias_entity_alias"),
    )
    op.create_index("ix_graph_alias_source", "graph_entity_aliases", ["organization_id", "source_system", "source_id"])
    op.create_index(op.f("ix_graph_entity_aliases_normalized_alias"), "graph_entity_aliases", ["normalized_alias"])
    op.create_index(op.f("ix_graph_entity_aliases_organization_id"), "graph_entity_aliases", ["organization_id"])
    op.create_index(op.f("ix_graph_entity_aliases_source_id"), "graph_entity_aliases", ["source_id"])
    op.create_index(op.f("ix_graph_entity_aliases_source_system"), "graph_entity_aliases", ["source_system"])

    op.create_table(
        "graph_entity_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("record_type", sa.String(length=100), nullable=False),
        sa.Column("record_id", sa.String(length=255), nullable=False),
        sa.Column("source_system", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["graph_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "record_type", "record_id", "entity_id", name="uq_graph_entity_link"),
    )
    op.create_index("ix_graph_link_record", "graph_entity_links", ["organization_id", "record_type", "record_id"])
    op.create_index(op.f("ix_graph_entity_links_organization_id"), "graph_entity_links", ["organization_id"])
    op.create_index(op.f("ix_graph_entity_links_record_id"), "graph_entity_links", ["record_id"])
    op.create_index(op.f("ix_graph_entity_links_record_type"), "graph_entity_links", ["record_type"])

    op.create_table(
        "graph_relationships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_entity_id", sa.String(length=36), nullable=False),
        sa.Column("target_entity_id", sa.String(length=36), nullable=False),
        sa.Column("relationship_type", relationship_type_col, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_system", sa.String(length=100), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_entity_id"], ["graph_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_entity_id"], ["graph_entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            "source_system",
            "source_id",
            name="uq_graph_relationship_source",
        ),
    )
    op.create_index("ix_graph_relationship_source_target", "graph_relationships", ["organization_id", "source_entity_id", "target_entity_id"])
    op.create_index("ix_graph_relationship_current", "graph_relationships", ["organization_id", "is_current"])
    op.create_index(op.f("ix_graph_relationships_organization_id"), "graph_relationships", ["organization_id"])
    op.create_index(op.f("ix_graph_relationships_relationship_type"), "graph_relationships", ["relationship_type"])
    op.create_index(op.f("ix_graph_relationships_source_id"), "graph_relationships", ["source_id"])
    op.create_index(op.f("ix_graph_relationships_source_system"), "graph_relationships", ["source_system"])

    op.create_table(
        "graph_relationship_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("relationship_id", sa.String(length=36), nullable=False),
        sa.Column("source_system", sa.String(length=100), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("evidence_type", sa.String(length=100), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["relationship_id"], ["graph_relationships.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "relationship_id",
            "source_system",
            "source_id",
            name="uq_graph_evidence_source",
        ),
    )
    op.create_index(op.f("ix_graph_relationship_evidence_organization_id"), "graph_relationship_evidence", ["organization_id"])
    _enable_rls()


def downgrade() -> None:
    op.drop_index(op.f("ix_graph_relationship_evidence_organization_id"), table_name="graph_relationship_evidence")
    op.drop_table("graph_relationship_evidence")
    op.drop_index(op.f("ix_graph_relationships_source_system"), table_name="graph_relationships")
    op.drop_index(op.f("ix_graph_relationships_source_id"), table_name="graph_relationships")
    op.drop_index(op.f("ix_graph_relationships_relationship_type"), table_name="graph_relationships")
    op.drop_index(op.f("ix_graph_relationships_organization_id"), table_name="graph_relationships")
    op.drop_index("ix_graph_relationship_source_target", table_name="graph_relationships")
    op.drop_index("ix_graph_relationship_current", table_name="graph_relationships")
    op.drop_table("graph_relationships")
    op.drop_index(op.f("ix_graph_entity_links_record_type"), table_name="graph_entity_links")
    op.drop_index(op.f("ix_graph_entity_links_record_id"), table_name="graph_entity_links")
    op.drop_index(op.f("ix_graph_entity_links_organization_id"), table_name="graph_entity_links")
    op.drop_index("ix_graph_link_record", table_name="graph_entity_links")
    op.drop_table("graph_entity_links")
    op.drop_index(op.f("ix_graph_entity_aliases_source_system"), table_name="graph_entity_aliases")
    op.drop_index(op.f("ix_graph_entity_aliases_source_id"), table_name="graph_entity_aliases")
    op.drop_index(op.f("ix_graph_entity_aliases_organization_id"), table_name="graph_entity_aliases")
    op.drop_index(op.f("ix_graph_entity_aliases_normalized_alias"), table_name="graph_entity_aliases")
    op.drop_index("ix_graph_alias_source", table_name="graph_entity_aliases")
    op.drop_table("graph_entity_aliases")
    op.drop_index(op.f("ix_graph_entities_source_system"), table_name="graph_entities")
    op.drop_index(op.f("ix_graph_entities_source_id"), table_name="graph_entities")
    op.drop_index(op.f("ix_graph_entities_organization_id"), table_name="graph_entities")
    op.drop_index(op.f("ix_graph_entities_normalized_name"), table_name="graph_entities")
    op.drop_index(op.f("ix_graph_entities_normalized_address"), table_name="graph_entities")
    op.drop_index(op.f("ix_graph_entities_entity_type"), table_name="graph_entities")
    op.drop_table("graph_entities")
    relationship_type.drop(op.get_bind(), checkfirst=True)
    entity_type.drop(op.get_bind(), checkfirst=True)
