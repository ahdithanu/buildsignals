"""Derived address-range locations, separate from immutable permit source evidence."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import OrgMixin


class PermitGeocode(OrgMixin, Base):
    __tablename__ = "permit_geocodes"
    __table_args__ = (UniqueConstraint("organization_id", "permit_id", name="uq_permit_geocodes_org_permit"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    permit_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("permit_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    address_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    matched_address: Mapped[str] = mapped_column(String(500), nullable=False)
    benchmark: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                   default=lambda: datetime.now(timezone.utc))
