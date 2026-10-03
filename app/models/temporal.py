"""Append-only observations and events, independent of mutable graph identities."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import OrgMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TemporalObservation(OrgMixin, Base):
    """A source-backed attribute snapshot with separate effective and known times."""

    __tablename__ = "temporal_observations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["raw_source_record_id", "organization_id"],
            ["raw_source_records.id", "raw_source_records.organization_id"],
            ondelete="RESTRICT",
            name="fk_temporal_observation_raw_record_org",
        ),
        UniqueConstraint("id", "organization_id", name="uq_temporal_observation_id_org"),
        UniqueConstraint(
            "organization_id", "observation_key", name="uq_temporal_observation_org_key"
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_temporal_observation_confidence"
        ),
        Index(
            "ix_temporal_observation_org_series_recorded",
            "organization_id", "series_key", "recorded_at",
        ),
        Index(
            "ix_temporal_observation_org_entity_attribute_recorded",
            "organization_id", "entity_id", "attribute", "recorded_at",
        ),
        Index("ix_temporal_observation_org_effective", "organization_id", "effective_at"),
        Index(
            "ix_temporal_observation_cohort_known",
            "organization_id", "source_id", "attribute", "methodology_version", "recorded_at",
        ),
        Index(
            "ix_temporal_observation_raw_attribute_method",
            "organization_id", "raw_source_record_id", "attribute", "methodology_version", "recorded_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # Creation validates tenant ownership; graph merges must not rewrite this snapshot.
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    raw_source_record_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ingestion_sources.id", ondelete="RESTRICT"), nullable=False
    )
    observation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    series_key: Mapped[str] = mapped_column(String(64), nullable=False)
    attribute: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[Any] = mapped_column(JSON(none_as_null=False), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The creation service supplies raw_source_records.received_at, never the request clock.
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_system: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    geography: Mapped[Any] = mapped_column(JSON, nullable=True)
    methodology_version: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


@event.listens_for(TemporalObservation, "before_update")
@event.listens_for(TemporalObservation, "before_delete")
def _prevent_temporal_observation_mutation(*_args: object) -> None:
    raise ValueError("TemporalObservation rows are immutable")


class TemporalEvent(OrgMixin, Base):
    """An immutable event whose entity and provenance are obtained through its observation."""

    __tablename__ = "temporal_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["observation_id", "organization_id"],
            ["temporal_observations.id", "temporal_observations.organization_id"],
            ondelete="RESTRICT",
            name="fk_temporal_event_observation_org",
        ),
        UniqueConstraint(
            "organization_id", "observation_id", "event_type",
            name="uq_temporal_event_org_observation_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    observation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


@event.listens_for(TemporalEvent, "before_update")
@event.listens_for(TemporalEvent, "before_delete")
def _prevent_temporal_event_mutation(*_args: object) -> None:
    raise ValueError("TemporalEvent rows are immutable")
