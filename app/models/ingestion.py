from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IngestionSource(OrgMixin, Base):
    """Registry entry for an external record provider and its adapter."""

    __tablename__ = "ingestion_sources"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_ingestion_source_org_key"),
        Index("ix_ingestion_source_org_active", "organization_id", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    adapter: Mapped[str] = mapped_column(String(100), nullable=False)
    record_type: Mapped[str] = mapped_column(String(100), nullable=False, default="permit")
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(255))
    base_url: Mapped[Optional[str]] = mapped_column(String(1000))
    settings: Mapped[Optional[dict]] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    field_mappings: Mapped[list["SourceFieldMapping"]] = relationship(
        "SourceFieldMapping", back_populates="source", cascade="all, delete-orphan"
    )
    runs: Mapped[list["IngestionRun"]] = relationship("IngestionRun", back_populates="source")
    raw_records: Mapped[list["RawSourceRecord"]] = relationship("RawSourceRecord", back_populates="source")
    permit_records: Mapped[list["PermitRecord"]] = relationship("PermitRecord", back_populates="source")


class SourceFieldMapping(OrgMixin, Base):
    """Declarative mapping from a provider field to a canonical field path."""

    __tablename__ = "source_field_mappings"
    __table_args__ = (
        UniqueConstraint("source_id", "source_field", name="uq_source_field_mapping"),
        Index("ix_source_field_mapping_canonical", "source_id", "canonical_field"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ingestion_sources.id", ondelete="CASCADE"), nullable=False
    )
    source_field: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_field: Mapped[str] = mapped_column(String(255), nullable=False)
    value_semantics: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown", server_default="unknown"
    )
    transform: Mapped[Optional[str]] = mapped_column(String(100))
    transform_options: Mapped[Optional[dict]] = mapped_column(JSON)
    default_value: Mapped[Optional[dict]] = mapped_column(JSON)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    source: Mapped["IngestionSource"] = relationship("IngestionSource", back_populates="field_mappings")


class IngestionRun(OrgMixin, Base):
    """One bounded attempt to fetch and normalize records from a source."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        Index("ix_ingestion_run_source_started", "source_id", "started_at"),
        Index("ix_ingestion_run_org_status", "organization_id", "status"),
        Index(
            "uq_ingestion_run_source_running",
            "source_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ingestion_sources.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    trigger: Mapped[str] = mapped_column(String(50), nullable=False, default="scheduled")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    checkpoint: Mapped[Optional[dict]] = mapped_column(JSON)
    parameters: Mapped[Optional[dict]] = mapped_column(JSON)
    records_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    source: Mapped["IngestionSource"] = relationship("IngestionSource", back_populates="runs")
    raw_records: Mapped[list["RawSourceRecord"]] = relationship("RawSourceRecord", back_populates="run")


class IngestionCandidateCanaryAttempt(OrgMixin, Base):
    """Persisted audit trail for candidate-source retry canaries."""

    __tablename__ = "ingestion_candidate_canary_attempts"
    __table_args__ = (
        Index("ix_ingestion_candidate_canary_candidate_created", "candidate_key", "created_at"),
        Index("ix_ingestion_candidate_canary_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    candidate_key: Mapped[str] = mapped_column(String(120), nullable=False)
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    records_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_valid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approval_stages: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sample_record_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    next_checkpoint: Mapped[Optional[dict]] = mapped_column(JSON)
    errors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class RawSourceRecord(OrgMixin, Base):
    """Immutable, content-addressed snapshot exactly as supplied by a source."""

    __tablename__ = "raw_source_records"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "external_record_id",
            "content_hash",
            name="uq_raw_source_record_version",
        ),
        Index("ix_raw_source_record_lookup", "source_id", "external_record_id", "received_at"),
        Index("ix_raw_source_record_run", "run_id", "received_at"),
        Index(
            "uq_raw_source_record_id_org",
            "id",
            "organization_id",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ingestion_sources.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ingestion_runs.id", ondelete="RESTRICT"), nullable=False
    )
    external_record_id: Mapped[str] = mapped_column(String(500), nullable=False)
    record_type: Mapped[str] = mapped_column(String(100), nullable=False, default="permit")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    source: Mapped["IngestionSource"] = relationship("IngestionSource", back_populates="raw_records")
    run: Mapped["IngestionRun"] = relationship("IngestionRun", back_populates="raw_records")
    permit_records: Mapped[list["PermitRecord"]] = relationship(
        "PermitRecord", back_populates="latest_raw_record", foreign_keys="[PermitRecord.latest_raw_record_id]"
    )
    permit_events: Mapped[list["PermitEvent"]] = relationship("PermitEvent", back_populates="raw_record")
    observation: Mapped[Optional["RawSourceRecordObservation"]] = relationship(
        "RawSourceRecordObservation",
        back_populates="raw_record",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


@event.listens_for(RawSourceRecord, "before_update")
@event.listens_for(RawSourceRecord, "before_delete")
def _prevent_raw_source_record_mutation(*_args: object) -> None:
    raise ValueError("RawSourceRecord rows are immutable")


class RawSourceRecordObservation(OrgMixin, Base):
    """Mutable last-seen state for an immutable raw content version."""

    __tablename__ = "raw_source_record_observations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["raw_source_record_id", "organization_id"],
            ["raw_source_records.id", "raw_source_records.organization_id"],
            ondelete="CASCADE",
            name="fk_raw_observation_record_org",
        ),
    )

    raw_source_record_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    raw_record: Mapped["RawSourceRecord"] = relationship(
        "RawSourceRecord", back_populates="observation"
    )


class PermitRecord(OrgMixin, Base):
    """Current canonical representation of a permit, independent of provider schema."""

    __tablename__ = "permit_records"
    __table_args__ = (
        UniqueConstraint("source_id", "external_record_id", name="uq_permit_record_source_external"),
        Index("ix_permit_record_org_number", "organization_id", "permit_number"),
        Index("ix_permit_record_org_status", "organization_id", "status"),
        Index("ix_permit_record_org_approval_stage", "organization_id", "approval_stage"),
        Index("ix_permit_record_source_active", "source_id", "is_active"),
        Index("ix_permit_record_location", "organization_id", "state", "city", "postal_code"),
        Index("ix_permit_record_parcel", "organization_id", "parcel_id"),
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
    application_number: Mapped[Optional[str]] = mapped_column(String(255))
    permit_number: Mapped[Optional[str]] = mapped_column(String(255))
    approval_stage: Mapped[Optional[str]] = mapped_column(String(32))
    permit_type: Mapped[Optional[str]] = mapped_column(String(255))
    permit_subtype: Mapped[Optional[str]] = mapped_column(String(255))
    work_class: Mapped[Optional[str]] = mapped_column(String(255))
    review_type: Mapped[Optional[str]] = mapped_column(String(255))
    proposed_use: Mapped[Optional[str]] = mapped_column(String(255))
    occupancy_type: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
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
    contractor_name: Mapped[Optional[str]] = mapped_column(String(500))
    contractor_license: Mapped[Optional[str]] = mapped_column(String(255))
    architect_name: Mapped[Optional[str]] = mapped_column(String(500))
    engineer_name: Mapped[Optional[str]] = mapped_column(String(500))
    valuation: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    square_feet: Mapped[Optional[int]] = mapped_column(Integer)
    units: Mapped[Optional[int]] = mapped_column(Integer)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    filed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[Optional[str]] = mapped_column(String(2000))
    attributes: Mapped[Optional[dict]] = mapped_column(JSON)
    last_seen_snapshot_id: Mapped[Optional[str]] = mapped_column(String(36))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    source: Mapped["IngestionSource"] = relationship("IngestionSource", back_populates="permit_records")
    latest_raw_record: Mapped["RawSourceRecord"] = relationship(
        "RawSourceRecord", back_populates="permit_records", foreign_keys=[latest_raw_record_id]
    )
    events: Mapped[list["PermitEvent"]] = relationship(
        "PermitEvent", back_populates="permit", cascade="all, delete-orphan"
    )


class PermitEvent(OrgMixin, Base):
    """Canonical point-in-time event in a permit's lifecycle."""

    __tablename__ = "permit_events"
    __table_args__ = (
        UniqueConstraint("permit_id", "source_event_id", name="uq_permit_event_source_event"),
        Index("ix_permit_event_timeline", "permit_id", "occurred_at"),
        Index("ix_permit_event_org_type", "organization_id", "event_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    permit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("permit_records.id", ondelete="CASCADE"), nullable=False
    )
    raw_source_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_source_records.id", ondelete="RESTRICT"), nullable=False
    )
    source_event_id: Mapped[str] = mapped_column(String(500), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String(100))
    approval_stage: Mapped[Optional[str]] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    attributes: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    permit: Mapped["PermitRecord"] = relationship("PermitRecord", back_populates="events")
    raw_record: Mapped["RawSourceRecord"] = relationship("RawSourceRecord", back_populates="permit_events")
