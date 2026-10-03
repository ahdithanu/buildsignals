"""Tenant-scoped evaluation datasets, runs, results, and normalized metrics."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import OrgMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EvalDataset(OrgMixin, Base):
    __tablename__ = "eval_dataset"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_eval_dataset_org_name"),
        UniqueConstraint("organization_id", "id", name="uq_eval_dataset_org_id"),
        CheckConstraint(
            "workflow IN ('copilot_answer', 'opportunity_memo', "
            "'multi_agent_research', 'score_explanation')",
            name="ck_eval_dataset_workflow",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''")
    )
    workflow: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class EvalCase(OrgMixin, Base):
    __tablename__ = "eval_case"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_eval_case_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "dataset_id"],
            ["eval_dataset.organization_id", "eval_dataset.id"],
            name="fk_eval_case_dataset_org",
            ondelete="CASCADE",
        ),
        Index("ix_eval_case_org_dataset", "organization_id", "dataset_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    expected_output: Mapped[dict] = mapped_column(JSON, nullable=False)
    retrieved_context: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class EvalRun(OrgMixin, Base):
    __tablename__ = "eval_run"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_eval_run_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "dataset_id"],
            ["eval_dataset.organization_id", "eval_dataset.id"],
            name="fk_eval_run_dataset_org",
            ondelete="CASCADE",
        ),
        CheckConstraint("mode IN ('live', 'replay')", name="ck_eval_run_mode"),
        CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_eval_run_status"),
        Index("ix_eval_run_org_dataset", "organization_id", "dataset_id"),
        Index("ix_eval_run_org_started_at", "organization_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    thresholds: Mapped[dict] = mapped_column(JSON, nullable=False)
    summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    gate_passed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvalResult(OrgMixin, Base):
    __tablename__ = "eval_result"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_eval_result_org_id"),
        UniqueConstraint("run_id", "case_id", name="uq_eval_result_run_case"),
        ForeignKeyConstraint(
            ["organization_id", "run_id"],
            ["eval_run.organization_id", "eval_run.id"],
            name="fk_eval_result_run_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "case_id"],
            ["eval_case.organization_id", "eval_case.id"],
            name="fk_eval_result_case_org",
            ondelete="CASCADE",
        ),
        CheckConstraint("status IN ('passed', 'failed', 'error')", name="ck_eval_result_status"),
        Index("ix_eval_result_org_run", "organization_id", "run_id"),
        Index("ix_eval_result_org_case", "organization_id", "case_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False)
    case_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    actual_output: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    retrieved_context: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(200), nullable=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    tokens_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class EvalMetric(OrgMixin, Base):
    __tablename__ = "eval_metric"
    __table_args__ = (
        UniqueConstraint("result_id", "name", name="uq_eval_metric_result_name"),
        ForeignKeyConstraint(
            ["organization_id", "result_id"],
            ["eval_result.organization_id", "eval_result.id"],
            name="fk_eval_metric_result_org",
            ondelete="CASCADE",
        ),
        CheckConstraint("value >= 0 AND value <= 1", name="ck_eval_metric_normalized"),
        Index("ix_eval_metric_org_result", "organization_id", "result_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    result_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
