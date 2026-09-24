"""Add tenant-scoped immutable prompt registry."""

import sqlalchemy as sa

from alembic import op

revision = "20260924_0001"
down_revision = "20260923_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_template",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("workflow", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("active_version", sa.Integer()),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "key", name="uq_prompt_template_org_key"),
        sa.UniqueConstraint("organization_id", "id", name="uq_prompt_template_org_id"),
        sa.CheckConstraint(
            "workflow IN ('copilot_answer', 'opportunity_memo', 'multi_agent_research', 'score_explanation')",
            name="ck_prompt_template_workflow",
        ),
    )
    op.create_table(
        "prompt_version",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("variables", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["organization_id", "template_id"], ["prompt_template.organization_id", "prompt_template.id"],
            name="fk_prompt_version_template_org", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("organization_id", "template_id", "version", name="uq_prompt_version_org_template_version"),
    )
    op.create_index("ix_prompt_template_organization_id", "prompt_template", ["organization_id"])
    op.create_index("ix_prompt_version_organization_id", "prompt_version", ["organization_id"])
    op.create_index("ix_prompt_version_org_template", "prompt_version", ["organization_id", "template_id"])
    if op.get_bind().dialect.name == "postgresql":
        for table in ("prompt_template", "prompt_version"):
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(
                f'CREATE POLICY tenant_isolation ON "{table}" '
                "USING (organization_id = current_setting('app.current_org', true)) "
                "WITH CHECK (organization_id = current_setting('app.current_org', true))"
            )
        op.execute(
            """CREATE FUNCTION prevent_prompt_version_content_mutation()
            RETURNS trigger AS $$
            BEGIN
                IF OLD.organization_id IS DISTINCT FROM NEW.organization_id
                   OR OLD.template_id IS DISTINCT FROM NEW.template_id
                   OR OLD.version IS DISTINCT FROM NEW.version
                   OR OLD.body IS DISTINCT FROM NEW.body
                   OR OLD.variables IS DISTINCT FROM NEW.variables
                   OR OLD.checksum IS DISTINCT FROM NEW.checksum
                   OR OLD.created_by IS DISTINCT FROM NEW.created_by
                   OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
                    RAISE EXCEPTION 'prompt version content is immutable';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql SET search_path = pg_catalog, public"""
        )
        op.execute(
            "CREATE TRIGGER trg_prompt_version_content_immutable BEFORE UPDATE ON prompt_version "
            "FOR EACH ROW EXECUTE FUNCTION prevent_prompt_version_content_mutation()"
        )
    elif op.get_bind().dialect.name == "sqlite":
        op.execute(
            """CREATE TRIGGER trg_prompt_version_content_immutable
            BEFORE UPDATE ON prompt_version
            WHEN OLD.organization_id IS NOT NEW.organization_id
              OR OLD.template_id IS NOT NEW.template_id
              OR OLD.version IS NOT NEW.version
              OR OLD.body IS NOT NEW.body
              OR OLD.variables IS NOT NEW.variables
              OR OLD.checksum IS NOT NEW.checksum
              OR OLD.created_by IS NOT NEW.created_by
              OR OLD.created_at IS NOT NEW.created_at
            BEGIN
                SELECT RAISE(ABORT, 'prompt version content is immutable');
            END"""
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_prompt_version_content_immutable ON prompt_version")
        op.execute("DROP FUNCTION IF EXISTS prevent_prompt_version_content_mutation()")
    elif op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_prompt_version_content_immutable")
    op.drop_table("prompt_version")
    op.drop_table("prompt_template")
