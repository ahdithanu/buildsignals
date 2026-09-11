from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class BrowserSession(Base):
    """Authentication state, not tenant business data. IDs are not credentials."""

    __tablename__ = "browser_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    browser_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    client_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
