"""Add graph source identities and entity merge provenance.

Revision ID: 20260821_0001
Revises: 20260814_0002
Create Date: 2026-08-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260821_0001"
down_revision: Union[str, None] = "20260814_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

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

_TABLES = ("graph_entity_source_identities", "graph_entity_merges")


def upgrade() -> None:
    entity_type = postgresql.ENUM(
        *ENTITY_TYPES,
        name="graphentitytype",
        create_type=False,
    )
    op.create_table(
        "graph_entity_source_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            sa.String(36),
            sa.ForeignKey("graph_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_system", sa.String(100), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "entity_id",
            "source_system",
            "source_id",
            name="uq_graph_entity_source_identity_entity",
        ),
    )
    op.create_index(
        "ix_graph_entity_source_identity_lookup",
        "graph_entity_source_identities",
        ["organization_id", "source_system", "source_id"],
    )
    op.create_index(
        "ix_graph_entity_source_identities_organization_id",
        "graph_entity_source_identities",
        ["organization_id"],
    )
    op.create_index(
        "ix_graph_entity_source_identities_source_system",
        "graph_entity_source_identities",
        ["source_system"],
    )
    op.create_index(
        "ix_graph_entity_source_identities_source_id",
        "graph_entity_source_identities",
        ["source_id"],
    )

    op.create_table(
        "graph_entity_merges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "survivor_entity_id",
            sa.String(36),
            sa.ForeignKey("graph_entities.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("merged_entity_id", sa.String(36), nullable=False),
        sa.Column("entity_type", entity_type, nullable=False),
        sa.Column("merged_display_name", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "merged_entity_id",
            name="uq_graph_entity_merge_retired",
        ),
    )
    op.create_index(
        "ix_graph_entity_merge_survivor",
        "graph_entity_merges",
        ["organization_id", "survivor_entity_id"],
    )
    op.create_index(
        "ix_graph_entity_merges_organization_id",
        "graph_entity_merges",
        ["organization_id"],
    )

    op.execute(
        """
        INSERT INTO graph_entity_source_identities
            (id, organization_id, entity_id, source_system, source_id,
             confidence, created_at, last_verified_at)
        SELECT
            lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' ||
            substr(lower(hex(randomblob(2))), 2) || '-' ||
            substr('89ab', abs(random()) % 4 + 1, 1) ||
            substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))),
            organization_id, id, source_system, source_id, confidence,
            created_at, last_verified_at
        FROM graph_entities
        WHERE source_system IS NOT NULL AND source_id IS NOT NULL
        """
        if op.get_bind().dialect.name == "sqlite"
        else """
        INSERT INTO graph_entity_source_identities
            (id, organization_id, entity_id, source_system, source_id,
             confidence, created_at, last_verified_at)
        SELECT
               substr(md5(organization_id || ':' || id || ':' || source_system || ':' || source_id), 1, 8) || '-' ||
               substr(md5(organization_id || ':' || id || ':' || source_system || ':' || source_id), 9, 4) || '-' ||
               substr(md5(organization_id || ':' || id || ':' || source_system || ':' || source_id), 13, 4) || '-' ||
               substr(md5(organization_id || ':' || id || ':' || source_system || ':' || source_id), 17, 4) || '-' ||
               substr(md5(organization_id || ':' || id || ':' || source_system || ':' || source_id), 21, 12),
               organization_id, id, source_system,
               source_id, confidence, created_at, last_verified_at
        FROM graph_entities
        WHERE source_system IS NOT NULL AND source_id IS NOT NULL
        """
    )

    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            """
            INSERT INTO graph_entity_source_identities
                (id, organization_id, entity_id, source_system, source_id,
                 confidence, created_at, last_verified_at)
            SELECT
                lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' ||
                substr(lower(hex(randomblob(2))), 2) || '-' ||
                substr('89ab', abs(random()) % 4 + 1, 1) ||
                substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))),
                alias.organization_id, alias.entity_id, alias.source_system,
                alias.source_id, alias.confidence, alias.created_at, alias.created_at
            FROM graph_entity_aliases AS alias
            WHERE alias.source_system IS NOT NULL
              AND alias.source_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM graph_entity_source_identities AS identity
                  WHERE identity.organization_id = alias.organization_id
                    AND identity.entity_id = alias.entity_id
                    AND identity.source_system = alias.source_system
                    AND identity.source_id = alias.source_id
              )
            """
        )
    else:
        op.execute(
            """
            INSERT INTO graph_entity_source_identities
                (id, organization_id, entity_id, source_system, source_id,
                 confidence, created_at, last_verified_at)
            SELECT
                substr(md5(alias.organization_id || ':' || alias.entity_id || ':' || alias.source_system || ':' || alias.source_id), 1, 8) || '-' ||
                substr(md5(alias.organization_id || ':' || alias.entity_id || ':' || alias.source_system || ':' || alias.source_id), 9, 4) || '-' ||
                substr(md5(alias.organization_id || ':' || alias.entity_id || ':' || alias.source_system || ':' || alias.source_id), 13, 4) || '-' ||
                substr(md5(alias.organization_id || ':' || alias.entity_id || ':' || alias.source_system || ':' || alias.source_id), 17, 4) || '-' ||
                substr(md5(alias.organization_id || ':' || alias.entity_id || ':' || alias.source_system || ':' || alias.source_id), 21, 12),
                alias.organization_id, alias.entity_id, alias.source_system,
                alias.source_id, alias.confidence, alias.created_at, alias.created_at
            FROM graph_entity_aliases AS alias
            WHERE alias.source_system IS NOT NULL
              AND alias.source_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM graph_entity_source_identities AS identity
                  WHERE identity.organization_id = alias.organization_id
                    AND identity.entity_id = alias.entity_id
                    AND identity.source_system = alias.source_system
                    AND identity.source_id = alias.source_id
              )
            """
        )

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


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table)
