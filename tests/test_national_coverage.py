from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.main import app
from app.services.ingestion.national_coverage import national_parcel_coverage
from app.utils.auth_deps import get_current_user


def test_national_parcel_coverage_is_honest_about_measured_vs_configured(monkeypatch, db):
    monkeypatch.setattr(
        "app.services.ingestion.national_coverage.load_catalog",
        lambda: [
            SimpleNamespace(key="tx-parcels", record_type="parcel", is_active=True,
                            jurisdiction="Austin, TX", settings={}),
            SimpleNamespace(key="ca-permits", record_type="permit", is_active=True,
                            jurisdiction="Los Angeles, CA", settings={}),
        ],
    )
    monkeypatch.setattr(
        "app.services.ingestion.national_coverage.load_candidate_catalog",
        lambda include_promoted=True: [
            SimpleNamespace(key="or-parcels", record_type="parcel", jurisdiction="Bend, OR",
                            status="queued", model_dump=lambda: {}),
        ],
    )
    monkeypatch.setattr(
        "app.services.ingestion.national_coverage.measured_coverage",
        lambda *args, **kwargs: {
            "readiness_states": [{
                "state": "TX", "source_count": 1, "stored_records": 4,
                "geocoded_records": 3, "recently_seen_records": 4,
            }],
        },
    )
    monkeypatch.setattr(
        "app.services.ingestion.national_coverage._state_parcel_counts",
        lambda db: {},
    )

    report = national_parcel_coverage(db, now=datetime(2026, 10, 21, tzinfo=timezone.utc))

    assert report["summary"]["state_count"] == 50
    assert report["summary"]["measured_state_count"] == 1
    assert report["summary"]["configured_only_state_count"] == 0
    assert report["summary"]["candidate_only_state_count"] == 1
    assert report["summary"]["uncovered_state_count"] == 48
    states = {row["state"]: row for row in report["states"]}
    assert states["TX"]["posture"] == "measured"
    assert states["TX"]["stored_parcel_records"] == 4
    assert states["OR"]["posture"] == "candidate_only"
    assert states["CA"]["posture"] == "uncovered"
    target_states = {row["state"] for row in report["next_connector_targets"]}
    assert {"CA", "OR"}.issubset(target_states)


def test_national_parcel_coverage_prioritizes_availability_evidence(monkeypatch, db):
    monkeypatch.setattr(
        "app.services.ingestion.national_coverage.load_catalog",
        lambda: [SimpleNamespace(key="tx-parcels", record_type="parcel", is_active=True,
                                 jurisdiction="Austin, TX", settings={})],
    )
    monkeypatch.setattr(
        "app.services.ingestion.national_coverage.load_candidate_catalog",
        lambda include_promoted=True: [],
    )
    monkeypatch.setattr(
        "app.services.ingestion.national_coverage.measured_coverage",
        lambda *args, **kwargs: {"readiness_states": [{
            "state": "TX", "source_count": 1, "stored_records": 4,
            "geocoded_records": 4, "recently_seen_records": 4,
        }]},
    )
    monkeypatch.setattr(
        "app.services.ingestion.national_coverage._state_parcel_counts",
        lambda db: {"TX": {
            "nearby_candidate_parcels": 3,
            "verified_available_parcels": 1,
            "nearby_verified_available_parcels": 1,
        }},
    )

    report = national_parcel_coverage(db)
    texas = next(row for row in report["states"] if row["state"] == "TX")

    assert texas["next_action"] == "review_verified_available_parcels"
    assert report["summary"]["nearby_verified_available_parcels"] == 1


def test_national_parcel_coverage_executes_real_empty_inventory_queries(monkeypatch, db):
    monkeypatch.setattr(
        "app.services.ingestion.national_coverage.load_catalog",
        lambda: [],
    )
    monkeypatch.setattr(
        "app.services.ingestion.national_coverage.load_candidate_catalog",
        lambda include_promoted=True: [],
    )

    report = national_parcel_coverage(db)

    assert report["summary"]["state_count"] == 50
    assert report["summary"]["stored_parcel_records"] == 0
    assert report["summary"]["nearby_candidate_parcels"] == 0
    assert report["summary"]["verified_available_parcels"] == 0
    assert report["summary"]["uncovered_state_count"] == 50


def test_national_parcel_coverage_endpoint_returns_typed_report(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.ingestion.national_parcel_coverage",
        lambda db: {
            "measured_at": datetime(2026, 10, 21, tzinfo=timezone.utc),
            "record_type": "parcel",
            "scope": "synthetic",
            "coverage_claim": "synthetic",
            "summary": {
                "state_count": 50,
                "measured_state_count": 0,
                "configured_only_state_count": 0,
                "candidate_only_state_count": 0,
                "uncovered_state_count": 50,
                "states_with_nearby_candidates": 0,
                "states_with_verified_available_parcels": 0,
                "stored_parcel_records": 0,
                "geocoded_parcel_records": 0,
                "nearby_candidate_parcels": 0,
                "verified_available_parcels": 0,
                "nearby_verified_available_parcels": 0,
            },
            "states": [],
            "next_connector_targets": [],
            "warnings": [],
        },
    )
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "test", "org_id": "default-org"}
    try:
        response = client.get("/ingestion/coverage/national-parcels")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()["summary"]["state_count"] == 50
