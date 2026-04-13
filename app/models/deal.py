from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Float, Text, Enum as SAEnum, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin, SoftDeleteMixin


class DealStatus(str, enum.Enum):
    new = "new"
    qualified = "qualified"
    underwriting = "underwriting"
    ic_review = "ic_review"
    loi_sent = "loi_sent"
    psa = "psa"
    closing = "closing"
    closed = "closed"
    dead = "dead"


class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Deal(OrgMixin, SoftDeleteMixin, Base):
    __tablename__ = "deals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(500))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(50))
    zip_code: Mapped[Optional[str]] = mapped_column(String(20))
    property_type: Mapped[Optional[str]] = mapped_column(String(100))
    units: Mapped[Optional[int]] = mapped_column()
    sq_ft: Mapped[Optional[int]] = mapped_column()
    year_built: Mapped[Optional[int]] = mapped_column()
    asking_price: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[DealStatus] = mapped_column(SAEnum(DealStatus), default=DealStatus.new)
    risk_level: Mapped[Optional[RiskLevel]] = mapped_column(SAEnum(RiskLevel))
    score: Mapped[Optional[float]] = mapped_column(Float)
    source: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # relationships
    assumptions = relationship("DealAssumptions", back_populates="deal", uselist=False, cascade="all, delete-orphan")
    outputs = relationship("DealOutputs", back_populates="deal", uselist=False, cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="deal", cascade="all, delete-orphan")
    activities = relationship("OutreachActivity", back_populates="deal", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="deal", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="deal", cascade="all, delete-orphan")
    memo = relationship("Memo", back_populates="deal", uselist=False, cascade="all, delete-orphan")
    pipeline_events = relationship("PipelineEvent", back_populates="deal", cascade="all, delete-orphan")
