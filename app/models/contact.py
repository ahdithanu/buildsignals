from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin, SoftDeleteMixin, OwnerMixin


class ContactStatus(str, enum.Enum):
    not_contacted = "not_contacted"
    contacted = "contacted"
    responded = "responded"
    qualified = "qualified"
    dead = "dead"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Contact(OrgMixin, SoftDeleteMixin, OwnerMixin, Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deal_id: Mapped[str] = mapped_column(String(36), ForeignKey("deals.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(100))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    company: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[ContactStatus] = mapped_column(SAEnum(ContactStatus), default=ContactStatus.not_contacted)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # ── Relationships ──────────────────────────────────────────────────────
    organization = relationship("Organization", back_populates="contacts", foreign_keys="[Contact.organization_id]")
    creator = relationship("User", back_populates="created_contacts", foreign_keys="[Contact.created_by]")
    updater = relationship("User", back_populates="updated_contacts", foreign_keys="[Contact.updated_by]")

    deal = relationship("Deal", back_populates="contacts")
    activities = relationship("OutreachActivity", back_populates="contact", cascade="all, delete-orphan")
