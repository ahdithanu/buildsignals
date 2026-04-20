"""Reusable column mixins for enterprise hardening."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

DEFAULT_ORG_ID = "default-org"


class OrgMixin:
    """Adds organization_id FK to any model."""
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        default=DEFAULT_ORG_ID,
    )


class SoftDeleteMixin:
    """Adds soft-delete support via deleted_at."""
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, default=None)

    def soft_delete(self) -> None:
        from datetime import timezone
        self.deleted_at = datetime.now(timezone.utc)

    @property
    def is_active(self) -> bool:
        return self.deleted_at is None


class OwnerMixin:
    """Adds created_by / updated_by user tracking."""
    created_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
