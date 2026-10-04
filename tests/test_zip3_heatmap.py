from datetime import datetime, timezone

from app.models.ingestion import PermitRecord, RawSourceRecord
from app.models.parcel import ParcelFact, ParcelRecord
from app.services.zip3_heatmap import zip3_heatmap
from tests.test_nearby_parcels import _add_parcel, _admin_headers, _setup_confirmed_signal


def test_zip3_heatmap_separates_candidates_from_verified_for_sale(client, db, tmp_path):
    deal, source_data, match = _setup_confirmed_signal(client, db, tmp_path)
    permit = db.query(PermitRecord).one()
    permit.postal_code = "78701"
    permit.approval_stage = "pre_approval"
    raw = db.query(RawSourceRecord).one()
    _add_parcel(
        db, source_data["id"], raw.id, "P-HEAT", -97.735,
        land_area_sq_ft=80_000,
        land_value=1_000_000,
        improvement_value=100_000,
        zoning_code="Commercial Retail",
        land_use="Retail",
    )
    db.commit()
    created = client.post(f"/deals/{deal['id']}/nearby-parcel-searches", json={
        "anchor_brand_match_id": match.id,
        "radius_miles": 2,
        "persona": "developer",
    })
    assert created.status_code == 201, created.text
    candidate_id = created.json()["candidates"][0]["id"]
    assert client.patch(f"/parcel-candidates/{candidate_id}", json={"review_status": "shortlisted"}).status_code == 200

    result = zip3_heatmap(db)
    top = result["items"][0]
    assert top["zip3"] == "787"
    assert top["latitude"] == 30.2672
    assert round(top["longitude"], 3) == -97.739
    assert top["pre_approval_signals"] == 1
    assert top["parcel_candidate_count"] == 1
    assert top["shortlisted_parcel_count"] == 1
    assert top["candidate_not_listing_count"] == 1
    assert top["verified_for_sale_count"] == 0
    assert top["sample_parcels"][0]["availability_label"] == "nearby_candidate_not_verified_for_sale"
    assert result["for_sale_semantics"]["verified_for_sale"].startswith("Requires listing")


def test_zip3_heatmap_endpoint_auth_state_and_limit(client, db, tmp_path):
    assert client.get("/acquisition-map/zip3-heatmap").status_code == 401
    headers = _admin_headers(db)
    _setup_confirmed_signal(client, db, tmp_path, headers=headers)
    permit = db.query(PermitRecord).one()
    permit.postal_code = "78701"
    permit.approval_stage = "pre_approval"
    db.commit()
    response = client.get("/acquisition-map/zip3-heatmap", headers=headers, params={"state": "TX", "limit": 1})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["limit"] == 1
    assert body["state"] == "TX"
    assert [item["zip3"] for item in body["items"]] == ["787"]
    assert client.get("/acquisition-map/zip3-heatmap", headers=headers, params={"state": "OH"}).json()["items"] == []


def test_zip3_heatmap_counts_only_source_backed_availability_as_verified(client, db, tmp_path):
    deal, source_data, match = _setup_confirmed_signal(client, db, tmp_path)
    permit = db.query(PermitRecord).one()
    permit.postal_code = "78701"
    raw = db.query(RawSourceRecord).one()
    _add_parcel(db, source_data["id"], raw.id, "P-LISTED", -97.735)
    parcel = db.query(ParcelRecord).filter(ParcelRecord.external_parcel_id == "P-LISTED").one()
    now = datetime.now(timezone.utc)
    db.add(ParcelFact(
        organization_id=parcel.organization_id,
        parcel_id=parcel.id,
        raw_source_record_id=raw.id,
        fact_type="availability",
        value={"status": "for_sale", "evidence_type": "broker", "asking_price": 2250000},
        source_system="test-broker-feed",
        source_url="https://broker.example/listing/P-LISTED",
        excerpt="Broker marketing page marks the parcel available for sale.",
        confidence=0.88,
        observed_at=now,
        last_verified_at=now,
        valid_from=now,
        is_current=True,
    ))
    db.commit()
    created = client.post(f"/deals/{deal['id']}/nearby-parcel-searches", json={
        "anchor_brand_match_id": match.id,
        "radius_miles": 2,
        "persona": "developer",
    })
    assert created.status_code == 201, created.text

    top = zip3_heatmap(db)["items"][0]
    assert top["verified_for_sale_count"] == 1
    assert top["candidate_not_listing_count"] == 0
    assert top["sample_parcels"][0]["availability_label"] == "verified_for_sale"
    assert top["sample_parcels"][0]["availability_source_url"] == "https://broker.example/listing/P-LISTED"
