from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Float, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BuyBox(OrgMixin, Base):
    __tablename__ = "buy_boxes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    asset_type: Mapped[Optional[str]] = mapped_column(String(100))
    locations: Mapped[Optional[str]] = mapped_column(Text)  # comma-separated or JSON
    min_price: Mapped[Optional[float]] = mapped_column(Float)
    max_price: Mapped[Optional[float]] = mapped_column(Float)
    min_irr: Mapped[Optional[float]] = mapped_column(Float)
    deal_type: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # ── Relationships ──────────────────────────────────────────────────────
    organization = relationship("Organization", back_populates="buy_boxes", foreign_keys="[BuyBox.organization_id]")
    user = relationship("User", back_populates="buy_boxes", foreign_keys="[BuyBox.user_id]")
