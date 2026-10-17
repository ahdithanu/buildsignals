from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.ingestion import IngestionSource
from app.models.organization import Organization
from app.services.demo_access import DEMO_ORG_ID
from scripts.recurring_columbus import refresh, refresh_entry


def test_rolling_window_is_bounded_and_never_retires_aged_records():
    entry = refresh_entry(demo=False, now=datetime(2026, 10, 16, tzinfo=timezone.utc))
    assert "2026-09-16 00:00:00" in entry.settings["connector"]["where"]
    assert "2026-10-17 00:00:00" in entry.settings["connector"]["where"]
    assert entry.settings["connector"]["page_size"] == 250
    assert entry.settings["reconciliation_mode"] == "incremental"
    assert "APPLICANT_FULL_NAME" not in entry.settings["field_allowlist"]
    assert not entry.settings["connector"]["include_geometry"]


@pytest.mark.parametrize("org,demo", [(DEMO_ORG_ID, False), ("customer", True), ("", False)])
def test_destination_mismatch_fails_before_database_access(org, demo):
    def forbidden():
        pytest.fail("Database must not be opened")
    with pytest.raises(ValueError, match="separate"):
        refresh(org, demo=demo, session_factory=forbidden)


def test_modes_have_distinct_keys_and_do_not_mutate_catalog():
    demo = refresh_entry(demo=True)
    production = refresh_entry(demo=False)
    assert demo.key != production.key
    assert demo.settings["demo_snapshot"]
    assert not production.settings["demo_snapshot"]
    demo.settings["connector"]["page_size"] = 1
    assert refresh_entry(demo=True).settings["connector"]["page_size"] == 250


@pytest.mark.parametrize("fail", [False, True])
def test_demo_refresh_always_returns_source_to_inactive(db, monkeypatch, fail):
    from types import SimpleNamespace

    from scripts import recurring_columbus as job

    db.add(Organization(id=DEMO_ORG_ID, slug="buildsignals-demo", name="BuildSignals Demo"))
    db.commit()
    monkeypatch.setattr(job, "provider_count", lambda *args: 0)

    def execute(session, source, **kwargs):
        assert source.organization_id == DEMO_ORG_ID
        assert source.is_active
        assert kwargs == {"max_pages": 4, "trigger": "scheduled"}
        if fail:
            raise RuntimeError("simulated fetch failure")
        return SimpleNamespace(id="test-run", status="completed", records_seen=0,
                               records_inserted=0, records_updated=0, records_failed=0, checkpoint=None)

    monkeypatch.setattr(job, "execute_source_run", execute)
    factory = sessionmaker(bind=db.get_bind())
    if fail:
        with pytest.raises(RuntimeError, match="simulated"):
            refresh(DEMO_ORG_ID, demo=True, session_factory=factory)
    else:
        assert refresh(DEMO_ORG_ID, demo=True, session_factory=factory)["status"] == "completed"
    source = db.query(IngestionSource).filter_by(organization_id=DEMO_ORG_ID).one()
    assert not source.is_active
    assert source.settings["schedule_mode"] == "manual"


def test_oversize_feed_stops_before_source_creation(db, monkeypatch):
    from scripts import recurring_columbus as job

    db.add(Organization(id="customer", slug="customer", name="Customer"))
    db.commit()
    monkeypatch.setattr(job, "provider_count", lambda *args: 1001)
    with pytest.raises(ValueError, match="budget"):
        refresh("customer", demo=False, session_factory=sessionmaker(bind=db.get_bind()))
    assert db.query(IngestionSource).count() == 0
