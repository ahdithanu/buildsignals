"""Enable row-level security on audit_logs.

audit_logs (organization_id NOT NULL, created in migration 001) is tenant data
but was never given RLS — migration 003 and the later "complete_tenant_rls"
sweep both omit it. app/routes/audit.py already filters reads by
organization_id, so there is no live leak today, but the DB-level backstop that
every other tenant table has is missing: a future raw query/join that forgets
the filter would expose one tenant's audit trail to another.

READ isolation is the security goal here (don't leak another tenant's audit
history). The policy is deliberately looser than the other tenant tables: audit
rows are written server-side from many contexts, INCLUDING pre-auth bootstrap
flows — most importantly registration, which writes an audit row tagged with a
brand-new org id while the transaction's app.current_org is still the bootstrap
value 'default-org' (the request is unauthenticated). A strict policy would 500
every registration — and note `INSERT ... RETURNING` (which SQLAlchemy may emit)
applies the SELECT/USING policy to the returned row too, so carving out only
WITH CHECK is not enough. So BOTH clauses additionally permit the 'default-org'
bootstrap context.

Net effect:
  * A real tenant (app.current_org = a real org id) can only read/write its own
    audit rows — full isolation, exactly the property the finding wanted.
  * The 'default-org' bootstrap/system context (registration, background jobs,
    and — only in dev, where ALLOW_ANONYMOUS is true — unauthenticated requests)
    is unconstrained. In deployed envs ALLOW_ANONYMOUS is false, so no
    authenticated request ever runs as 'default-org', and the audit reader
    (routes/audit.py, auth-required) therefore always carries a real org.

audit_logs are never written from client-controlled input, so write-forgery is
not the threat model; cross-tenant READ by a real tenant is, and this blocks it.
Postgres-only (SQLite dev/test relies on app-layer scoping).
"""
from __future__ import annotations

from typing import Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260915_0001"
down_revision: Union[str, None] = "20260909_0002"
branch_labels = None
depends_on = None

_TABLE = "audit_logs"
# The bootstrap/system org context set by get_org_id() when no auth context
# exists (app.utils.org_scope.DEFAULT_ORG_ID). Registration and other pre-auth
# audit writes run under this context.
_BOOTSTRAP_ORG = "default-org"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f'ALTER TABLE "{_TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{_TABLE}" FORCE ROW LEVEL SECURITY')
    op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{_TABLE}"')
    op.execute(
        f"""CREATE POLICY tenant_isolation ON "{_TABLE}"
        USING (
            organization_id = current_setting('app.current_org', true)
            OR current_setting('app.current_org', true) = '{_BOOTSTRAP_ORG}'
        )
        WITH CHECK (
            organization_id = current_setting('app.current_org', true)
            OR current_setting('app.current_org', true) = '{_BOOTSTRAP_ORG}'
        )"""
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{_TABLE}"')
    op.execute(f'ALTER TABLE "{_TABLE}" NO FORCE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{_TABLE}" DISABLE ROW LEVEL SECURITY')
