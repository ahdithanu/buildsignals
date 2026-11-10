from datetime import datetime, timezone
from uuid import uuid4

from app.models.ingestion import IngestionRun, IngestionSource, PermitRecord, RawSourceRecord
from app.services import investment_areas as areas
from app.utils.org_scope import (
    SYSTEM_USER_ID,
    RequestContext,
    reset_current_context,
    set_current_context,
)


def snapshot():
    return {"year": 2025, "captured_at": "2026-11-10T07:00:00+00:00", "snapshot_id": "a"*64,
        "provenance": [], "metros": [{"cbsa": code, "name": f"Synthetic {code}",
            "hpi": {2023: 100, 2025: 110},
            "units": {2022: 100, 2023: 100, 2024: 100, 2025: 110}}
            for code in ["36100", "45300"] + [f"{10000+i}" for i in range(18)]]}


def register(client, email):
    email = email.replace("@example.test", "@example.com")
    response = client.post("/auth/register", json={"email": email,
        "password": "CorrectHorseBattery42", "full_name": "Synthetic Reviewer",
        "organization_name": email.split("@")[0]})
    assert response.status_code == 201, response.text
    return response.json()


def seed(db, org):
    source = IngestionSource(organization_id=org, key="ocala_fl_gis_new_building_projects",
        name="Synthetic Ocala context", adapter="arcgis", record_type="permit",
        is_active=True, settings={"context_only": True})
    db.add(source); db.flush()
    run = IngestionRun(organization_id=org, source_id=source.id, status="completed",
        completed_at=datetime.now(timezone.utc))
    db.add(run); db.flush()
    raw = RawSourceRecord(organization_id=org, source_id=source.id, run_id=run.id,
        external_record_id="synthetic", record_type="permit", content_hash="b"*64, payload={})
    db.add(raw); db.flush()
    db.add(PermitRecord(organization_id=org, source_id=source.id, latest_raw_record_id=raw.id,
        external_record_id="synthetic", normalization_hash="c"*64, latitude=29, longitude=-82))
    db.commit()


def test_http_model_uses_public_snapshot_and_only_request_tenant_evidence(client, db, monkeypatch):
    monkeypatch.setattr(areas, "current_snapshot", snapshot)
    a, b = register(client, "area-a@example.test"), register(client, "area-b@example.test")
    seed(db, a["organization_id"])
    outputs = []
    for user in (a, b):
        response = client.get("/v1/investment-areas?cbsa=36100",
            headers={"Authorization": f"Bearer {user['access_token']}"})
        assert response.status_code == 200, response.text
        assert response.headers["Cache-Control"] == "no-store"
        assert "Authorization" in response.headers["Vary"]
        outputs.append(response.json())
    assert outputs[0]["local_evidence"]["records"] == 1
    assert outputs[1]["local_evidence"]["records"] == 0
    assert outputs[0]["market"] == outputs[1]["market"]
    assert outputs[0]["status"] == "research"
    assert outputs[0]["investment_quality"]["status"] == "insufficient_data"
    assert "rent_yield" in outputs[0]["investment_quality"]["missing"]


def test_http_requires_login_and_valid_geography(client, monkeypatch):
    monkeypatch.setattr(areas, "current_snapshot", snapshot)
    assert client.get("/v1/investment-areas?cbsa=36100").status_code == 401
    user = register(client, "area-validation@example.test")
    h = {"Authorization": f"Bearer {user['access_token']}"}
    assert client.get("/v1/investment-areas?cbsa=Ocala", headers=h).status_code == 422
    assert client.get("/v1/investment-areas?cbsa=99999", headers=h).status_code == 404


def test_http_input_failure_is_clean_retryable_503(client, monkeypatch):
    def fail():
        raise RuntimeError("private upstream debug detail")
    monkeypatch.setattr(areas, "current_snapshot", fail)
    user = register(client, "area-failure@example.test")
    response = client.get("/v1/investment-areas?cbsa=36100",
        headers={"Authorization": f"Bearer {user['access_token']}"})
    assert response.status_code == 503 and response.headers["Retry-After"] == "60"
    assert "private" not in response.text


def test_local_context_never_boosts_rank_and_unknown_metro_is_not_zero_inventory(db):
    token = set_current_context(RequestContext(str(uuid4()), SYSTEM_USER_ID))
    try:
        output = areas.investment_area(db, "45300", snapshot=snapshot())
        assert output["local_evidence"]["geography_match"] == "unmapped"
        assert output["local_evidence"]["is_complete_metro_inventory"] is False
    finally:
        reset_current_context(token)


def test_known_metro_without_aligned_hpi_returns_demand_context_not_fabricated_rank(db):
    data = snapshot()
    data["metros"] = [row for row in data["metros"] if row["cbsa"] != "45300"]
    data["metros"].append({**data["metros"][-1], "cbsa": "88888"})
    data["context_metros"] = {"45300": {"name": "Synthetic Tampa metro",
        "population_2024": 1000, "population_2025": 1010, "net_migration_2025": 15}}
    token = set_current_context(RequestContext(str(uuid4()), SYSTEM_USER_ID))
    try:
        output = areas.investment_area(db, "45300", snapshot=data)
        assert output["status"] == "insufficient_data"
        assert output["market"]["score"] is None
        assert output["market"]["population_growth_1yr"] > 0
    finally:
        reset_current_context(token)


def test_public_cache_has_single_refresh_and_does_not_serve_expired_data(monkeypatch):
    from app.services import investment_inputs

    calls = []
    now = [0.0]
    monkeypatch.setattr(areas, "monotonic", lambda: now[0])
    monkeypatch.setattr(areas, "_public_cache", None)
    monkeypatch.setattr(areas, "_cache_until", 0)
    monkeypatch.setattr(areas, "_retry_after", 0)
    monkeypatch.setattr(investment_inputs, "get_snapshot", lambda: calls.append(1) or snapshot())
    assert areas.current_snapshot() == areas.current_snapshot()
    assert len(calls) == 1
    now[0] = 3601

    def fail():
        calls.append(1)
        raise ValueError("untrusted upstream body")
    monkeypatch.setattr(investment_inputs, "get_snapshot", fail)
    import pytest
    for _ in range(2):
        with pytest.raises(RuntimeError, match="unavailable"):
            areas.current_snapshot()
    assert len(calls) == 2
