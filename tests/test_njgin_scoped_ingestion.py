"""Synthetic transport through the real NJ profile; not live/production acceptance."""
from decimal import Decimal

import pytest

from app.models.ingestion import IngestionSource, RawSourceRecord
from app.models.parcel import ParcelRecord
from app.services.ingestion.connectors import ConnectorResponseError, factory
from app.services.ingestion.health import validate_source_canary
from scripts.retail_parcel_refresh import scoped_entry
from tests.internal_operations_fixtures import internal_operator as internal_operator
from tests.test_nearby_parcels import _admin_headers


@pytest.mark.parametrize("unexpected_field", [None, "ST_ADDRESS", "CITY_STATE", "ZIP5", "OWNER_NAME"])
def test_njgin_scope_ingests_replays_and_exposes_only_tenant_map_context(
    client, internal_operator, db, monkeypatch,
    unexpected_field,
):
    calls = []
    ring = [[-75.311, 39.739], [-75.309, 39.739], [-75.309, 39.741],
            [-75.311, 39.741], [-75.311, 39.739]]

    class Transport:
        def get_json(self, url, *, params=None, headers=None):
            calls.append(params)
            features = [{
                "attributes": {
                    "OBJECTID": 1, "PIN_NODUP": "0817_SYNTHETIC_1",
                    "PAMS_PIN": "0817_SYNTHETIC_1",
                    "PROP_LOC": "100 Test Way", "MUN_NAME": "SWEDESBORO BORO",
                    "CALC_ACRE": 1,
                },
                "geometry": {"rings": [ring]},
            }]
            if unexpected_field:
                features.append({"attributes": {
                    **features[0]["attributes"], "OBJECTID": 2,
                    "PIN_NODUP": "0817_SYNTHETIC_2", unexpected_field: "DO_NOT_RETAIN",
                }, "geometry": {"rings": [ring]}})
            return {"spatialReference": {"wkid": 4326}, "features": features}

    monkeypatch.setattr(factory, "RetryingHttpClient", lambda **kwargs: Transport())
    headers = _admin_headers(db)
    entry = scoped_entry("new_jersey_njgin_statewide_parcels_nearby_narrow",
                         anchor_id="synthetic-anchor-not-live-evidence",
                         latitude=39.74, longitude=-75.31, radius_miles=1)
    assert entry.is_active is False
    # Activation is only for this test's disposable SQLite database.
    payload = entry.model_dump(mode="json")
    payload["is_active"] = True
    source = client.post("/ingestion/sources", headers=headers, json=payload)
    assert source.status_code == 201, source.text
    source_id = source.json()["id"]
    persisted_source = db.get(IngestionSource, source_id)
    if unexpected_field:
        with pytest.raises(ConnectorResponseError, match="reviewed field scope"):
            validate_source_canary(persisted_source, sample_size=3)
    else:
        canary = validate_source_canary(persisted_source, sample_size=3)
        assert canary.ok and canary.records_valid == 1
    for expected_inserts in (1, 0):
        run = client.post(f"/ingestion/sources/{source_id}/runs", headers=headers,
                          json={"max_pages": 1})
        assert run.status_code == 201, run.text
        if unexpected_field:
            assert run.json()["status"] == "failed", run.text
            assert "DO_NOT_RETAIN" not in run.text
            assert db.query(RawSourceRecord).count() == db.query(ParcelRecord).count() == 0
            return
        assert run.json()["status"] == "completed", run.text
        assert run.json()["records_inserted"] == expected_inserts
        assert run.json()["records_failed"] == 0

    parcel = db.query(ParcelRecord).one()
    raw = db.query(RawSourceRecord).one()
    assert parcel.source_id == source_id and parcel.latest_raw_record_id == raw.id
    assert parcel.external_parcel_id == "0817_SYNTHETIC_1"
    assert parcel.state == "NJ"
    assert parcel.latitude == pytest.approx(39.74, abs=0.000001)
    assert parcel.longitude == pytest.approx(-75.31, abs=0.000001)
    assert parcel.land_area_sq_ft == Decimal("43560")
    assert parcel.address == "100 Test Way"
    assert parcel.postal_code is None
    assert not {"ST_ADDRESS", "CITY_STATE", "ZIP5", "ZIP_CODE", "ZIP_PLUS4"} & raw.payload.keys()
    assert not parcel.zoning_code
    assert not {"ownership", "sale", "zoning"} & {fact.fact_type for fact in parcel.facts}
    assert all(call["distance"] == 1 and call["outSR"] == 4326 for call in calls)
    assert all(call["outFields"] == entry.settings["connector"]["out_fields"] for call in calls)
    detail = client.get(f"/parcels/{parcel.id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["parcel"]["boundary_geometry"]["type"] == "Polygon"
    assert detail.json()["parcel"]["boundary_geometry"]["coordinates"] == [ring]
    assert detail.json()["graph_entity"] is not None
    other = client.post("/auth/register", json={
        "email": "other-nj-scope@example.com", "password": "CorrectHorseBattery42",
        "full_name": "Other workspace", "organization_name": "Other NJ Scope",
    })
    assert other.status_code == 201, other.text
    other_headers = {"Authorization": "Bearer " + other.json()["access_token"]}
    assert client.get(f"/parcels/{parcel.id}", headers=other_headers).status_code == 404
