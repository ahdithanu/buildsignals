from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GraphEntityType(str, enum.Enum):
    opportunity = "opportunity"
    permit = "permit"
    parcel = "parcel"
    property = "property"
    developer = "developer"
    owner = "owner"
    general_contractor = "general_contractor"
    architect = "architect"
    engineer = "engineer"
    city = "city"
    lender = "lender"
    broker = "broker"
    company = "company"
    person = "person"
    source_record = "source_record"


class GraphRelationshipType(str, enum.Enum):
    located_on = "located_on"
    owns = "owns"
    owned_by = "owned_by"
    developed_by = "developed_by"
    developer_of = "developer_of"
    contracted_by = "contracted_by"
    contractor_for = "contractor_for"
    designed_by = "designed_by"
    engineer_for = "engineer_for"
    permitted_by = "permitted_by"
    permit_for = "permit_for"
    financed_by = "financed_by"
    brokered_by = "brokered_by"
    related_to = "related_to"


class GraphEntity(OrgMixin, Base):
    __tablename__ = "graph_entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    entity_type: Mapped[GraphEntityType] = mapped_column(SAEnum(GraphEntityType), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_address: Mapped[Optional[str]] = mapped_column(String(500), index=True)
    source_system: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    address: Mapped[Optional[str]] = mapped_column(String(500))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(50))
    zip_code: Mapped[Optional[str]] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    attributes: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    aliases: Mapped[List["GraphEntityAlias"]] = relationship(
        "GraphEntityAlias", back_populates="entity", cascade="all, delete-orphan"
    )
    source_identities: Mapped[List["GraphEntitySourceIdentity"]] = relationship(
        "GraphEntitySourceIdentity", back_populates="entity", cascade="all, delete-orphan"
    )
    links: Mapped[List["GraphEntityLink"]] = relationship(
        "GraphEntityLink", back_populates="entity", cascade="all, delete-orphan"
    )
    outgoing_relationships: Mapped[List["GraphRelationship"]] = relationship(
        "GraphRelationship",
        back_populates="source_entity",
        foreign_keys="[GraphRelationship.source_entity_id]",
        cascade="all, delete-orphan",
    )
    incoming_relationships: Mapped[List["GraphRelationship"]] = relationship(
        "GraphRelationship",
        back_populates="target_entity",
        foreign_keys="[GraphRelationship.target_entity_id]",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "entity_type",
            "source_system",
            "source_id",
            name="uq_graph_entity_source_identity",
        ),
    )


class GraphEntityAlias(OrgMixin, Base):
    __tablename__ = "graph_entity_aliases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    entity_id: Mapped[str] = mapped_column(String(36), ForeignKey("graph_entities.id", ondelete="CASCADE"), nullable=False)
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_system: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    entity: Mapped["GraphEntity"] = relationship("GraphEntity", back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("organization_id", "entity_id", "normalized_alias", name="uq_graph_alias_entity_alias"),
        Index("ix_graph_alias_source", "organization_id", "source_system", "source_id"),
    )


class GraphEntitySourceIdentity(OrgMixin, Base):
    __tablename__ = "graph_entity_source_identities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("graph_entities.id", ondelete="CASCADE"), nullable=False
    )
    source_system: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    entity: Mapped["GraphEntity"] = relationship("GraphEntity", back_populates="source_identities")

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "entity_id",
            "source_system",
            "source_id",
            name="uq_graph_entity_source_identity_entity",
        ),
        Index(
            "ix_graph_entity_source_identity_lookup",
            "organization_id",
            "source_system",
            "source_id",
        ),
    )


class GraphEntityMerge(OrgMixin, Base):
    __tablename__ = "graph_entity_merges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    survivor_entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("graph_entities.id", ondelete="RESTRICT"), nullable=False
    )
    merged_entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entity_type: Mapped[GraphEntityType] = mapped_column(SAEnum(GraphEntityType), nullable=False)
    merged_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "merged_entity_id", name="uq_graph_entity_merge_retired"),
        Index("ix_graph_entity_merge_survivor", "organization_id", "survivor_entity_id"),
    )


class GraphEntityLink(OrgMixin, Base):
    __tablename__ = "graph_entity_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    entity_id: Mapped[str] = mapped_column(String(36), ForeignKey("graph_entities.id", ondelete="CASCADE"), nullable=False)
    record_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    record_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_system: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    entity: Mapped["GraphEntity"] = relationship("GraphEntity", back_populates="links")

    __table_args__ = (
        UniqueConstraint("organization_id", "record_type", "record_id", "entity_id", name="uq_graph_entity_link"),
        Index("ix_graph_link_record", "organization_id", "record_type", "record_id"),
    )


class GraphRelationship(OrgMixin, Base):
    __tablename__ = "graph_relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_entity_id: Mapped[str] = mapped_column(String(36), ForeignKey("graph_entities.id", ondelete="CASCADE"), nullable=False)
    target_entity_id: Mapped[str] = mapped_column(String(36), ForeignKey("graph_entities.id", ondelete="CASCADE"), nullable=False)
    relationship_type: Mapped[GraphRelationshipType] = mapped_column(SAEnum(GraphRelationshipType), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source_system: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    attributes: Mapped[Optional[dict]] = mapped_column(JSON)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    source_entity: Mapped["GraphEntity"] = relationship(
        "GraphEntity", back_populates="outgoing_relationships", foreign_keys=[source_entity_id]
    )
    target_entity: Mapped["GraphEntity"] = relationship(
        "GraphEntity", back_populates="incoming_relationships", foreign_keys=[target_entity_id]
    )
    evidence: Mapped[List["GraphRelationshipEvidence"]] = relationship(
        "GraphRelationshipEvidence", back_populates="relationship", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            "source_system",
            "source_id",
            name="uq_graph_relationship_source",
        ),
        Index("ix_graph_relationship_source_target", "organization_id", "source_entity_id", "target_entity_id"),
        Index("ix_graph_relationship_current", "organization_id", "is_current"),
    )


class GraphRelationshipEvidence(OrgMixin, Base):
    __tablename__ = "graph_relationship_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    relationship_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("graph_relationships.id", ondelete="CASCADE"), nullable=False
    )
    source_system: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[Optional[str]] = mapped_column(String(255))
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    evidence_type: Mapped[Optional[str]] = mapped_column(String(100))
    excerpt: Mapped[Optional[str]] = mapped_column(Text)
    observed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    relationship: Mapped["GraphRelationship"] = relationship("GraphRelationship", back_populates="evidence")

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "relationship_id",
            "source_system",
            "source_id",
            name="uq_graph_evidence_source",
        ),
    )
