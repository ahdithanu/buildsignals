from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DealOutputs(OrgMixin, Base):
    __tablename__ = "deal_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deal_id: Mapped[str] = mapped_column(String(36), ForeignKey("deals.id", ondelete="CASCADE"), unique=True)

    noi: Mapped[Optional[float]] = mapped_column(Float)
    dscr: Mapped[Optional[float]] = mapped_column(Float)
    cash_on_cash: Mapped[Optional[float]] = mapped_column(Float)
    cap_rate: Mapped[Optional[float]] = mapped_column(Float)
    irr: Mapped[Optional[float]] = mapped_column(Float)
    equity_multiple: Mapped[Optional[float]] = mapped_column(Float)
    total_project_cost: Mapped[Optional[float]] = mapped_column(Float)
    equity_required: Mapped[Optional[float]] = mapped_column(Float)
    annual_debt_service: Mapped[Optional[float]] = mapped_column(Float)
    net_cash_flow: Mapped[Optional[float]] = mapped_column(Float)
    exit_value: Mapped[Optional[float]] = mapped_column(Float)
    profit: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    organization = relationship("Organization", foreign_keys="[DealOutputs.organization_id]")
    deal = relationship("Deal", back_populates="outputs")
