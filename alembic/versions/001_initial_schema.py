"""Initial schema with Organization, User, Membership and all business tables.

Revision ID: 001
Revises: None
Create Date: 2026-04-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Organizations ──────────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    # ── Users ──────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ── Organization Memberships ───────────────────────────────────────────
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Enum("admin", "editor", "viewer", name="memberrole"), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_user"),
    )
    op.create_index("ix_org_memberships_org_id", "organization_memberships", ["organization_id"])
    op.create_index("ix_org_memberships_user_id", "organization_memberships", ["user_id"])

    # ── Deals ──────────────────────────────────────────────────────────────
    op.create_table(
        "deals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(50), nullable=True),
        sa.Column("zip_code", sa.String(20), nullable=True),
        sa.Column("property_type", sa.String(100), nullable=True),
        sa.Column("units", sa.Integer(), nullable=True),
        sa.Column("sq_ft", sa.Integer(), nullable=True),
        sa.Column("year_built", sa.Integer(), nullable=True),
        sa.Column("asking_price", sa.Float(), nullable=True),
        sa.Column("status", sa.Enum("new", "qualified", "underwriting", "ic_review", "loi_sent", "psa", "closing", "closed", "dead", name="dealstatus"), nullable=True),
        sa.Column("risk_level", sa.Enum("low", "medium", "high", name="risklevel"), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_deals_organization_id", "deals", ["organization_id"])

    # ── Deal Assumptions ───────────────────────────────────────────────────
    op.create_table(
        "deal_assumptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="CASCADE"), unique=True),
        sa.Column("purchase_price", sa.Float(), nullable=True),
        sa.Column("closing_costs_pct", sa.Float(), nullable=True),
        sa.Column("renovation_cost", sa.Float(), nullable=True),
        sa.Column("loan_amount", sa.Float(), nullable=True),
        sa.Column("interest_rate", sa.Float(), nullable=True),
        sa.Column("loan_term_years", sa.Integer(), nullable=True),
        sa.Column("gross_rental_income", sa.Float(), nullable=True),
        sa.Column("vacancy_pct", sa.Float(), nullable=True),
        sa.Column("opex_pct", sa.Float(), nullable=True),
        sa.Column("cap_rate_market", sa.Float(), nullable=True),
        sa.Column("exit_cap_rate", sa.Float(), nullable=True),
        sa.Column("hold_period_years", sa.Integer(), nullable=True),
        sa.Column("rent_growth_pct", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_deal_assumptions_org_id", "deal_assumptions", ["organization_id"])

    # ── Deal Outputs ───────────────────────────────────────────────────────
    op.create_table(
        "deal_outputs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="CASCADE"), unique=True),
        sa.Column("noi", sa.Float(), nullable=True),
        sa.Column("dscr", sa.Float(), nullable=True),
        sa.Column("cash_on_cash", sa.Float(), nullable=True),
        sa.Column("cap_rate", sa.Float(), nullable=True),
        sa.Column("irr", sa.Float(), nullable=True),
        sa.Column("equity_multiple", sa.Float(), nullable=True),
        sa.Column("total_project_cost", sa.Float(), nullable=True),
        sa.Column("equity_required", sa.Float(), nullable=True),
        sa.Column("annual_debt_service", sa.Float(), nullable=True),
        sa.Column("net_cash_flow", sa.Float(), nullable=True),
        sa.Column("exit_value", sa.Float(), nullable=True),
        sa.Column("profit", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_deal_outputs_org_id", "deal_outputs", ["organization_id"])

    # ── Contacts ───────────────────────────────────────────────────────────
    op.create_table(
        "contacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("status", sa.Enum("not_contacted", "contacted", "responded", "qualified", "dead", name="contactstatus"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_contacts_organization_id", "contacts", ["organization_id"])

    # ── Outreach Activities ────────────────────────────────────────────────
    op.create_table(
        "outreach_activities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="CASCADE")),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("activity_type", sa.Enum("call", "email", "sms", "note", "meeting", "system", name="activitytype"), nullable=True),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("follow_up_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed", sa.Boolean(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_outreach_activities_org_id", "outreach_activities", ["organization_id"])

    # ── Signals ────────────────────────────────────────────────────────────
    op.create_table(
        "signals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("signal_type", sa.String(100), nullable=False),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_signals_organization_id", "signals", ["organization_id"])

    # ── Documents ──────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="CASCADE")),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("doc_type", sa.String(100), nullable=True),
        sa.Column("file_path", sa.String(1000), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_documents_organization_id", "documents", ["organization_id"])

    # ── Memos ──────────────────────────────────────────────────────────────
    op.create_table(
        "memos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="CASCADE"), unique=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_memos_organization_id", "memos", ["organization_id"])

    # ── Pipeline Events ────────────────────────────────────────────────────
    op.create_table(
        "pipeline_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="CASCADE")),
        sa.Column("from_stage", sa.String(50), nullable=False),
        sa.Column("to_stage", sa.String(50), nullable=False),
        sa.Column("changed_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pipeline_events_org_id", "pipeline_events", ["organization_id"])

    # ── Audit Logs ─────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("old_values", sa.Text(), nullable=True),
        sa.Column("new_values", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("pipeline_events")
    op.drop_table("memos")
    op.drop_table("documents")
    op.drop_table("signals")
    op.drop_table("outreach_activities")
    op.drop_table("contacts")
    op.drop_table("deal_outputs")
    op.drop_table("deal_assumptions")
    op.drop_table("deals")
    op.drop_table("organization_memberships")
    op.drop_table("users")
    op.drop_table("organizations")

    # Postgres materializes each `sa.Enum(..., name=...)` as a first-class
    # TYPE, and drop_table does NOT drop it. Without this, a downgrade leaves
    # the enum types behind and a subsequent re-upgrade fails with
    # "type <name> already exists". SQLite has no separate enum type (enums
    # are VARCHAR + CHECK), so this block is Postgres-only.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for enum_name in (
            "activitytype",
            "contactstatus",
            "dealstatus",
            "memberrole",
            "risklevel",
        ):
            op.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))
