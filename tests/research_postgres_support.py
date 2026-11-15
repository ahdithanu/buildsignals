"""Opt-in research test sessions and read-only PostgreSQL lock monitoring.

Only SNAPSHOT_TEST_POSTGRES_URL / SNAPSHOT_TEST_RUN_ID select the target; there
is no fallback to application or generic test database URLs. Independently
provision a fresh disposable database first. Every physical connection must
pass the shared loopback/ambient-env guard and read-only database-name, nonce
and restricted current/session-role proof before a tenant session is yielded.
These helpers neither provision a database nor constitute PG acceptance by
themselves; unset dedicated configuration leaves the research PG tests skipped.
"""
import os
import time
from contextlib import contextmanager

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.db import _set_rls_org
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.snapshot_postgres_support import verified_snapshot_connection

URL = os.environ.get("SNAPSHOT_TEST_POSTGRES_URL")
RUN_ID = os.environ.get("SNAPSHOT_TEST_RUN_ID", "")


@contextmanager
def tenant_session(org):
    token = set_current_context(RequestContext(org, "synthetic-research-test"))
    try:
        with verified_snapshot_connection(URL, RUN_ID) as connection:
            with Session(bind=connection, autoflush=False, expire_on_commit=False) as db:
                event.listen(db, "after_begin", _set_rls_org)
                yield db
    finally:
        reset_current_context(token)


def assert_blocked_by(db, state, relation):
    """Poll for the owned blocker PID and complete lock SQL on a 3s deadline."""
    blocker = db.scalar(text("SELECT pg_catalog.pg_backend_pid()"))
    assert state["pid"] != blocker
    activity_limit = db.scalar(text(
        "SELECT pg_catalog.pg_size_bytes(current_setting('track_activity_query_size'))"
    ))
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        # Refresh activity statistics inside the lock-holder's transaction.
        db.execute(text("SELECT pg_catalog.pg_stat_clear_snapshot()"))
        activity = db.execute(text(
            "SELECT pg_catalog.pg_blocking_pids(pid), query FROM pg_catalog.pg_stat_activity "
            "WHERE pid=:pid"
        ), {"pid": state["pid"]}).one()
        if blocker in activity[0] and f"FROM {relation}" in activity[1]:
            # PostgreSQL reserves one byte for the activity text's terminator.
            assert len(activity[1].encode('utf-8')) < activity_limit - 1, "Captured lock SQL may be truncated"
            assert activity[1].rstrip().endswith("FOR UPDATE"), "Complete SELECT FOR UPDATE not observed"
            return
        time.sleep(0.01)
    pytest.fail("No actual PostgreSQL blocker relationship observed")
