"""Execute cohort ranking and bounds on migrated PostgreSQL, not only SQLite."""
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import app.services.activity_baseline as baseline
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.test_activity_baseline import AS_OF, _cohort_factory, counts, request_for

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not set")


def test_postgres_baseline_corrections_and_history_bounds(monkeypatch):
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    org_id = f"baseline-{uuid4().hex[:8]}"
    token = set_current_context(RequestContext(org_id, "test"))
    try:
        with Session(engine) as db:
            role = db.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
            assert not role.rolsuper and not role.rolbypassrls
            db.execute(text("SELECT set_config('app.current_org', :org, true)"), {"org": org_id})
            source, add = _cohort_factory(db, monkeypatch)()
            add("corrected", recorded=AS_OF - timedelta(hours=2))
            add("corrected", effective=None)
            add("remaining")
            report = baseline.activity_baseline(db, request_for(source))
            assert counts(report) == [0, 0, 0, 1]
            assert report["sources"][0]["diagnostics"]["missing_or_cleared_date"] == 1
            monkeypatch.setattr(baseline, "MAX_HISTORY_ROWS", 2)
            bounded = baseline.activity_baseline(db, request_for(source))
            assert bounded["status"] == "bounded_query_exceeded" and bounded["sources"] == []
            db.rollback()
    finally:
        reset_current_context(token)
        engine.dispose()
