"""Tenant-scoped AI workflow usage rollups for billing readiness."""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AiWorkflowUsageDailyRollup(Base):
    __tablename__ = "ai_workflow_usage_daily_rollups"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "usage_date",
            "workflow",
            "model",
            "prompt_version",
            name="uq_ai_workflow_usage_daily_rollup_bucket",
        ),
        Index("ix_ai_workflow_usage_daily_org_date", "organization_id", "usage_date"),
        Index("ix_ai_workflow_usage_daily_org_workflow", "organization_id", "workflow"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    workflow: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(200), nullable=False)
    total_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_results: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    known_cost_results: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    known_token_results: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    known_latency_results: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens_input: Mapped[int | None] = mapped_column(Integer)
    total_tokens_output: Mapped[int | None] = mapped_column(Integer)
    total_latency_ms: Mapped[float | None] = mapped_column(Float)
    total_cost_usd: Mapped[float | None] = mapped_column(Float)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    organization = relationship("Organization", foreign_keys="[AiWorkflowUsageDailyRollup.organization_id]")
