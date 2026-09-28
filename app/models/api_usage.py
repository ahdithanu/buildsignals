from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
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
