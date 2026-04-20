from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, ForeignKey, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import OrgMixin, SoftDeleteMixin, OwnerMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(OrgMixin, SoftDeleteMixin, OwnerMixin, Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deal_id: Mapped[str] = mapped_column(String(36), ForeignKey("deals.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    doc_type: Mapped[Optional[str]] = mapped_column(String(100))
    file_path: Mapped[Optional[str]] = mapped_column(String(1000))
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # ── Relationships ──────────────────────────────────────────────────────
    organization = relationship("Organization", back_populates="documents", foreign_keys="[Document.organization_id]")
    creator = relationship("User", back_populates="created_documents", foreign_keys="[Document.created_by]")
    updater = relationship("User", back_populates="updated_documents", foreign_keys="[Document.updated_by]")

    deal = relationship("Deal", back_populates="documents")
