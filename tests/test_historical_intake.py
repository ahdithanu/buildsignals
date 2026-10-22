import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.ingestion import PermitRecord, RawSourceRecord
from app.models.temporal import TemporalObservation
from app.services.ingestion.catalog import load_catalog
from app.services.ingestion.connectors.base import FetchEnvelope
from app.services.ingestion.historical_intake import (
    SITE_ENGINEERING_ATTRIBUTE,
    SITE_ENGINEERING_METHODOLOGY_VERSION,
    SITE_ENGINEERING_SOURCE_ID,
    SITE_ENGINEERING_SOURCE_KEY,
    historical_entry,
    normalize_site_engineering_observations,
    provider_count,
    run_local_intake,
)
from app.services.temporal_service import observation_series_key

KEY = "columbus_oh_commercial_building_permits"
SITE_KEY = SITE_ENGINEERING_SOURCE_KEY


def _epoch_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _site_record(*, status: str = "Approved") -> dict:
    filed = datetime(2023, 1, 5, tzinfo=timezone.utc)
    updated = datetime(2023, 1, 12, tzinfo=timezone.utc)
    return {
        "OBJECTID": 1001,
        "B1_ALT_ID": "SYNTH-2023-0001",
        "B1_PER_GROUP": "Engineering",
        "B1_PER_TYPE": "Site Compliance Plan",
        "B1_PER_SUB_TYPE": "Final",
        "B1_PER_CATEGORY": "New Application",
        "B1_PARCEL_NBR": "SYNTH-PARCEL-1",
        "SITE_ADDRESS": "100 Synthetic Avenue",
        "B1_SITUS_ZIP": "43215",
        "B1_SHORT_NOTES": "Synthetic mixed-use site engineering record",
        "APPLICANT_BUS_NAME": "Synthetic Development LLC",
        "FILED_YEAR": filed.year,
        "B1_FILE_DD": _epoch_ms(filed),
        "B1_APPL_STATUS": status,
        "LAST_STATUS_DT": _epoch_ms(updated),
        "B1_WORK_DESC": "Synthetic site engineering application.",
        "ACA_URL": "https://example.invalid/synthetic-columbus-record",
    }


def test_site_engineering_historical_scope_pins_approved_filed_at_cohort():
    entry = historical_entry(SITE_KEY, date(2023, 1, 1), date(2023, 2, 1))
    where = entry.settings["connector"]["where"]

    assert "B1_FILE_DD >= TIMESTAMP '2023-01-01 00:00:00'" in where
    assert "B1_FILE_DD < TIMESTAMP '2023-02-01 00:00:00'" in where
    assert "B1_APPL_STATUS IN ('Approved', 'Complete', 'Completed', 'Closed')" in where
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["page_size"] == 500
    assert entry.settings["schedule_mode"] == "manual"
    assert entry.settings["historical_qualification"]["status"] == "gated"
    assert entry.settings["historical_qualification"]["can_run_canary"] is False

    original = next(e for e in load_catalog() if e.key == SITE_KEY)
    assert original.settings["schedule_mode"] == "automatic"
    assert "B1_FILE_DD >= TIMESTAMP" not in original.settings["connector"]["where"]


def test_site_engineering_normalization_keeps_event_and_capture_times_separate():
    received = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)
    recorded = datetime(2026, 10, 20, 15, 2, tzinfo=timezone.utc)
    rows = normalize_site_engineering_observations(
        _site_record(),
        entity_id="graph-permit-synthetic-1",
        first_observed_at=received,
        recorded_at=recorded,
    )

    filed, stage = rows
    assert filed["attribute"] == SITE_ENGINEERING_ATTRIBUTE
    assert filed["value"] == filed["effective_at"] == "2023-01-05T00:00:00+00:00"
    assert filed["source_filed_at"] == "2023-01-05T00:00:00+00:00"
    assert filed["source_updated_at"] == "2023-01-12T00:00:00+00:00"
    assert filed["source_id"] == SITE_ENGINEERING_SOURCE_ID
    assert filed["source_key"] == SITE_ENGINEERING_SOURCE_KEY
    assert filed["first_observed_at"] == received.isoformat()
    assert filed["recorded_at"] == recorded.isoformat()
    assert filed["recorded_at"] != filed["source_filed_at"]
    assert filed["series_key"] == observation_series_key(
        "graph-permit-synthetic-1", SITE_ENGINEERING_SOURCE_ID, "SYNTH-2023-0001",
        SITE_ENGINEERING_ATTRIBUTE, SITE_ENGINEERING_METHODOLOGY_VERSION,
    )
    assert stage["attribute"] == "permit.approval_stage"
    assert stage["value"] == "approved"
    assert stage["effective_at"] == "2023-01-12T00:00:00+00:00"


def test_site_engineering_normalization_rejects_unapproved_or_untrusted_capture_time():
    with pytest.raises(ValueError, match="only accepts approved"):
        normalize_site_engineering_observations(
            _site_record(status="Under Review"),
            entity_id="graph-permit-synthetic-1",
            first_observed_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
            recorded_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_site_engineering_observations(
            _site_record(),
            entity_id="graph-permit-synthetic-1",
            first_observed_at=datetime(2026, 10, 20),
            recorded_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
        )
    with pytest.raises(ValueError, match="1 to 36 characters"):
        normalize_site_engineering_observations(
            _site_record(),
            entity_id="x" * 37,
            first_observed_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
            recorded_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
        )


def test_synthetic_columbus_fixture_is_labeled_and_loadable_through_contract(db):
    from app.services.corpus_qualification import CorpusQualificationRequest, qualify_corpus
    from eval.replay.manifest import load_fixture

    path = Path("tests/fixtures/columbus/site_engineering_intake_synthetic.jsonl")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert rows and all(row["fixture_status"] == "synthetic_non_qualified" for row in rows)
    assert all(row["recorded_at"].startswith("2026-10-20") for row in rows)
    assert load_fixture(db, path).source_id == SITE_ENGINEERING_SOURCE_ID

    report = qualify_corpus(
        db,
        CorpusQualificationRequest(
            as_of=datetime(2026, 10, 20, 23, tzinfo=timezone.utc),
            sources=[{"source_id": SITE_ENGINEERING_SOURCE_ID, "methodology_version": SITE_ENGINEERING_METHODOLOGY_VERSION}],
            city="Columbus",
            state="OH",
        ),
    )
    assert report["verdict"] == "insufficient_depth"
    assert report["completeness"]["event_date_completeness"] == 1.0


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
