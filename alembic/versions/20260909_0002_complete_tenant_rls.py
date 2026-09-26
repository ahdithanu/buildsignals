"""Enforce tenant isolation on four later-added ingestion/planning tables."""
from alembic import op

revision = "20260909_0002"
down_revision = "20260909_0001"
branch_labels = None
depends_on = None

TABLES = (
    "ingestion_candidate_canary_attempts",
    "planning_records",
    "planning_company_matches",
    "record_external_references",
)


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY tenant_isolation ON "{table}" '
            "USING (organization_id = current_setting('app.current_org', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org', true))"
        )


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in reversed(TABLES):
        op.execute(f'DROP POLICY tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
