from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrganizationApiKey(Base):
    __tablename__ = "organization_api_keys"
    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_organization_api_keys_key_hash"),
        Index("ix_organization_api_keys_active", "organization_id", "revoked_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization = relationship("Organization", foreign_keys="[OrganizationApiKey.organization_id]")
    creator = relationship("User", foreign_keys="[OrganizationApiKey.created_by]")
    revoker = relationship("User", foreign_keys="[OrganizationApiKey.revoked_by]")
