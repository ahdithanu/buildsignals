from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ParcelLineageEvent(OrgMixin, Base):
    """A source-reported parcel split, merge, replat, or identity correction."""

    __tablename__ = "parcel_lineage_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('split', 'merge', 'replat', 'correction')",
            name="ck_parcel_lineage_event_type",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_parcel_lineage_event_confidence",
        ),
        UniqueConstraint(
            "organization_id",
            "source_id",
            "external_event_id",
            name="uq_parcel_lineage_event_source_external",
        ),
        Index(
            "ix_parcel_lineage_event_org_observed",
            "organization_id",
            "observed_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ingestion_sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_event_id: Mapped[str] = mapped_column(String(500), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attributes: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    source = relationship("IngestionSource")
    participants: Mapped[list["ParcelLineageParticipant"]] = relationship(
        "ParcelLineageParticipant",
        back_populates="event",
        cascade="all, delete-orphan",
    )
    evidence: Mapped[list["ParcelLineageEvidence"]] = relationship(
        "ParcelLineageEvidence",
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="ParcelLineageEvidence.observed_at.desc()",
    )


class ParcelLineageParticipant(OrgMixin, Base):
    """A predecessor or successor parcel in a lineage event."""

    __tablename__ = "parcel_lineage_participants"
    __table_args__ = (
        CheckConstraint(
            "role IN ('predecessor', 'successor')",
            name="ck_parcel_lineage_participant_role",
        ),
        UniqueConstraint(
            "organization_id",
            "event_id",
            "role",
            "external_parcel_id",
            name="uq_parcel_lineage_participant_identity",
        ),
        Index(
            "ix_parcel_lineage_participant_parcel",
            "organization_id",
            "parcel_id",
        ),
        Index(
            "ix_parcel_lineage_participant_unresolved",
            "organization_id",
            "source_id",
            "external_parcel_id",
            "parcel_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    event_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("parcel_lineage_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ingestion_sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    parcel_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("parcel_records.id", ondelete="SET NULL")
    )
    external_parcel_id: Mapped[str] = mapped_column(String(500), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    last_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    event: Mapped[ParcelLineageEvent] = relationship(
        "ParcelLineageEvent", back_populates="participants"
    )
    source = relationship("IngestionSource")
    parcel = relationship("ParcelRecord")


class ParcelLineageEvidence(OrgMixin, Base):
    """Immutable source evidence supporting a parcel lineage event."""

    __tablename__ = "parcel_lineage_evidence"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_parcel_lineage_evidence_confidence",
        ),
        UniqueConstraint(
            "organization_id",
            "event_id",
            "raw_source_record_id",
            name="uq_parcel_lineage_evidence_raw",
        ),
        Index(
            "ix_parcel_lineage_evidence_event",
            "organization_id",
            "event_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    event_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("parcel_lineage_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_source_record_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("raw_source_records.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_url: Mapped[Optional[str]] = mapped_column(String(2000))
    excerpt: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    payload: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    event: Mapped[ParcelLineageEvent] = relationship(
        "ParcelLineageEvent", back_populates="evidence"
    )
    raw_source_record = relationship("RawSourceRecord")
