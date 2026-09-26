"""Reconcile legacy nullability and indexes without inventing historical data.

Run online, during a maintenance window, as the PostgreSQL table owner (or
superuser). PostgreSQL holds ACCESS EXCLUSIVE locks and temporarily relaxes
FORCE RLS in the same transaction so preflight sees every tenant. Policies and
their original FORCE flags are preserved. PostGIS objects are untouched.

SQLite uses transactional batch rebuilds with foreign_keys OFF on this dedicated
migration connection (the existing Alembic environment's default). Never toggle
that pragma inside a transaction: refuse instead of risking cascade deletion.
Foreign-key validity is checked before and after, and existing triggers survive.

NULL historical values abort the entire revision with per-column counts. Repair
them from authoritative records before retrying; no backfill or DELETE is used.
Legacy server defaults, enum types, and useful composite indexes are retained.
"""
from __future__ import annotations

from contextlib import contextmanager

import sqlalchemy as sa

from alembic import op

revision = "20260923_0001"
down_revision = "20260920_0001"
branch_labels = None
depends_on = None

# Explicitly reviewed differences from 001/002, not runtime model metadata.
REQUIRED = {
    "audit_logs": ("created_at",),
    "buy_boxes": ("created_at",),
    "contacts": ("deal_id", "status", "created_at", "updated_at"),
    "deal_assumptions": ("deal_id", "created_at", "updated_at"),
    "deal_distributions": ("sent_at",),
    "deal_outputs": ("deal_id", "created_at", "updated_at"),
    "deals": ("status", "created_at", "updated_at"),
    "documents": ("deal_id", "uploaded_at"),
    "memos": ("deal_id", "version", "created_at", "updated_at"),
    "organization_memberships": ("joined_at",),
    "organizations": ("created_at", "updated_at"),
    "outreach_activities": ("deal_id", "activity_type", "completed", "created_at"),
    "pipeline_events": ("deal_id", "created_at"),
    "signals": ("created_at",),
    "users": ("created_at", "updated_at"),
}
RENAMED = (
    ("buy_boxes", "organization_id", "ix_buy_boxes_org_id"),
    ("deal_assumptions", "organization_id", "ix_deal_assumptions_org_id"),
    ("deal_distributions", "organization_id", "ix_deal_distributions_org_id"),
    ("deal_outputs", "organization_id", "ix_deal_outputs_org_id"),
    ("organization_memberships", "organization_id", "ix_org_memberships_org_id"),
    ("organization_memberships", "user_id", "ix_org_memberships_user_id"),
    ("outreach_activities", "organization_id", "ix_outreach_activities_org_id"),
    ("pipeline_events", "organization_id", "ix_pipeline_events_org_id"),
)
ADDED = (
    ("graph_relationships", "is_current"),
    ("ingestion_candidate_canary_attempts", "organization_id"),
    ("planning_company_matches", "organization_id"),
    ("planning_records", "organization_id"),
)
# PostgreSQL names automatically named constraints; SQLite leaves them unnamed.
UNIQUE = (
    ("organizations", "slug", "organizations_slug_key"),
    ("users", "email", "users_email_key"),
    ("password_reset_tokens", "token_hash", "uq_password_reset_tokens_token_hash"),
)
TABLES = tuple(sorted(set(REQUIRED) | {table for table, _, _ in UNIQUE}))


def _foreign_key_check(bind):
    violations = bind.exec_driver_sql("PRAGMA foreign_key_check").fetchmany(10)
    if violations:
        tables = sorted({row[0] for row in violations})
        raise RuntimeError(
            "Schema reconciliation preflight: SQLite foreign-key violations in "
            + ", ".join(tables) + "; repair authoritative references before retrying."
        )


@contextmanager
def _maintenance():
    context = op.get_context()
    if context.as_sql:
        raise RuntimeError("Schema reconciliation requires an online data preflight; --sql is unsafe.")
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        if bind.exec_driver_sql("PRAGMA foreign_keys").scalar():
            raise RuntimeError(
                "Schema reconciliation requires PRAGMA foreign_keys=OFF on a dedicated "
                "SQLite migration connection before its transaction; refusing batch rebuild "
                "with cascading foreign keys enabled."
            )
        # Python sqlite3 legacy transaction control otherwise autocommits DDL.
        if not bind.connection.driver_connection.in_transaction:
            bind.exec_driver_sql("BEGIN IMMEDIATE")
        _foreign_key_check(bind)
        # Other tables' triggers/views may reference a parent while batch rebuild
        # briefly removes it. Do not validate/rewrite those references on rename.
        legacy = bind.exec_driver_sql("PRAGMA legacy_alter_table").scalar_one()
        bind.exec_driver_sql("PRAGMA legacy_alter_table = ON")
        try:
            yield bind
            _foreign_key_check(bind)
        finally:
            bind.exec_driver_sql(f"PRAGMA legacy_alter_table = {int(legacy)}")
    elif bind.dialect.name == "postgresql":
        if getattr(bind.connection.driver_connection, "autocommit", False) or not bind.in_transaction():
            raise RuntimeError("Schema reconciliation requires transactional PostgreSQL DDL.")
        locked = sorted(set(TABLES) | {table for table, _ in ADDED})
        bind.exec_driver_sql(
            "LOCK TABLE " + ", ".join(f'"{table}"' for table in locked)
            + " IN ACCESS EXCLUSIVE MODE"
        )
        forced = [table for table in TABLES if bind.execute(sa.text(
            "SELECT relforcerowsecurity FROM pg_class WHERE oid = to_regclass(:table)"
        ), {"table": table}).scalar_one()]
        previous = bind.exec_driver_sql("SHOW row_security").scalar_one()
        for table in forced:
            bind.exec_driver_sql(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        # Fail closed if this role cannot bypass RLS, rather than counting a subset.
        bind.exec_driver_sql("SET LOCAL row_security = off")
        yield bind
        for table in forced:
            bind.exec_driver_sql(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        bind.execute(sa.text("SELECT set_config('row_security', :value, true)"), {"value": previous})
        # On error Alembic rolls back ALL DDL, including the temporary FORCE change.
    else:
        raise RuntimeError("Schema reconciliation supports only SQLite and PostgreSQL.")


def _preflight(bind):
    problems = []
    for table, columns in REQUIRED.items():
        for column in columns:
            count = bind.exec_driver_sql(
                f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NULL'
            ).scalar_one()
            if count:
                problems.append(f"{table}.{column}: {count} NULL row(s)")
    for table, column, _ in UNIQUE:
        count = bind.exec_driver_sql(
            f'SELECT count(*) FROM (SELECT "{column}" FROM "{table}" '
            f'GROUP BY "{column}" HAVING count(*) > 1) AS duplicates'
        ).scalar_one()
        if count:
            problems.append(f"{table}.{column}: {count} duplicate group(s)")
    if problems:
        raise RuntimeError(
            "Schema reconciliation preflight failed; no rows were changed. "
            "Repair these values from authoritative records before retrying: "
            + "; ".join(problems)
        )


def _alter(bind, *, upgrading):
    sqlite = bind.dialect.name == "sqlite"
    for table in TABLES:
        unique = next((item for item in UNIQUE if item[0] == table), None)
        triggers = []
        copy_from = None
        if sqlite:
            triggers = bind.execute(sa.text(
                "SELECT sql FROM sqlite_master WHERE type = 'trigger' "
                "AND tbl_name = :table AND sql IS NOT NULL"
            ), {"table": table}).scalars().all()
            copy_from = sa.Table(table, sa.MetaData(), autoload_with=bind)
            # Preserve originally unnamed SQLite constraints on downgrade.
            if unique:
                _, column, name = unique
                for constraint in list(copy_from.constraints):
                    if isinstance(constraint, sa.UniqueConstraint) and list(constraint.columns.keys()) == [column]:
                        copy_from.constraints.remove(constraint)
                if not upgrading:
                    copy_from.append_constraint(sa.UniqueConstraint(
                        column, name=name if table == "password_reset_tokens" else None,
                    ))
        with op.batch_alter_table(
            table, copy_from=copy_from, recreate="always" if sqlite else "auto",
        ) as batch:
            for column in REQUIRED.get(table, ()):
                batch.alter_column(column, nullable=not upgrading)
            if unique:
                _, column, name = unique
                index = f"ix_{table}_{column}"
                if not sqlite:
                    if upgrading:
                        # Build replacement enforcement before removing the constraint.
                        batch.drop_index(index)
                        batch.create_index(index, [column], unique=True)
                        batch.drop_constraint(name, type_="unique")
                    else:
                        batch.create_unique_constraint(name, [column])
                        batch.drop_index(index)
                        batch.create_index(index, [column], unique=False)
                else:
                    batch.drop_index(index)
                    batch.create_index(index, [column], unique=upgrading)
        for trigger in triggers:
            bind.exec_driver_sql(trigger)
    for table, column, old in RENAMED:
        new = f"ix_{table}_{column}"
        source, target = (old, new) if upgrading else (new, old)
        if sqlite:
            op.create_index(target, table, [column])
            op.drop_index(source, table_name=table)
        else:
            bind.exec_driver_sql(f'ALTER INDEX "{source}" RENAME TO "{target}"')
    for table, column in ADDED:
        index = f"ix_{table}_{column}"
        if upgrading:
            op.create_index(index, table, [column])
        else:
            op.drop_index(index, table_name=table)


def upgrade():
    with _maintenance() as bind:
        _preflight(bind)
        _alter(bind, upgrading=True)


def downgrade():
    with _maintenance() as bind:
        _alter(bind, upgrading=False)
