from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PlanningRecord(OrgMixin, Base):
    """A public planning, hearing, agenda, or staff-review event."""

    __tablename__ = "planning_records"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "external_record_id", name="uq_planning_record_source_external"
        ),
        Index("ix_planning_record_org_stage", "organization_id", "stage"),
        Index("ix_planning_record_org_meeting", "organization_id", "meeting_at"),
        Index("ix_planning_record_org_priority", "organization_id", "priority_score"),
        Index(
            "ix_planning_record_reference_scope",
            "organization_id",
            "reference_number",
            "state",
            "city",
        ),
        Index("ix_planning_record_location", "organization_id", "state", "city", "postal_code"),
        Index("ix_planning_record_parcel", "organization_id", "parcel_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ingestion_sources.id", ondelete="RESTRICT"), nullable=False
    )
    latest_raw_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_source_records.id", ondelete="RESTRICT"), nullable=False
    )
    external_record_id: Mapped[str] = mapped_column(String(500), nullable=False)
    normalization_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_number: Mapped[Optional[str]] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    stage: Mapped[Optional[str]] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    evidence_excerpt: Mapped[Optional[str]] = mapped_column(Text)
    agenda_item_number: Mapped[Optional[str]] = mapped_column(String(100))
    meeting_name: Mapped[Optional[str]] = mapped_column(String(500))
    governing_body: Mapped[Optional[str]] = mapped_column(String(500))
    project_name: Mapped[Optional[str]] = mapped_column(String(500))
    address: Mapped[Optional[str]] = mapped_column(String(1000))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(50))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    parcel_id: Mapped[Optional[str]] = mapped_column(String(255))
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(255))
    applicant_name: Mapped[Optional[str]] = mapped_column(String(500))
    owner_name: Mapped[Optional[str]] = mapped_column(String(500))
    developer_name: Mapped[Optional[str]] = mapped_column(String(500))
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    meeting_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    decision_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[Optional[str]] = mapped_column(String(2000))
    signal_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    priority_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    priority_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    attributes: Mapped[Optional[dict]] = mapped_column(JSON)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    source = relationship("IngestionSource", back_populates="planning_records")
    latest_raw_record = relationship("RawSourceRecord", foreign_keys=[latest_raw_record_id])
    company_matches: Mapped[list["PlanningCompanyMatch"]] = relationship(
        "PlanningCompanyMatch", back_populates="planning_record", cascade="all, delete-orphan"
    )


class PlanningCompanyMatch(OrgMixin, Base):
    """A reviewable company mention found in planning evidence."""

    __tablename__ = "planning_company_matches"
    __table_args__ = (
        UniqueConstraint("planning_record_id", "brand_id", name="uq_planning_company_match"),
        Index("ix_planning_company_match_org_status", "organization_id", "review_status"),
        Index("ix_planning_company_match_org_confidence", "organization_id", "confidence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    planning_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("planning_records.id", ondelete="CASCADE"), nullable=False
    )
    brand_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brand_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    raw_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_source_records.id", ondelete="RESTRICT"), nullable=False
    )
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate")
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    matched_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    matched_field: Mapped[str] = mapped_column(String(100), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    detector_version: Mapped[str] = mapped_column(String(50), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    planning_record: Mapped[PlanningRecord] = relationship(
        "PlanningRecord", back_populates="company_matches"
    )
    brand = relationship("BrandProfile")
    raw_record = relationship("RawSourceRecord")
