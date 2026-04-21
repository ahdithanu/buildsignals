"""Proves Postgres row-level security actually blocks cross-org reads.

Skips unless `TEST_POSTGRES_URL` is set — e.g. in CI or when a developer
runs a local Postgres container. The rest of the suite continues to run
on SQLite where RLS is a no-op.

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
    """Insert one deal per org using a bypass role or by SET app.current_org
    per insert. Uses SET LOCAL twice so each insert satisfies WITH CHECK."""
    deal_a = str(uuid.uuid4())
    deal_b = str(uuid.uuid4())

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
