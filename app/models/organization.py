from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # ── Relationships ──────────────────────────────────────────────────────
    memberships: Mapped[List["OrganizationMembership"]] = relationship(
        "OrganizationMembership", back_populates="organization", cascade="all, delete-orphan"
    )
    deals: Mapped[List["Deal"]] = relationship(  # type: ignore[name-defined]
        "Deal", back_populates="organization", foreign_keys="[Deal.organization_id]"
    )
    contacts: Mapped[List["Contact"]] = relationship(  # type: ignore[name-defined]
        "Contact", back_populates="organization", foreign_keys="[Contact.organization_id]"
    )
    activities: Mapped[List["OutreachActivity"]] = relationship(  # type: ignore[name-defined]
        "OutreachActivity", back_populates="organization", foreign_keys="[OutreachActivity.organization_id]"
    )
    signals: Mapped[List["Signal"]] = relationship(  # type: ignore[name-defined]
        "Signal", back_populates="organization", foreign_keys="[Signal.organization_id]"
    )
    documents: Mapped[List["Document"]] = relationship(  # type: ignore[name-defined]
        "Document", back_populates="organization", foreign_keys="[Document.organization_id]"
    )
    memos: Mapped[List["Memo"]] = relationship(  # type: ignore[name-defined]
        "Memo", back_populates="organization", foreign_keys="[Memo.organization_id]"
    )
    pipeline_events: Mapped[List["PipelineEvent"]] = relationship(  # type: ignore[name-defined]
        "PipelineEvent", back_populates="organization", foreign_keys="[PipelineEvent.organization_id]"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(  # type: ignore[name-defined]
        "AuditLog", back_populates="organization", foreign_keys="[AuditLog.organization_id]"
    )
    buy_boxes: Mapped[List["BuyBox"]] = relationship(  # type: ignore[name-defined]
        "BuyBox", back_populates="organization", foreign_keys="[BuyBox.organization_id]"
    )
    distributions: Mapped[List["DealDistribution"]] = relationship(  # type: ignore[name-defined]
        "DealDistribution", back_populates="organization", foreign_keys="[DealDistribution.organization_id]"
    )

    def __repr__(self) -> str:
        return f"<Organization {self.slug}>"
