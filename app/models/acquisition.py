from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ParcelAcquisitionCase(OrgMixin, Base):
    """Canonical organization workflow for evaluating one parcel."""

    __tablename__ = "parcel_acquisition_cases"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "parcel_id", name="uq_parcel_acquisition_case_org_parcel"
        ),
        Index("ix_parcel_acquisition_case_org_status", "organization_id", "status"),
        Index(
            "ix_parcel_acquisition_case_org_assignee",
            "organization_id",
            "assigned_to_user_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    parcel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parcel_records.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), default="candidate", server_default="candidate", nullable=False
    )
    assigned_to_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_to_name: Mapped[Optional[str]] = mapped_column(String(255))
    assigned_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    contacted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    follow_up_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    promoted_deal_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("deals.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    parcel = relationship("ParcelRecord")
    assigned_to_user = relationship("User", foreign_keys=[assigned_to_user_id])
    assigned_by_user = relationship("User", foreign_keys=[assigned_by_user_id])
    promoted_deal = relationship("Deal", foreign_keys=[promoted_deal_id])
    sources: Mapped[list["ParcelAcquisitionSource"]] = relationship(
        "ParcelAcquisitionSource", back_populates="case", cascade="all, delete-orphan"
    )
    activities: Mapped[list["ParcelAcquisitionActivity"]] = relationship(
        "ParcelAcquisitionActivity",
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="ParcelAcquisitionActivity.occurred_at.desc()",
    )


class ParcelAcquisitionSource(OrgMixin, Base):
    """Provenance from an acquisition case to each contributing search result."""

    __tablename__ = "parcel_acquisition_sources"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "case_id",
            "candidate_id",
            name="uq_parcel_acquisition_source_candidate",
        ),
        Index("ix_parcel_acquisition_source_case", "organization_id", "case_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parcel_acquisition_cases.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("nearby_parcel_candidates.id", ondelete="CASCADE"), nullable=False
    )
    search_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("nearby_parcel_searches.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    case: Mapped[ParcelAcquisitionCase] = relationship(
        "ParcelAcquisitionCase", back_populates="sources"
    )
    candidate = relationship("NearbyParcelCandidate")
    search = relationship("NearbyParcelSearch")


class ParcelAcquisitionActivity(OrgMixin, Base):
    """Immutable outreach and diligence history for an acquisition case."""

    __tablename__ = "parcel_acquisition_activities"
    __table_args__ = (
        Index(
            "ix_parcel_acquisition_activity_case_occurred",
            "organization_id",
            "case_id",
            "occurred_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parcel_acquisition_cases.id", ondelete="CASCADE"), nullable=False
    )
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    actor_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    follow_up_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    case: Mapped[ParcelAcquisitionCase] = relationship(
        "ParcelAcquisitionCase", back_populates="activities"
    )
    actor = relationship("User", foreign_keys=[actor_user_id])
