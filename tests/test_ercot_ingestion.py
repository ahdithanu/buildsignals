"""Offline ERCOT catalog contract and supported ingestion persistence regressions.

The real factory, XLSX parser, normalizer, ingestion service and disposable SQLite
database are used. Only HTTP transport is replaced with synthetic in-memory data;
the held candidate is never enabled, fetched live or registered outside the test DB.
"""
from __future__ import annotations

from copy import deepcopy
from email.message import Message

import pytest

from app.models.ingestion import PermitEvent, PermitRecord, RawSourceRecord
from app.services.ingestion.catalog import load_candidate_catalog, load_catalog
from app.services.ingestion.connectors import build_connector
from app.services.ingestion.connectors import factory as connector_factory
from app.services.ingestion.health import validate_candidate_source_canary
from app.services.ingestion.normalization import (
    CANONICAL_FIELDS,
    normalize_permit,
    prepare_mapped_record,
)
from app.services.ingestion.rollout import build_production_rollout_manifest
from tests.xlsx_builder import build_xlsx

SOURCE_KEY = "ercot_tx_interconnection_queue"
ENDPOINT = "https://www.ercot.com/misapp/GetReports.do?reportTypeId=15933"
DOWNLOAD = (
    "https://www.ercot.com/misdownload/servlets/mirDownload"
    "?mimic_duns=000000000&doclookupId=123456"
)
TAB = "Project Details - Large Gen"


def _candidate():
    return next(row for row in load_candidate_catalog() if row.key == SOURCE_KEY)


class SyntheticHttp:
    def __init__(self):
        self.calls: list[str] = []
        self.workbook = build_xlsx({TAB: [
            ["INR", "Project Name", "County", "Fuel", "Technology", "Capacity (MW)",
             "GIM Study Phase", "Projected COD", "Approved for Synchronization",
             "Approved for Energization", "IA Signed"],
            ["QUEUE-1", "Study Project", "Travis", "SOL", "PV", 125,
             "SS Completed, FIS Completed, IA", "2027-06-01", None, None, "2026-09-01"],
            ["QUEUE-2", "Generic Approval", "Travis", "SOL", "PV", 25,
             "Approved", "2027-07-01", None, None, None],
            ["QUEUE-3", "Synchronization Project", "Glasscock", "WIN", "WT", 200,
             "SS Completed, FIS Completed, IA", "2027-08-01", "2026-09-15", None, None],
            ["QUEUE-4", "Placeholder Approval", "Travis", "SOL", "PV", 50,
             "Screening Study", "2027-09-01", "Pending", "N/A", None],
        ]})

    def get_bytes(self, url, *, max_bytes, params=None, headers=None):
        self.calls.append(url)
        if url == ENDPOINT:
            body = (
                "<html><table><tr><td>"
                "RPT.00015933.0000000000000000.20261001.010000.GIS_Report_September2026.xlsx"
                "</td><td><a href='/misdownload/servlets/mirDownload?doclookupId=123456'>"
                "xlsx</a></td></tr></table></html>"
            ).encode()
        elif url == DOWNLOAD:
            body = self.workbook
        else:
            raise AssertionError(f"Unexpected synthetic HTTP request: {url}")
        assert len(body) <= max_bytes
        return body, Message()


@pytest.fixture()
def synthetic_http(monkeypatch):
    transport = SyntheticHttp()
    monkeypatch.setattr(connector_factory, "RetryingHttpClient", lambda **_kwargs: transport)
    return transport


def test_ercot_candidate_stays_held_and_excluded_from_production():
    candidate = _candidate()
    assert candidate.status == "technical_hold"
    assert candidate.can_run_canary is False
    assert candidate.probe_settings["freshness_field"] == "post_date"
    assert candidate.probe_settings["freshness_semantics"] == "dataset_refreshed_at"
    assert SOURCE_KEY not in {row.key for row in load_catalog()}
    manifest = build_production_rollout_manifest(
        load_catalog(), candidates=load_candidate_catalog(), shard_count=4,
    )
    assert SOURCE_KEY not in manifest.candidate_retries.candidate_keys
    assert all(SOURCE_KEY not in wave.source_keys for wave in manifest.waves)
    with pytest.raises(ValueError, match="Only operational_retry candidates"):
        validate_candidate_source_canary(candidate)


def test_catalog_probe_normalizes_real_connector_records(synthetic_http):
    candidate = _candidate()
    assert {row.canonical_field for row in candidate.probe_field_mappings} <= CANONICAL_FIELDS
    assert set(candidate.probe_settings["defaults"]) <= CANONICAL_FIELDS
    connector = build_connector(candidate.adapter, candidate.probe_settings["connector"])
    records = list(connector.iter_records())
    expected = {"QUEUE-1": "pre_approval", "QUEUE-2": "pre_approval",
                "QUEUE-3": "approved", "QUEUE-4": "pre_approval"}
    assert len(records) == len(expected)
    for record in records:
        prepared, mapping = prepare_mapped_record(record, candidate.probe_field_mappings)
        normalized = normalize_permit(
            prepared, mapping, defaults=candidate.probe_settings["defaults"],
        )
        assert normalized.values["approval_stage"] == expected[record["inr"]]
        assert normalized.values["application_number"] == record["inr"]
        assert normalized.values["permit_type"] == "Generation interconnection request"
        assert "permit_number" not in normalized.values
        assert "completed_at" not in normalized.values
        assert "filed_at" not in normalized.values
        for key in ("county", "fuel", "technology", "capacity_mw", "projected_cod",
                    "stage", "event_type", "report_period", "post_date", "tab"):
            assert normalized.unmapped[key] == record[key]
        assert normalized.unmapped["report_period"] == "2026-09"
        assert normalized.unmapped["post_date"] == "2026-10-01"
    assert synthetic_http.calls == [ENDPOINT, DOWNLOAD]


def test_supported_ingestion_persists_interconnection_evidence_and_is_idempotent(
    client, db, synthetic_http,
):
    candidate = _candidate()
    payload = {
        "key": "synthetic_ercot_contract_test",
        "name": "Synthetic offline ERCOT test",
        "adapter": candidate.adapter,
        "record_type": candidate.record_type,
        "jurisdiction": candidate.jurisdiction,
        "base_url": candidate.base_url,
        "settings": deepcopy(candidate.probe_settings),
        "field_mappings": [row.model_dump() for row in candidate.probe_field_mappings],
    }
    created = client.post("/ingestion/sources", json=payload)
    assert created.status_code == 201, created.text
    run_url = f"/ingestion/sources/{created.json()['id']}/runs"
    first = client.post(run_url, json={"max_pages": 1})
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "completed", first.text
    assert first.json()["records_seen"] == first.json()["records_inserted"] == 4
    assert first.json()["records_failed"] == 0

    records = {row.application_number: row for row in db.query(PermitRecord).all()}
    assert set(records) == {"QUEUE-1", "QUEUE-2", "QUEUE-3", "QUEUE-4"}
    for inr, record in records.items():
        assert record.approval_stage == ("approved" if inr == "QUEUE-3" else "pre_approval")
        assert record.permit_type == "Generation interconnection request"
        assert record.permit_subtype == "ERCOT Monthly GIS queue"
        assert record.permit_number is None
        assert record.filed_at is record.approved_at is record.completed_at is None
        assert record.attributes["stage"] == ("decision" if inr == "QUEUE-3" else "application")
        assert record.attributes["event_type"].startswith("interconnection_queue_")
        assert record.attributes["capacity_mw"]
        assert record.attributes["projected_cod"].startswith("2027-")
        assert record.attributes["report_period"] == "2026-09"
        assert record.attributes["post_date"] == "2026-10-01"
        assert record.attributes["tab"] == TAB
        assert record.source_url == DOWNLOAD
    assert records["QUEUE-3"].attributes["approved_synchronization"] == "2026-09-15"
    assert db.query(RawSourceRecord).count() == db.query(PermitEvent).count() == 4
    for raw in db.query(RawSourceRecord).all():
        assert raw.payload["inr"] in records
        assert raw.payload["report_label"] == "GIS_Report_September2026"
        assert raw.payload["county"]
        assert raw.source_updated_at.date().isoformat() == "2026-10-01"

    second = client.post(run_url, json={"max_pages": 1})
    assert second.status_code == 201, second.text
    assert second.json()["status"] == "completed"
    assert second.json()["records_inserted"] == second.json()["records_updated"] == 0
    assert second.json()["records_failed"] == 0
    assert db.query(PermitRecord).count() == db.query(RawSourceRecord).count() == 4
    assert db.query(PermitEvent).count() == 4
    assert synthetic_http.calls == [ENDPOINT, DOWNLOAD, ENDPOINT, DOWNLOAD]
