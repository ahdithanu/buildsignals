from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.demo_access import DEMO_ORG_ID
from app.services.ingestion.catalog import load_catalog
from scripts import recurring_regions as worker


def test_sf_refresh_uses_changed_rows_and_preserves_identity_freshness_and_privacy():
    key = "san_francisco_ca_building_permits_primary_address"
    original = next(e for e in load_catalog() if e.key == key).model_dump()
    entry = worker.regional_entry(key, now=datetime(2026, 11, 11, tzinfo=timezone.utc))
    config = entry.settings["connector"]
    query = config["query"]
    assert query["$where"] == (
        "(primary_address_flag = 'Y') AND data_loaded_at >= '2026-10-12T00:00:00' "
        "AND data_loaded_at < '2026-11-12T00:00:00'"
    )
    assert config["keyset_fields"] == ["data_loaded_at", "record_id"]
    fields = set(query["$select"].split(","))
    assert {"permit_number", "record_id", "data_loaded_at", "status_date", "block", "lot"} <= fields
    assert fields == set(entry.settings["field_allowlist"])
    for mapping in entry.field_mappings:
        if not mapping.source_field.startswith("__"):
            assert mapping.source_field in fields
        assert set((mapping.transform_options or {}).get("fields", [])) <= fields
    assert not fields & {"applicant", "owner", "contact", "phone", "email"}
    assert entry.settings["freshness_field"] == "data_loaded_at"
    assert entry.settings["freshness_semantics"] == "record_updated_at"
    assert entry.settings["freshness_sla_hours"] == 36
    assert entry.settings["attribution_required"] is True
    assert entry.settings["regional_event_kind"] == "publisher_row_update_not_new_filing"
    assert entry.settings["rights_basis"]
    assert next(e for e in load_catalog() if e.key == key).model_dump() == original


@pytest.mark.parametrize("change", ["license", "host"])
def test_sf_profile_fails_closed_if_reviewed_source_contract_changes(monkeypatch, change):
    entries = load_catalog()
    entry = next(e for e in entries if e.key == worker.SF_BUILDING_KEY)
    if change == "license":
        entry.settings["license"] = "Unreviewed terms"
    else:
        entry.base_url = "https://other.example/resource/i98e-djp9.json"
    monkeypatch.setattr(worker, "load_catalog", lambda: entries)
    with pytest.raises(ValueError, match="reviewed canonical PDDL"):
        worker.regional_entry(worker.SF_BUILDING_KEY)


def test_sf_legacy_host_source_requires_explicit_migration_not_silent_rebinding():
    entry = worker.regional_entry("san_francisco_ca_building_permits_primary_address")
    legacy = SimpleNamespace(base_url="https://data.sfgov.org/resource/i98e-djp9.json",
                             record_type="permit", is_active=True)
    with pytest.raises(ValueError, match="identity differs"):
        worker.ensure_reactivatable(legacy, entry)


def test_california_held_profiles_are_not_silently_scheduled():
    for key in ("los_angeles_ca_building_permits_submitted",
                "san_francisco_ca_planning_department_non_project_records"):
        with pytest.raises(KeyError):
            worker.regional_entry(key)


@pytest.mark.parametrize("key,update_field", sorted(worker.UPDATE_WINDOW_FIELDS.items()))
def test_expansion_windows_preserve_scope_and_include_recent_lifecycle_updates(key, update_field):
    original = next(e for e in load_catalog() if e.key == key)
    entry = worker.regional_entry(key, now=datetime(2026, 11, 9, tzinfo=timezone.utc))
    config = entry.settings["connector"]
    assert config["where"].startswith("(" + original.settings["connector"]["where"] + ") AND ")
    assert " OR " in config["where"] and update_field in config["where"]
    assert "2026-10-10" in config["where"] and "2026-11-10" in config["where"]
    assert config["out_fields"] == original.settings["connector"]["out_fields"]
    assert config["keyset_field"]
    if key.startswith("detroit"):
        assert "TIMESTAMP" not in config["where"]
        assert "DATE '2026-10-10'" in config["where"]


def test_arcgis_count_uses_query_endpoint_for_bend_layer_url(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "RetryingHttpClient", lambda **kw:
        SimpleNamespace(get_json=lambda url, **kwargs: calls.append(url) or {"count": 5}))
    assert worker.count_source(worker.regional_entry("bend_or_permit_applications_point")) == 5
    assert calls[0].endswith("/FeatureServer/0/query")


def test_arcgis_auth_error_is_an_explicit_gate_without_echoing_provider_text(monkeypatch):
    monkeypatch.setattr(worker, "RetryingHttpClient", lambda **kw:
        SimpleNamespace(get_json=lambda *a, **kwargs: {"error": {"code": 499, "message": "untrusted"}}))
    with pytest.raises(ValueError, match="requires authorized credentials") as exc:
        worker.count_source(worker.regional_entry("tacoma_wa_commercial_permit_lifecycle"))
    assert "untrusted" not in str(exc.value)


def test_expansion_windows_use_utc_day_across_local_midnight():
    local = datetime(2026, 11, 10, 0, 30, tzinfo=timezone(timedelta(hours=9)))
    key = "detroit_mi_bseed_building_plan_reviews"
    local_scope = worker.regional_entry(key, now=local)
    utc_scope = worker.regional_entry(key, now=local.astimezone(timezone.utc))
    assert local_scope.model_dump() == utc_scope.model_dump()
    assert "DATE '2026-10-10'" in local_scope.settings["connector"]["where"]


def test_bend_keyset_cursor_keeps_order_and_progresses():
    from app.services.ingestion.connectors.arcgis import ArcGISFeatureServerConnector

    calls = []

    def get_json(url, *, params, **kwargs):
        calls.append(params)
        ids = range(1, 251) if len(calls) == 1 else [251]
        return {"features": [{"attributes": {"OBJECTID": i}} for i in ids],
                "exceededTransferLimit": len(calls) == 1}

    entry = worker.regional_entry("bend_or_permit_applications_point")
    config = entry.settings["connector"]
    connector = ArcGISFeatureServerConnector(entry.base_url, page_size=250,
        where=config["where"], keyset_field=config["keyset_field"],
        order_by_fields=config["order_by_fields"], http_client=SimpleNamespace(get_json=get_json))
    first = connector.fetch()
    second = connector.fetch(first.checkpoint)
    assert first.checkpoint == {"keyset": {"OBJECTID": 250}}
    assert "OBJECTID > 250" in calls[1]["where"]
    assert all(p["orderByFields"] == "OBJECTID ASC" for p in calls)
    assert not second.has_more
    assert len({r["OBJECTID"] for r in (*first.records, *second.records)}) == 251


@pytest.mark.parametrize("key", [
    "seattle_wa_land_use_permits", "cincinnati_oh_building_permits",
])
def test_new_city_scopes_preserve_commercial_filters_and_coordinates(key):
    entry = worker.regional_entry(key, now=datetime(2026, 11, 9, tzinfo=timezone.utc))
    query = entry.settings["connector"]["query"]
    assert "applieddate >= '2026-10-10T00:00:00'" in query["$where"]
    assert "applieddate < '2026-11-10T00:00:00'" in query["$where"]
    assert "permitclass" in query["$where"]
    original = next(e for e in load_catalog() if e.key == key)
    assert query["$where"].startswith("(" + original.settings["connector"]["query"]["$where"] + ") AND ")
    assert entry.settings["connector"]["order_by"] == "applieddate DESC, :id ASC"
    assert "latitude" in query["$select"] and "longitude" in query["$select"]
    assert entry.settings["reconciliation_mode"] == "incremental"
    assert worker.SOURCES[key] == ("applieddate", "application")


def test_quarantined_source_is_not_silently_reactivated():
    entry = worker.regional_entry(
        "orlando_fl_permit_applications", now=datetime(2026, 10, 16, tzinfo=timezone.utc)
    )
    active = SimpleNamespace(base_url=entry.base_url, record_type=entry.record_type, is_active=True)
    quarantined = SimpleNamespace(base_url=entry.base_url, record_type=entry.record_type, is_active=False)
    mismatched = SimpleNamespace(base_url="https://other.example/x", record_type=entry.record_type, is_active=True)

    worker.ensure_reactivatable(active, entry)  # active source: no error
    with pytest.raises(RuntimeError, match="quarantined"):
        worker.ensure_reactivatable(quarantined, entry)
    with pytest.raises(ValueError, match="identity differs"):
        worker.ensure_reactivatable(mismatched, entry)


@pytest.mark.parametrize("key", sorted(worker.SOURCES))
def test_regional_scope_keeps_reviewed_bounds_and_rights(key):
    entry = worker.regional_entry(key, now=datetime(2026, 10, 16, tzinfo=timezone.utc))
    config = entry.settings["connector"]
    if entry.adapter not in {"arcgis", "socrata"}:
        assert config["max_records"] <= (250 if entry.adapter == "legistar" else 100)
        return
    predicate = config.get("where") if entry.adapter == "arcgis" else config["query"]["$where"]
    if key == worker.OCALA_CONTEXT_KEY:
        assert predicate == "1=1"
        assert entry.settings["context_only"] is True
        assert entry.settings["rolling_window_days"] is None
    elif key == "savannah_ga_commercial_building_permits":
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
    if worker.SOURCES[key][0] is not None:
        assert worker.SOURCES[key][0] in predicate


def test_unreviewed_sources_and_demo_tenant_are_not_accepted():
    with pytest.raises(KeyError):
        worker.regional_entry("diberville_ms_council_planning_agendas")
    with pytest.raises(ValueError, match="non-demo"):
        worker.refresh(next(iter(worker.SOURCES)), DEMO_ORG_ID)


def test_cincinnati_sort_is_sent_on_every_page():
    from app.services.ingestion.connectors.socrata import SocrataConnector

    calls = []

    def get_json(url, *, params, headers=None):
        calls.append(params)
        offset = params["$offset"]
        return [{":id": str(i)} for i in range(offset, min(offset + 250, 316))]

    entry = worker.regional_entry("cincinnati_oh_building_permits")
    config = entry.settings["connector"]
    connector = SocrataConnector(entry.base_url, page_size=250,
        order_by=config["order_by"], query=config["query"],
        http_client=SimpleNamespace(get_json=get_json))
    first = connector.fetch()
    second = connector.fetch(first.checkpoint)
    assert len(first.records) + len(second.records) == 316
    assert len({r[":id"] for r in (*first.records, *second.records)}) == 316
    assert not second.has_more
    assert [p["$offset"] for p in calls] == [0, 250]
    assert all(p["$order"] == "applieddate DESC, :id ASC" for p in calls)


@pytest.mark.parametrize("count", [0, 100001])
def test_empty_and_oversize_scopes_fail_before_canary(monkeypatch, count):
    monkeypatch.setattr(worker, "count_source", lambda entry: count)
    monkeypatch.setattr(worker, "validate_source_canary", lambda *a, **k: pytest.fail("No fetch expected"))
    with pytest.raises(ValueError, match="budget"):
        worker.verify(worker.regional_entry(next(iter(worker.SOURCES))))


@pytest.mark.parametrize("count", [2264, 100000])
def test_increased_record_budget_accepts_counts_after_canary(monkeypatch, count):
    monkeypatch.setattr(worker, "count_source", lambda entry: count)
    monkeypatch.setattr(worker, "validate_source_canary", lambda *a, **k:
        SimpleNamespace(ok=True, records_valid=10, records_failed=0))
    assert worker.verify(worker.regional_entry("texas_comptroller_sales_tax_locations"))[0] == count
    assert worker.MAX_PAGES_PER_RUN == 401
    assert (worker.MAX_PAGES_PER_RUN - 1) * worker.PAGE_SIZE == worker.MAX_RECORDS_PER_RUN


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


def test_100k_refresh_resumes_four_chunks_and_terminal_probe(monkeypatch):
    calls = []

    def execute(db, source, *, max_pages, checkpoint, trigger):
        index = len(calls)
        calls.append((max_pages, checkpoint))
        return SimpleNamespace(id=str(index), status="completed" if index == 4 else "partial",
            records_seen=0 if index == 4 else 25000, records_inserted=0 if index == 4 else 25000,
            records_updated=0, records_failed=0, error_message=None,
            checkpoint=None if index == 4 else {"offset": (index + 1) * 25000})

    monkeypatch.setattr(worker, "execute_source_run", execute)
    run = worker.execute_regional_refresh(None, SimpleNamespace(key="test"))
    assert [c[0] for c in calls] == [100, 100, 100, 100, 1]
    assert calls[-1][1] == {"offset": 100000}
    assert run.records_seen == run.records_inserted == 100000
    assert worker.run_reconciled(run, 100000, 100000)


def test_count_outage_does_not_mark_refresh_reconciled(monkeypatch):
    def unavailable(entry):
        raise TimeoutError("untrusted provider text")
    monkeypatch.setattr(worker, "count_source", unavailable)
    run = SimpleNamespace(status="completed", records_failed=0, records_seen=10, error_message=None)
    assert worker.reconcile_after_refresh(None, run, 10) == (None, False)
    assert "reconciliation failed" in run.error_message
    assert "untrusted" not in run.error_message


@pytest.mark.parametrize("status,failed,checkpoint", [
    ("partial_with_errors", 1, {"offset": 10}),
    ("partial", 0, None),
    ("failed", 0, None),
])
def test_chunk_failure_does_not_resume(monkeypatch, status, failed, checkpoint):
    calls = []

    def execute(*a, **kw):
        calls.append(kw)
        return SimpleNamespace(id="failed", status=status, records_seen=10,
            records_inserted=9, records_updated=0, records_failed=failed,
            error_message="failure", checkpoint=checkpoint)

    monkeypatch.setattr(worker, "execute_source_run", execute)
    result = worker.execute_regional_refresh(None, SimpleNamespace(key="test"))
    assert len(calls) == 1
    assert not worker.run_reconciled(result, 10, 10)
