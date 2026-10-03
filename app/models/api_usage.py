from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrganizationApiKeyUsageEvent(Base):
    __tablename__ = "organization_api_key_usage_events"
    __table_args__ = (
        Index("ix_api_key_usage_org_created", "organization_id", "created_at"),
        Index("ix_api_key_usage_key_created", "api_key_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_key_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organization_api_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    method: Mapped[str] = mapped_column(String(12), nullable=False)
    path: Mapped[str] = mapped_column(String(240), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_items: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    organization = relationship("Organization", foreign_keys="[OrganizationApiKeyUsageEvent.organization_id]")
    api_key = relationship("OrganizationApiKey", foreign_keys="[OrganizationApiKeyUsageEvent.api_key_id]")


class OrganizationApiKeyUsageDailyRollup(Base):
    __tablename__ = "organization_api_key_usage_daily_rollups"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "api_key_id",
            "usage_date",
            "method",
            "path",
            name="uq_api_key_usage_daily_rollup_bucket",
        ),
        Index("ix_api_key_usage_daily_rollups_org_date", "organization_id", "usage_date"),
        Index("ix_api_key_usage_daily_rollups_key_date", "api_key_id", "usage_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_key_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organization_api_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(12), nullable=False)
    path: Mapped[str] = mapped_column(String(240), nullable=False)
    total_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    organization = relationship("Organization", foreign_keys="[OrganizationApiKeyUsageDailyRollup.organization_id]")
    api_key = relationship("OrganizationApiKey", foreign_keys="[OrganizationApiKeyUsageDailyRollup.api_key_id]")
