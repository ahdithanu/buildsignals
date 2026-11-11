"""Offline contract tests for the bounded Ocala GIS context worker profile."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.schemas.ingestion import IngestionSourceCreate
from app.services.ingestion.catalog import load_catalog
from app.services.ingestion.health import _freshness_errors
from app.services.ingestion.normalization import normalize_permit, prepare_mapped_record
from scripts import recurring_regions as worker

KEY = "ocala_fl_gis_new_building_projects"
NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)
PUBLIC_FIELDS = {"OBJECTID", "PermitNo", "Applied", "Subtype", "Status", "APN", "Issued", "Expired"}


def test_context_profile_is_explicit_public_scope_with_centroid_only():
    entry = worker.ocala_context_entry()
    assert isinstance(entry, IngestionSourceCreate)
    assert entry.key == KEY and entry.adapter == "arcgis" and entry.is_active
    config = entry.settings["connector"]
    assert set(config["out_fields"].split(",")) == PUBLIC_FIELDS
    assert config["include_geometry"] is False and config["include_centroid"] is True
    assert config["query"] == {"outSR": 4326}
    assert (config["keyset_field"], config["order_by_fields"]) == ("OBJECTID", "OBJECTID ASC")
    assert entry.base_url.endswith("/Public/GrowthManagement/FeatureServer/19")
    assert {m.source_field for m in entry.field_mappings} <= PUBLIC_FIELDS | {"__source_record_id", "__latitude", "__longitude"}
    mappings = {m.canonical_field: m for m in entry.field_mappings}
    assert mappings["source_record_id"].source_field == "__source_record_id"
    assert mappings["source_record_id"].transform_options == {"fields": ["PermitNo"]}
    assert mappings["source_record_id"].is_required
    for canonical, axis in (("longitude", "x"), ("latitude", "y")):
        mapping = mappings[canonical]
        assert mapping.source_field == "__" + canonical and mapping.transform == "object_path"
        assert mapping.transform_options == {"source_field": "centroid", "path": [axis]}
        assert not mapping.is_required  # Raw centroid required; aliases are derived.
    assert entry.settings["canary_required_fields"] == ["PermitNo", "centroid"]
    assert "approval_stage" not in mappings
    assert "approval_stage" not in entry.settings["defaults"]


def test_context_profile_persists_under_mapping_uniqueness_constraint(db):
    from app.services.ingestion.service import create_source

    source = create_source(db, worker.ocala_context_entry())
    db.commit()
    assert len(source.field_mappings) == 10
    assert len({row.source_field for row in source.field_mappings}) == 10


def test_required_fields_use_raw_inputs_not_synthetic_aliases():
    from app.services.ingestion.normalization import missing_required_source_fields

    entry = worker.ocala_context_entry()
    record = {"PermitNo": "SYNTHETIC", "centroid": {"x": -82, "y": 29}}
    assert missing_required_source_fields(record, entry.field_mappings,
        extra_required_fields=entry.settings["canary_required_fields"]) == []


@pytest.mark.parametrize("status", ["HOLD", "IN REVIEW", "EXPIRED", "ISSUED"])
def test_context_mapping_preserves_native_status_without_stage_inference(status):
    entry = worker.ocala_context_entry()
    record = {"OBJECTID": 1, "PermitNo": "SYNTHETIC-1", "Status": status,
              "Subtype": "Commercial", "APN": "synthetic-parcel",
              "centroid": {"x": -82.14, "y": 29.18}}
    prepared, fields = prepare_mapped_record(record, entry.field_mappings)
    normalized = normalize_permit(prepared, fields, defaults=entry.settings["defaults"])
    assert normalized.values["status"] == status
    assert normalized.values["longitude"] == Decimal("-82.14")
    assert normalized.values["latitude"] == Decimal("29.18")
    assert normalized.values.get("approval_stage") is None


def test_context_inventory_has_no_rolling_date_filter_or_publisher_freshness_claim():
    entry = worker.regional_entry(KEY, now=NOW)
    later = worker.regional_entry(KEY, now=datetime(2027, 1, 1, tzinfo=timezone.utc))
    assert worker.SOURCES[KEY] == (None, "curated_project_context")
    assert entry.settings["connector"]["where"] == "1=1"
    assert entry.settings["connector"] == later.settings["connector"]
    assert entry.settings["rolling_window_days"] is None
    assert entry.settings["reconciliation_mode"] == "incremental"
    assert entry.settings["context_only"] is True
    assert entry.settings["publisher_currentness"] == "unknown"
    assert entry.settings["freshness_semantics"] == "ingestion_observed_at"
    assert not entry.settings.get("freshness_field")
    basis = entry.settings["rights_basis"].lower()
    assert "2026-11-09" in basis and "authorized" in basis
    assert "publisher" in basis and "not independently verified" in basis
    assert "unverified" in entry.settings["license"].lower()


@pytest.mark.parametrize("count", [0, 1001, 100000])
def test_context_count_ceiling_rejects_before_canary(monkeypatch, count):
    monkeypatch.setattr(worker, "count_source", lambda entry: count)
    monkeypatch.setattr(worker, "validate_source_canary",
                        lambda *a, **kw: pytest.fail("Rejected count must not fetch canary"))
    with pytest.raises(ValueError, match="budget"):
        worker.verify(worker.regional_entry(KEY, now=NOW))


@pytest.mark.parametrize("ok,valid", [(False, 1), (True, 0)])
def test_context_canary_failure_is_not_bypassed(monkeypatch, ok, valid):
    monkeypatch.setattr(worker, "count_source", lambda entry: 61)
    monkeypatch.setattr(worker, "validate_source_canary", lambda *a, **kw:
                        SimpleNamespace(ok=ok, records_valid=valid, errors=["synthetic rejection"]))
    with pytest.raises(ValueError, match="Canary failed"):
        worker.verify(worker.regional_entry(KEY, now=NOW))


@pytest.mark.parametrize("key,count", [(KEY, 61), (KEY, 1000),
                                      ("bend_or_permit_applications_point", 1001)])
def test_qualified_context_and_existing_feed_budgets_pass(monkeypatch, key, count):
    monkeypatch.setattr(worker, "count_source", lambda entry: count)
    monkeypatch.setattr(worker, "validate_source_canary", lambda *a, **kw:
                        SimpleNamespace(ok=True, records_valid=10, records_failed=0))
    observed, receipt = worker.verify(worker.regional_entry(key, now=NOW))
    assert observed == receipt["provider_count"] == count


@pytest.mark.parametrize("key", ["bend_or_permit_applications_point",
                                 "detroit_mi_bseed_building_plan_reviews",
                                 "tacoma_wa_commercial_permit_lifecycle"])
def test_existing_feed_windows_and_publisher_freshness_contracts_are_unchanged(key):
    original = next(row for row in load_catalog() if row.key == key)
    entry = worker.regional_entry(key, now=NOW)
    predicate = entry.settings["connector"]["where"]
    assert predicate.startswith("(" + original.settings["connector"]["where"] + ") AND ")
    assert "2026-10-10" in predicate and "2026-11-10" in predicate
    assert entry.settings["rolling_window_days"] == 31
    for setting in ("freshness_field", "freshness_semantics", "freshness_sla_hours",
                    "canary_freshness_probe", "canary_stage_probes"):
        assert entry.settings.get(setting) == original.settings.get(setting)
    if entry.settings.get("freshness_field") and entry.settings.get("freshness_semantics") != "filing_event_at":
        assert _freshness_errors(
            [{entry.settings["freshness_field"]: "2020-01-01T00:00:00Z"}], entry.settings, now=NOW,
        )


def test_context_refresh_page_budget_cannot_expand_to_shared_100k(monkeypatch):
    calls = []

    def execute(*args, **kwargs):
        calls.append(kwargs["max_pages"])
        return SimpleNamespace(id="bounded", status="partial", error_message=None,
            checkpoint={"offset": 1000}, records_seen=1000, records_inserted=1000,
            records_updated=0, records_failed=0)

    monkeypatch.setattr(worker, "execute_source_run", execute)
    result = worker.execute_regional_refresh(None, SimpleNamespace(key=worker.OCALA_CONTEXT_KEY))
    assert calls == [5]
    assert result.status == "partial"


def test_factory_guard_is_source_specific_and_restored_on_error(monkeypatch):
    from app.services.ingestion import service

    sentinel = object()
    original = lambda *args: sentinel
    monkeypatch.setattr(service, "build_connector", original)
    entry = worker.ocala_context_entry()
    with pytest.raises(RuntimeError):
        with worker.context_connector_guard(entry):
            wrapped = service.build_connector("arcgis", {"endpoint": entry.base_url})
            assert isinstance(wrapped, worker.ContextConnectorGuard)
            with pytest.raises(ValueError, match="identity"):
                service.build_connector("csv", {"endpoint": entry.base_url})
            raise RuntimeError("synthetic failure")
    assert service.build_connector is original
    with worker.context_connector_guard(SimpleNamespace(key="other")):
        assert service.build_connector is original
