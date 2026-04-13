from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin


class ActivityType(str, enum.Enum):
    call = "call"
    email = "email"
    sms = "sms"
    note = "note"
    meeting = "meeting"
    system = "system"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OutreachActivity(OrgMixin, Base):
    __tablename__ = "outreach_activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deal_id: Mapped[str] = mapped_column(String(36), ForeignKey("deals.id", ondelete="CASCADE"))
    contact_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("contacts.id", ondelete="SET NULL"))
    activity_type: Mapped[ActivityType] = mapped_column(SAEnum(ActivityType))
    subject: Mapped[Optional[str]] = mapped_column(String(500))
    body: Mapped[Optional[str]] = mapped_column(Text)
    follow_up_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    deal = relationship("Deal", back_populates="activities")
    contact = relationship("Contact", back_populates="activities")
