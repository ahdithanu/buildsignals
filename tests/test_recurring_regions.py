from datetime import datetime, timezone

import pytest

from app.services.demo_access import DEMO_ORG_ID
from scripts import recurring_regions as worker


@pytest.mark.parametrize("key", sorted(worker.SOURCES))
def test_regional_scope_keeps_reviewed_bounds_and_rights(key):
    entry = worker.regional_entry(key, now=datetime(2026, 10, 16, tzinfo=timezone.utc))
    config = entry.settings["connector"]
    if entry.adapter not in {"arcgis", "socrata"}:
        assert config["max_records"] <= (250 if entry.adapter == "legistar" else 100)
        return
    predicate = config.get("where") if entry.adapter == "arcgis" else config["query"]["$where"]
    if key == "savannah_ga_commercial_building_permits":
        assert "09/16/2026" in predicate and "10/16/2026" in predicate
        assert "TIMESTAMP" not in predicate
    elif key == "texas_comptroller_sales_tax_locations":
        assert "2026-10-10" in predicate and "2026-10-17" in predicate
    else:
        assert "2026-09-16" in predicate and "2026-10-17" in predicate
    assert entry.settings["rights_basis"]
    assert entry.settings["reconciliation_mode"] == "incremental"
    assert config["page_size"] == 250
    assert config["max_retries"] == 1
    assert worker.SOURCES[key][0] in predicate


def test_unreviewed_sources_and_demo_tenant_are_not_accepted():
    with pytest.raises(KeyError):
        worker.regional_entry("diberville_ms_council_planning_agendas")
    with pytest.raises(ValueError, match="non-demo"):
        worker.refresh(next(iter(worker.SOURCES)), DEMO_ORG_ID)


@pytest.mark.parametrize("count", [0, 1001])
def test_empty_and_oversize_scopes_fail_before_canary(monkeypatch, count):
    monkeypatch.setattr(worker, "count_source", lambda entry: count)
    monkeypatch.setattr(worker, "validate_source_canary", lambda *a, **k: pytest.fail("No fetch expected"))
    with pytest.raises(ValueError, match="budget"):
        worker.verify(worker.regional_entry(next(iter(worker.SOURCES))))


def test_completed_keyset_cursor_is_not_mistaken_for_partial_ingestion():
    from types import SimpleNamespace

    run = SimpleNamespace(status="completed", records_failed=0, records_seen=43,
                          checkpoint={"keyset": {"folderrsn": "123"}})
    assert worker.run_reconciled(run, 43, 43)
    assert not worker.run_reconciled(run, 43, 44)
    run.status = "partial"
    assert not worker.run_reconciled(run, 43, 43)
    run.status, run.records_failed = "completed", 1
    assert not worker.run_reconciled(run, 43, 43)
