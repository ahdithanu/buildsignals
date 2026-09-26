"""Immutable, tenant-owned prompt templates and versions."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import OrgMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PromptTemplate(OrgMixin, Base):
    __tablename__ = "prompt_template"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_prompt_template_org_key"),
        UniqueConstraint("organization_id", "id", name="uq_prompt_template_org_id"),
        CheckConstraint(
            "workflow IN ('copilot_answer', 'opportunity_memo', 'multi_agent_research', 'score_explanation')",
            name="ck_prompt_template_workflow",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    workflow: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    active_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class PromptVersion(OrgMixin, Base):
    __tablename__ = "prompt_version"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "template_id"],
            ["prompt_template.organization_id", "prompt_template.id"],
            name="fk_prompt_version_template_org", ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "template_id", "version", name="uq_prompt_version_org_template_version"),
        Index("ix_prompt_version_org_template", "organization_id", "template_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    template_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
