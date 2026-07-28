from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Incremented by /auth/logout-all to invalidate every outstanding refresh
    # token for this user. The current tv is embedded as a claim in access
    # and refresh tokens; /auth/refresh compares the cookie's tv against the
    # row's tv and 401s on mismatch. Cheap (one int per row, no extra writes
    # per refresh) and survives without Redis.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    # ── 2FA (TOTP) ─────────────────────────────────────────────────────────
    # `totp_secret` is the base32 shared secret stored at /auth/2fa/setup
    # time. It exists *before* the user confirms enrollment with /verify, so
    # presence of a secret alone doesn't mean 2FA is enforced — that's what
    # `totp_enabled` is for. /auth/login only requires a TOTP code when
    # totp_enabled is True. /auth/2fa/disable clears both.
    totp_secret: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", default=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # ── Relationships ──────────────────────────────────────────────────────
    memberships: Mapped[List["OrganizationMembership"]] = relationship(
        "OrganizationMembership", back_populates="user", cascade="all, delete-orphan"
    )

    # Ownership back-refs (created_by / updated_by)
    created_deals: Mapped[List["Deal"]] = relationship(  # type: ignore[name-defined]
        "Deal", back_populates="creator", foreign_keys="[Deal.created_by]"
    )
    updated_deals: Mapped[List["Deal"]] = relationship(  # type: ignore[name-defined]
        "Deal", back_populates="updater", foreign_keys="[Deal.updated_by]"
    )
    created_contacts: Mapped[List["Contact"]] = relationship(  # type: ignore[name-defined]
        "Contact", back_populates="creator", foreign_keys="[Contact.created_by]"
    )
    updated_contacts: Mapped[List["Contact"]] = relationship(  # type: ignore[name-defined]
        "Contact", back_populates="updater", foreign_keys="[Contact.updated_by]"
    )
    created_memos: Mapped[List["Memo"]] = relationship(  # type: ignore[name-defined]
        "Memo", back_populates="creator", foreign_keys="[Memo.created_by]"
    )
    updated_memos: Mapped[List["Memo"]] = relationship(  # type: ignore[name-defined]
        "Memo", back_populates="updater", foreign_keys="[Memo.updated_by]"
    )
    created_documents: Mapped[List["Document"]] = relationship(  # type: ignore[name-defined]
        "Document", back_populates="creator", foreign_keys="[Document.created_by]"
    )
    updated_documents: Mapped[List["Document"]] = relationship(  # type: ignore[name-defined]
        "Document", back_populates="updater", foreign_keys="[Document.updated_by]"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(  # type: ignore[name-defined]
        "AuditLog", back_populates="actor", foreign_keys="[AuditLog.actor_id]"
    )
    buy_boxes: Mapped[List["BuyBox"]] = relationship(  # type: ignore[name-defined]
        "BuyBox", back_populates="user", foreign_keys="[BuyBox.user_id]"
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
