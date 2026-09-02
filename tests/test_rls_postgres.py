"""Proves Postgres row-level security actually blocks cross-org reads.

Skips unless `TEST_POSTGRES_URL` is set. CI sets it (a Postgres service +
non-superuser `appuser`); a developer can too against a local Postgres. The
rest of the suite runs on SQLite where RLS is a no-op.

⚠ `TEST_POSTGRES_URL` MUST connect as a NON-superuser role. Postgres
superusers (and BYPASSRLS roles) ignore row-level security entirely — even
under FORCE ROW LEVEL SECURITY — so these assertions silently pass-through
and validate nothing if you point them at a superuser connection. Migration
003 uses FORCE RLS specifically so the policy applies to the table owner;
production on Render connects as a non-superuser owner, which is exactly the
condition under which RLS protects tenant data. Test as that role or you're
testing a lie.

What this test guards against: a future refactor that drops the
`after_begin` hook in app/db.py or reverts migration 003 would make all
tenant data readable across orgs on Postgres. Without this test, that
regression is invisible until prod.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TEST_POSTGRES_URL not set; skipping Postgres RLS tests",
)


@pytest.fixture(scope="module")
def pg_engine():
    """Engine pointed at a Postgres instance with migration 003 applied.

    The fixture assumes `alembic upgrade head` has already run against
    TEST_POSTGRES_URL (CI does this in a setup step). If the policy is
    missing, the first assertion will fail loud.
    """
    engine = create_engine(POSTGRES_URL, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def pg_session(pg_engine):
    Session = sessionmaker(bind=pg_engine)
    s = Session()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _seed_deals(session, org_a: str, org_b: str) -> tuple[str, str]:
    """Insert one deal per org. `deals.organization_id` FKs to `organizations`,
    so the org rows must exist first. `organizations` is NOT in TENANT_TABLES
    (migration 003), so those inserts aren't RLS-governed. Deals ARE, so each
    deal insert runs with app.current_org set to satisfy the WITH CHECK policy."""
    deal_a = str(uuid.uuid4())
    deal_b = str(uuid.uuid4())

    # Orgs first (no RLS on organizations) — satisfies the deals FK.
    for oid in (org_a, org_b):
        session.execute(
            text("INSERT INTO organizations (id, name, slug) VALUES (:id, :n, :s)"),
            {"id": oid, "n": f"Org {oid}", "s": oid},
        )
    session.commit()

    # Insert A
    session.execute(
        text("SELECT set_config('app.current_org', :o, true)"), {"o": org_a}
    )
    session.execute(
        text(
            "INSERT INTO deals (id, name, organization_id, status) "
            "VALUES (:id, :n, :o, 'new')"
        ),
        {"id": deal_a, "n": "A-deal", "o": org_a},
    )

    # Insert B (new transaction so SET LOCAL is fresh)
    session.commit()
    session.execute(
        text("SELECT set_config('app.current_org', :o, true)"), {"o": org_b}
    )
    session.execute(
        text(
            "INSERT INTO deals (id, name, organization_id, status) "
            "VALUES (:id, :n, :o, 'new')"
        ),
        {"id": deal_b, "n": "B-deal", "o": org_b},
    )
    session.commit()
    return deal_a, deal_b


def test_rls_isolates_reads_by_org(pg_session):
    org_a = f"rls-a-{uuid.uuid4().hex[:6]}"
    org_b = f"rls-b-{uuid.uuid4().hex[:6]}"
    deal_a, deal_b = _seed_deals(pg_session, org_a, org_b)

    # Acting as org_a — only A-deal should be visible.
    pg_session.execute(
        text("SELECT set_config('app.current_org', :o, true)"), {"o": org_a}
    )
    visible = pg_session.execute(
        text("SELECT id FROM deals WHERE id IN (:a, :b)"),
        {"a": deal_a, "b": deal_b},
    ).scalars().all()
    assert visible == [deal_a], (
        f"RLS leak: org_a saw {visible}, expected only {deal_a}"
    )

    # Acting as org_b — only B-deal should be visible.
    pg_session.commit()
    pg_session.execute(
        text("SELECT set_config('app.current_org', :o, true)"), {"o": org_b}
    )
    visible = pg_session.execute(
        text("SELECT id FROM deals WHERE id IN (:a, :b)"),
        {"a": deal_a, "b": deal_b},
    ).scalars().all()
    assert visible == [deal_b]


def test_rls_blocks_writes_with_wrong_org(pg_session):
    org_a = f"rls-wa-{uuid.uuid4().hex[:6]}"
    org_b = f"rls-wb-{uuid.uuid4().hex[:6]}"

    pg_session.execute(
        text("SELECT set_config('app.current_org', :o, true)"), {"o": org_a}
    )
    # Attempt to insert a row claiming to belong to org_b while acting as
    # org_a — WITH CHECK must reject it.
    with pytest.raises(Exception):  # psycopg raises on RLS violation
        pg_session.execute(
            text(
                "INSERT INTO deals (id, name, organization_id, status) "
                "VALUES (:id, 'evil', :o, 'new')"
            ),
            {"id": str(uuid.uuid4()), "o": org_b},
        )
    pg_session.rollback()


def test_rls_blocks_when_app_current_org_unset(pg_engine):
    """Without `app.current_org` set, current_setting(..., true) returns ''
    and no rows should be visible — the policy must not accidentally
    permit the empty case."""
    Session = sessionmaker(bind=pg_engine)
    s = Session()
    try:
        # Do NOT set app.current_org. Any SELECT must return zero rows.
        rows = s.execute(text("SELECT count(*) FROM deals")).scalar_one()
        assert rows == 0, (
            "RLS default-deny failed: unset app.current_org leaked "
            f"{rows} rows. Check migration 003's policy."
        )
    finally:
        s.rollback()
        s.close()


def test_ingestion_onboarding_tables_force_tenant_rls(pg_session):
    tables = {
        "organization_ingestion_enrollments",
        "organization_ingestion_enrollment_sources",
    }
    rows = pg_session.execute(
        text(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, p.polname "
            "FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_policy p ON p.polrelid = c.oid "
            "WHERE n.nspname = current_schema() AND c.relname = ANY(:tables)"
        ),
        {"tables": sorted(tables)},
    ).all()

    assert {row.relname for row in rows} == tables
    assert all(row.relrowsecurity for row in rows)
    assert all(row.relforcerowsecurity for row in rows)
    assert all(row.polname == "tenant_isolation" for row in rows)


def test_raw_record_trigger_blocks_direct_mutation_but_allows_org_erasure(
    pg_session,
):
    org_id = f"raw-guard-{uuid.uuid4().hex[:8]}"
    source_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    raw_id = str(uuid.uuid4())

    pg_session.execute(
        text("INSERT INTO organizations (id, name, slug) VALUES (:id, :n, :s)"),
        {"id": org_id, "n": "Raw Guard", "s": org_id},
    )
    pg_session.commit()
    pg_session.execute(
        text("SELECT set_config('app.current_org', :o, true)"), {"o": org_id}
    )
    pg_session.execute(text(
        "INSERT INTO ingestion_sources "
        "(id, key, name, adapter, record_type, organization_id) "
        "VALUES (:id, :key, 'Raw Guard', 'csv', 'permit', :org)"
    ), {"id": source_id, "key": org_id, "org": org_id})
    pg_session.execute(text(
        "INSERT INTO ingestion_runs "
        "(id, source_id, status, trigger, organization_id) "
        "VALUES (:id, :source, 'completed', 'manual', :org)"
    ), {"id": run_id, "source": source_id, "org": org_id})
    pg_session.execute(text(
        "INSERT INTO raw_source_records "
        "(id, source_id, run_id, external_record_id, record_type, content_hash, "
        "payload, received_at, organization_id) VALUES "
        "(:id, :source, :run, 'record-1', 'permit', 'hash-1', "
        "'{}', CURRENT_TIMESTAMP, :org)"
    ), {"id": raw_id, "source": source_id, "run": run_id, "org": org_id})
    pg_session.execute(text(
        "INSERT INTO raw_source_record_observations "
        "(raw_source_record_id, last_observed_at, organization_id) "
        "VALUES (:id, CURRENT_TIMESTAMP, :org)"
    ), {"id": raw_id, "org": org_id})
    pg_session.commit()

    pg_session.execute(
        text("SELECT set_config('app.current_org', :o, true)"), {"o": org_id}
    )
    pg_session.execute(text(
        "UPDATE raw_source_record_observations "
        "SET last_observed_at = CURRENT_TIMESTAMP "
        "WHERE raw_source_record_id = :id"
    ), {"id": raw_id})
    pg_session.commit()

    pg_session.execute(text("CREATE TEMP TABLE organizations (id text)"))
    pg_session.commit()

    for statement, parameters in (
        (
            "UPDATE raw_source_records "
            "SET payload = '{\"tampered\": true}' WHERE id = :id",
            {"id": raw_id},
        ),
        ("DELETE FROM raw_source_records WHERE id = :id", {"id": raw_id}),
        ("TRUNCATE raw_source_records CASCADE", {}),
    ):
        pg_session.execute(
            text("SELECT set_config('app.current_org', :o, true)"), {"o": org_id}
        )
        with pytest.raises(DBAPIError, match="raw_source_records are immutable"):
            pg_session.execute(text(statement), parameters)
        pg_session.rollback()

    pg_session.execute(
        text("DELETE FROM public.organizations WHERE id = :id"), {"id": org_id}
    )
    pg_session.commit()
    pg_session.execute(
        text("SELECT set_config('app.current_org', :o, true)"), {"o": org_id}
    )
    assert pg_session.execute(
        text("SELECT count(*) FROM raw_source_records WHERE id = :id"),
        {"id": raw_id},
    ).scalar_one() == 0
