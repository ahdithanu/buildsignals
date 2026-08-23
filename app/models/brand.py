from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BrandProfile(OrgMixin, Base):
    """A company or brand an organization wants to detect in public records."""

    __tablename__ = "brand_profiles"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_brand_profile_org_key"),
        Index("ix_brand_profile_org_active", "organization_id", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(100))
    scale: Mapped[Optional[str]] = mapped_column(String(50))
    priority: Mapped[int] = mapped_column(default=3, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    attributes: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    aliases: Mapped[list["BrandAlias"]] = relationship(
        "BrandAlias", back_populates="brand", cascade="all, delete-orphan"
    )
    permit_matches: Mapped[list["PermitBrandMatch"]] = relationship(
        "PermitBrandMatch", back_populates="brand"
    )
    party_fingerprints: Mapped[list["BrandPartyFingerprint"]] = relationship(
        "BrandPartyFingerprint", back_populates="brand", cascade="all, delete-orphan"
    )


class BrandAlias(OrgMixin, Base):
    """A matchable brand spelling with optional anti-ambiguity context."""

    __tablename__ = "brand_aliases"
    __table_args__ = (
        UniqueConstraint("organization_id", "normalized_alias", name="uq_brand_alias_org_alias"),
        Index("ix_brand_alias_brand_active", "brand_id", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    brand_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    requires_context: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    minimum_field_matches: Mapped[int] = mapped_column(default=1, nullable=False)
    context_terms: Mapped[Optional[list[str]]] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    brand: Mapped[BrandProfile] = relationship("BrandProfile", back_populates="aliases")


class BrandPartyFingerprint(OrgMixin, Base):
    """An evidence-backed professional or shell-entity association for a brand."""

    __tablename__ = "brand_party_fingerprints"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "brand_id",
            "party_type",
            "normalized_name",
            "state",
            name="uq_brand_party_fingerprint_identity",
        ),
        Index(
            "ix_brand_party_fingerprint_brand_type_active",
            "brand_id",
            "party_type",
            "is_active",
        ),
        Index(
            "ix_brand_party_fingerprint_org_name_state",
            "organization_id",
            "normalized_name",
            "state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    brand_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False
    )
    party_type: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_match_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    brand: Mapped[BrandProfile] = relationship(
        "BrandProfile", back_populates="party_fingerprints"
    )


class PermitBrandMatch(OrgMixin, Base):
    """A reviewable brand candidate backed by immutable permit evidence."""

    __tablename__ = "permit_brand_matches"
    __table_args__ = (
        UniqueConstraint("permit_id", "brand_id", name="uq_permit_brand_match"),
        Index("ix_permit_brand_match_org_status", "organization_id", "review_status"),
        Index("ix_permit_brand_match_org_confidence", "organization_id", "confidence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    permit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("permit_records.id", ondelete="CASCADE"), nullable=False
    )
    brand_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brand_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    first_raw_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_source_records.id", ondelete="RESTRICT"), nullable=False
    )
    latest_raw_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_source_records.id", ondelete="RESTRICT"), nullable=False
    )
    review_status: Mapped[str] = mapped_column(String(32), default="candidate", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    matched_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    matched_field: Mapped[str] = mapped_column(String(100), nullable=False)
    matched_fields: Mapped[Optional[list[str]]] = mapped_column(JSON)
    rule_ids: Mapped[Optional[list[str]]] = mapped_column(JSON)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    detector_version: Mapped[str] = mapped_column(String(50), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    permit = relationship("PermitRecord")
    brand: Mapped[BrandProfile] = relationship("BrandProfile", back_populates="permit_matches")
    first_raw_record = relationship("RawSourceRecord", foreign_keys=[first_raw_record_id])
    latest_raw_record = relationship("RawSourceRecord", foreign_keys=[latest_raw_record_id])
