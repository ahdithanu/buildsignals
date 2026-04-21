"""Enable Postgres row-level security for all tenant tables.

Revision ID: 003
Revises: 002
Create Date: 2026-04-20

Adds defence-in-depth below the application-layer org scoping (PR #3):
even if a code path forgets to call `scope_query(...)`, Postgres will
silently filter rows to `organization_id = current_setting('app.current_org')`.

App-side, the session sets `app.current_org` at the start of every
transaction (see app/db.py). Without that setting the policy evaluates
to false and no rows are visible.

SQLite has no concept of policies, so the migration is a no-op there.
This lets local/dev/test remain on SQLite while prod (Postgres) gets
real RLS enforcement.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every table that carries an organization_id (OrgMixin).
TENANT_TABLES: tuple[str, ...] = (
    "deals",
    "deal_assumptions",
    "deal_outputs",
    "deal_distributions",
    "contacts",
    "outreach_activities",
    "signals",
    "documents",
    "memos",
    "pipeline_events",
    "buy_boxes",
)

POLICY_NAME = "tenant_isolation"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        # SQLite / other backends: RLS is not supported. App-layer scoping
        # (scope_query / active_query) is the sole enforcement in dev.
        return

    for tbl in TENANT_TABLES:
        # Enable + force RLS. FORCE is required because the owner role
        # (typically the app's DB user) is otherwise exempt from policies.
        op.execute(f'ALTER TABLE "{tbl}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{tbl}" FORCE ROW LEVEL SECURITY')

        # Recreate cleanly in case a prior partial run left the policy.
        op.execute(f'DROP POLICY IF EXISTS {POLICY_NAME} ON "{tbl}"')
        op.execute(
            f"""
            CREATE POLICY {POLICY_NAME} ON "{tbl}"
                USING (organization_id = current_setting('app.current_org', true))
                WITH CHECK (organization_id = current_setting('app.current_org', true))
            """
        )


def downgrade() -> None:
    if not _is_postgres():
        return

    for tbl in TENANT_TABLES:
        op.execute(f'DROP POLICY IF EXISTS {POLICY_NAME} ON "{tbl}"')
        op.execute(f'ALTER TABLE "{tbl}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{tbl}" DISABLE ROW LEVEL SECURITY')
