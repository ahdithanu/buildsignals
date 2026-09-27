from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ParcelRecord(OrgMixin, Base):
    """Current canonical parcel identity and assessor snapshot."""

    __tablename__ = "parcel_records"
    __table_args__ = (
        UniqueConstraint("source_id", "external_parcel_id", name="uq_parcel_record_source_external"),
        Index("ix_parcel_record_org_active", "organization_id", "is_active"),
        Index("ix_parcel_record_location", "organization_id", "state", "county", "jurisdiction"),
        Index("ix_parcel_record_normalized_address", "organization_id", "normalized_address"),
        Index("ix_parcel_record_coordinates", "latitude", "longitude"),
        Index(
            "ix_parcel_record_physical_group",
            "organization_id", "source_id", "parcel_group_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ingestion_sources.id", ondelete="RESTRICT"), nullable=False
    )
    latest_raw_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_source_records.id", ondelete="RESTRICT"), nullable=False
    )
    external_parcel_id: Mapped[str] = mapped_column(String(500), nullable=False)
    parcel_group_id: Mapped[Optional[str]] = mapped_column(String(500))
    normalization_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    last_seen_snapshot_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(255))
    county: Mapped[Optional[str]] = mapped_column(String(255))
    state: Mapped[Optional[str]] = mapped_column(String(50))
    address: Mapped[Optional[str]] = mapped_column(String(1000))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    normalized_address: Mapped[Optional[str]] = mapped_column(String(1000))
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    land_area_sq_ft: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    improvement_area_sq_ft: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    land_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    improvement_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    total_assessed_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    land_use: Mapped[Optional[str]] = mapped_column(String(255))
    zoning_code: Mapped[Optional[str]] = mapped_column(String(255))
    attributes: Mapped[Optional[dict]] = mapped_column(JSON)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    retired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    source = relationship("IngestionSource")
    latest_raw_record = relationship("RawSourceRecord", foreign_keys=[latest_raw_record_id])
    facts: Mapped[list["ParcelFact"]] = relationship(
        "ParcelFact", back_populates="parcel", cascade="all, delete-orphan"
    )
    candidates: Mapped[list["NearbyParcelCandidate"]] = relationship(
        "NearbyParcelCandidate", back_populates="parcel"
    )

    @property
    def boundary_geometry(self) -> dict | None:
        from app.services.parcel_geometry import resolve_display_boundary_geometry

        export_policy = None
        if self.source is not None and isinstance(self.source.settings, dict):
            export_policy = self.source.settings.get("export_policy")
        return resolve_display_boundary_geometry(self.attributes, export_policy)


class ParcelFact(OrgMixin, Base):
    """Versioned parcel fact with immutable-source evidence and independent freshness."""

    __tablename__ = "parcel_facts"
    __table_args__ = (
        UniqueConstraint(
            "parcel_id",
            "fact_type",
            "raw_source_record_id",
            "valid_from",
            name="uq_parcel_fact_source_occurrence",
        ),
        Index("ix_parcel_fact_current", "organization_id", "parcel_id", "fact_type", "is_current"),
        Index("ix_parcel_fact_observed", "parcel_id", "observed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    parcel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parcel_records.id", ondelete="CASCADE"), nullable=False
    )
    raw_source_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_source_records.id", ondelete="RESTRICT"), nullable=False
    )
    fact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_system: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(2000))
    field_path: Mapped[Optional[str]] = mapped_column(String(1000))
    excerpt: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    parcel: Mapped[ParcelRecord] = relationship("ParcelRecord", back_populates="facts")
    raw_source_record = relationship("RawSourceRecord")


class NearbyParcelSearch(OrgMixin, Base):
    """Immutable search inputs and anchor coordinates used for parcel discovery."""

    __tablename__ = "nearby_parcel_searches"
    __table_args__ = (
        CheckConstraint(
            "radius_miles >= 0.25 AND radius_miles <= 5.0",
            name="ck_nearby_parcel_search_radius",
        ),
        CheckConstraint("result_limit > 0", name="ck_nearby_parcel_search_result_limit"),
        Index("ix_nearby_parcel_search_deal_created", "organization_id", "deal_id", "created_at"),
        Index("ix_nearby_parcel_search_permit", "anchor_permit_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False
    )
    anchor_brand_match_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("permit_brand_matches.id", ondelete="SET NULL")
    )
    anchor_permit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("permit_records.id", ondelete="RESTRICT"), nullable=False
    )
    anchor_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    anchor_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    radius_miles: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    persona: Mapped[str] = mapped_column(String(50), nullable=False)
    filters: Mapped[Optional[dict]] = mapped_column(JSON)
    result_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ranker_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    deal = relationship("Deal")
    anchor_brand_match = relationship("PermitBrandMatch")
    anchor_permit = relationship("PermitRecord")
    candidates: Mapped[list["NearbyParcelCandidate"]] = relationship(
        "NearbyParcelCandidate", back_populates="search", cascade="all, delete-orphan",
        order_by="NearbyParcelCandidate.rank",
    )


class NearbyParcelCandidate(OrgMixin, Base):
    """Ranked, reviewable parcel result persisted for a single search."""

    __tablename__ = "nearby_parcel_candidates"
    __table_args__ = (
        UniqueConstraint("search_id", "parcel_id", name="uq_nearby_parcel_candidate_search_parcel"),
        Index("ix_nearby_parcel_candidate_search_rank", "search_id", "rank"),
        Index("ix_nearby_parcel_candidate_org_status", "organization_id", "review_status"),
        Index(
            "ix_nearby_parcel_candidate_assigned_to",
            "organization_id", "assigned_to_user_id", "review_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    search_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("nearby_parcel_searches.id", ondelete="CASCADE"), nullable=False
    )
    parcel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parcel_records.id", ondelete="RESTRICT"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_miles: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    score_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[dict] = mapped_column(JSON, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), default="candidate", nullable=False)
    assigned_to_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_to_name: Mapped[Optional[str]] = mapped_column(String(255))
    assigned_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ranker_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    search: Mapped[NearbyParcelSearch] = relationship("NearbyParcelSearch", back_populates="candidates")
    parcel: Mapped[ParcelRecord] = relationship("ParcelRecord", back_populates="candidates")
    assigned_to_user = relationship("User", foreign_keys=[assigned_to_user_id])
    assigned_by_user = relationship("User", foreign_keys=[assigned_by_user_id])

    @property
    def facts(self) -> list[ParcelFact]:
        return [fact for fact in self.parcel.facts if fact.is_current]
