from types import SimpleNamespace

from app.services.ingestion.parcel_readiness import build_parcel_readiness


def test_report_does_not_equate_admission_or_configuration_with_live_coverage():
    source = SimpleNamespace(key="county_parcels", record_type="parcel", jurisdiction="Florida",
                             settings={}, is_active=True, adapter="arcgis", field_mappings=[])
    ledger = "## County A\n\n**Decision: admitted.**\nSource: `county_parcels`.\n\n## County B\n\n**Decision: admitted for bulk files.**\n"
    report = build_parcel_readiness([source], [], ledger)
    assert report["configured_source_count"] == 1
    assert report["measured_imported_parcels"] is None
    assert report["sources"][0]["live_validation"] == "not_run"
    assert report["ledger_sections"][0]["explicit_catalog_references"] == ["county_parcels"]
    assert report["ledger_sections"][1]["reconciliation_status"] == "manual_reconciliation_required"


def test_report_preserves_holds_and_multiline_decisions():
    candidate = SimpleNamespace(record_type="parcel", key="held", status="legal_hold", blocker_summary="Written permission needed")
    report = build_parcel_readiness([], [candidate], "## County\n**Decision: narrow context;\nowner data hold.**\n")
    assert report["candidates"][0]["status"] == "legal_hold"
    assert report["ledger_sections"][0]["recorded_decision"] == "narrow context; owner data hold."


def test_report_keeps_sections_separate_with_windows_newlines_and_subheadings():
    ledger = "## First\r\n### Scope\r\nNo decision yet.\r\n## Second\r\n**Decision: hold.**\r\n"
    sections = build_parcel_readiness([], [], ledger)["ledger_sections"]
    assert [row["jurisdiction"] for row in sections] == ["First", "Second"]
    assert sections[0]["recorded_decision"] is None
    assert sections[1]["recorded_decision"] == "hold."
