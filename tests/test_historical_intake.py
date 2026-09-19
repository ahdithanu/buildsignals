from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.ingestion import PermitRecord, RawSourceRecord
from app.models.temporal import TemporalObservation
from app.services.ingestion.catalog import load_catalog
from app.services.ingestion.connectors.base import FetchEnvelope
from app.services.ingestion.historical_intake import (
    historical_entry,
    provider_count,
    run_local_intake,
)

KEY = "columbus_oh_commercial_building_permits"


def test_historical_scope_is_bounded_and_does_not_mutate_catalog():
    entry = historical_entry(KEY, date(2024, 1, 1), date(2024, 2, 1))
    assert "ISSUED_YEAR" not in entry.settings["connector"]["where"]
    assert "2024-02-01" in entry.settings["connector"]["where"]
    assert entry.settings["connector"]["page_size"] == 250
    original = next(e for e in load_catalog() if e.key == KEY)
    assert "ISSUED_YEAR >= 2025" in original.settings["connector"]["where"]
    assert original.settings["freshness_semantics"] == "record_updated_at"
    for start, end in [(date(2024, 1, 1), date(2024, 3, 1)), (date(2024, 2, 1), date(2024, 1, 1))]:
        with pytest.raises(ValueError):
            historical_entry(KEY, start, end)


@pytest.mark.parametrize("provider_rows", [1, 2, None])
def test_local_import_preserves_evidence_and_refuses_existing_database(tmp_path, monkeypatch, provider_rows):
    entry = historical_entry(KEY, date(2024, 1, 1), date(2024, 2, 1))
    calls = []

    def count(*_):
        calls.append(True)
        if provider_rows is None and len(calls) > 1:
            raise ValueError("Invalid final provider response")
        return provider_rows if provider_rows is not None else 1

    monkeypatch.setattr("app.services.ingestion.historical_intake.provider_count", count)
    monkeypatch.setattr(
        "app.services.ingestion.connectors.arcgis.ArcGISFeatureServerConnector.fetch",
        lambda *_: FetchEnvelope(source="arcgis_featureserver", records=({
            "OBJECTID": 1, "B1_ALT_ID": "TEST-2024", "SITE_ADDRESS": "100 TEST ST",
            "ISSUED_DT": 1704153600000, "LAST_STATUS_DT": 1704153600000,
            "PERMIT_STATUS": "Permit Issued",
        },), has_more=False, checkpoint=None),
    )
    path = tmp_path / "qualification.db"
    result = run_local_intake(path, entry, max_pages=1)
    assert result["count_reconciled"] is (provider_rows == 1)
    assert result["provider_count_error"] == ("ValueError" if provider_rows is None else None)
    assert result["coverage_verified"] is False
    assert result["workflow_readiness"]["geocoded_permits"] == 0
    assert result["workflow_readiness"]["permits_without_coordinates"] == 1
    assert result["workflow_readiness"]["nearby_search_ready"] is False
    engine = create_engine("sqlite:///" + str(path))
    with Session(engine) as db:
        assert db.query(PermitRecord).one().issued_at.year == 2024
        assert db.query(RawSourceRecord).one().received_at.year >= 2026
        assert db.query(TemporalObservation).count() > 0
    engine.dispose()
    with pytest.raises(FileExistsError):
        run_local_intake(path, entry)
    with pytest.raises(ValueError):
        run_local_intake(tmp_path / "invalid.db", entry, max_pages=5)
    assert not (tmp_path / "invalid.db").exists()


@pytest.mark.parametrize("payload", [{"count": True}, {"count": -1}, {}, [], {"count": 1, "error": {}}])
def test_provider_count_rejects_invalid_responses(payload):
    class Client:
        def get_json(self, *args, **kwargs):
            return payload

    entry = historical_entry(KEY, date(2024, 1, 1), date(2024, 2, 1))
    with pytest.raises(ValueError):
        provider_count(entry, Client())
