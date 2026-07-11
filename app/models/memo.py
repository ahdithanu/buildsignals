from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin, OwnerMixin, SoftDeleteMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Memo(OrgMixin, SoftDeleteMixin, OwnerMixin, Base):
    __tablename__ = "memos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deal_id: Mapped[str] = mapped_column(String(36), ForeignKey("deals.id", ondelete="CASCADE"), unique=True)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    content: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # ── Relationships ──────────────────────────────────────────────────────
    organization = relationship("Organization", back_populates="memos", foreign_keys="[Memo.organization_id]")
    creator = relationship("User", back_populates="created_memos", foreign_keys="[Memo.created_by]")
    updater = relationship("User", back_populates="updated_memos", foreign_keys="[Memo.updated_by]")

    deal = relationship("Deal", back_populates="memo")
