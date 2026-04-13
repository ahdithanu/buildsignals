from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Float, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DealAssumptions(OrgMixin, Base):
    __tablename__ = "deal_assumptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deal_id: Mapped[str] = mapped_column(String(36), ForeignKey("deals.id", ondelete="CASCADE"), unique=True)

    purchase_price: Mapped[Optional[float]] = mapped_column(Float)
    closing_costs_pct: Mapped[Optional[float]] = mapped_column(Float, default=0.02)
    renovation_cost: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    loan_amount: Mapped[Optional[float]] = mapped_column(Float)
    interest_rate: Mapped[Optional[float]] = mapped_column(Float, default=0.065)
    loan_term_years: Mapped[Optional[int]] = mapped_column(default=30)
    gross_rental_income: Mapped[Optional[float]] = mapped_column(Float)
    vacancy_pct: Mapped[Optional[float]] = mapped_column(Float, default=0.05)
    opex_pct: Mapped[Optional[float]] = mapped_column(Float, default=0.35)
    cap_rate_market: Mapped[Optional[float]] = mapped_column(Float, default=0.06)
    exit_cap_rate: Mapped[Optional[float]] = mapped_column(Float, default=0.065)
    hold_period_years: Mapped[Optional[int]] = mapped_column(default=5)
    rent_growth_pct: Mapped[Optional[float]] = mapped_column(Float, default=0.03)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    deal = relationship("Deal", back_populates="assumptions")
