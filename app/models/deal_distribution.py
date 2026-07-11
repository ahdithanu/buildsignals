from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DealDistribution(OrgMixin, Base):
    __tablename__ = "deal_distributions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    recipient_name: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    status: Mapped[Optional[str]] = mapped_column(String(50), default="logged")  # logged | sent | failed
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # ── Relationships ──────────────────────────────────────────────────────
    organization = relationship("Organization", back_populates="distributions", foreign_keys="[DealDistribution.organization_id]")
    deal = relationship("Deal", back_populates="distributions", foreign_keys="[DealDistribution.deal_id]")
