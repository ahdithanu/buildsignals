from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrganizationIngestionEnrollment(Base):
    """Tenant control-plane state for catalog-backed ingestion activation."""

    __tablename__ = "organization_ingestion_enrollments"
    __table_args__ = (Index("ix_ingestion_enrollments_enabled", "enabled", "organization_id"),)

    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    coverage_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="nationwide", server_default="nationwide"
    )
    state_codes: Mapped[Optional[list[str]]] = mapped_column(JSON)
    record_types: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    rollout_waves: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    shard_count: Mapped[int] = mapped_column(Integer, nullable=False, default=4, server_default="4")
    catalog_manifest_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    last_catalog_sync_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    last_dispatch_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class OrganizationIngestionEnrollmentSource(Base):
    """One reviewed catalog source enrolled for one organization."""

    __tablename__ = "organization_ingestion_enrollment_sources"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_key",
            name="uq_ingestion_enrollment_source_org_key",
        ),
        Index(
            "ix_ingestion_enrollment_sources_due",
            "status",
            "next_run_at",
            "organization_id",
        ),
        Index(
            "ix_ingestion_enrollment_sources_org_status",
            "organization_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "organization_ingestion_enrollments.organization_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    ingestion_source_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("ingestion_sources.id", ondelete="SET NULL")
    )
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    record_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )
    cadence_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    max_pages_per_run: Mapped[int] = mapped_column(Integer, nullable=False)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[Optional[str]] = mapped_column(String(64))
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
