from datetime import datetime, timezone

from app.models.audit_log import AuditLog
from app.models.ingestion import IngestionRun, IngestionSource, RawSourceRecord
from app.models.parcel import ParcelFact, ParcelRecord
from app.services.zip3_heatmap import zip3_heatmap
from tests.test_nearby_parcels import _add_parcel, _admin_headers, _setup_confirmed_signal


def _parcel(db):
    now = datetime.now(timezone.utc)
    source = IngestionSource(
        organization_id="default-org",
        key="availability-parcels",
        name="Availability Parcels",
        adapter="csv",
        record_type="parcel",
    )
    db.add(source)
    db.flush()
    run = IngestionRun(organization_id="default-org", source_id=source.id, status="completed", trigger="manual")
    db.add(run)
    db.flush()
    raw = RawSourceRecord(
        organization_id="default-org",
        source_id=source.id,
        run_id=run.id,
        external_record_id="P-AVAILABLE",
        record_type="parcel",
        content_hash="b" * 64,
        payload={"parcel": "P-AVAILABLE"},
        received_at=now,
    )
    db.add(raw)
    db.flush()
    parcel = ParcelRecord(
        organization_id="default-org",
        source_id=source.id,
        latest_raw_record_id=raw.id,
        external_parcel_id="P-AVAILABLE",
        jurisdiction="Austin",
        county="Travis",
        state="TX",
        address="125 Congress Ave",
        city="Austin",
        postal_code="78701",
        latitude=30.2672,
        longitude=-97.7431,
        last_verified_at=now,
    )
    db.add(parcel)
    db.commit()
    return parcel


def test_availability_evidence_endpoint_creates_source_backed_fact(client, db):
    headers = _admin_headers(db)
    parcel = _parcel(db)

    response = client.post(
        f"/parcels/{parcel.id}/availability-evidence",
        headers=headers,
        json={
            "status": "for_sale",
            "evidence_type": "broker",
            "source_url": "https://broker.example/listing/P-AVAILABLE",
            "excerpt": "Broker listing marks the parcel available for sale.",
            "confidence": 0.86,
            "asking_price": 2250000,
            "contact_company": "Example Brokerage",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["fact_type"] == "availability"
    assert body["value"]["status"] == "for_sale"
    assert body["value"]["evidence_type"] == "broker"
    assert body["source_url"] == "https://broker.example/listing/P-AVAILABLE"
    fact = db.query(ParcelFact).filter(ParcelFact.parcel_id == parcel.id).one()
    assert fact.raw_source_record.record_type == "parcel_availability"
    assert fact.raw_source_record.payload["external_parcel_id"] == "P-AVAILABLE"
    assert db.query(AuditLog).filter(
        AuditLog.entity_type == "parcel",
        AuditLog.entity_id == parcel.id,
        AuditLog.action == "availability_evidence_created",
    ).count() == 1


def test_availability_evidence_requires_actual_source_evidence(client, db):
    headers = _admin_headers(db)
    parcel = _parcel(db)

    response = client.post(
        f"/parcels/{parcel.id}/availability-evidence",
        headers=headers,
        json={
            "status": "for_sale",
            "evidence_type": "broker",
            "confidence": 0.86,
        },
    )

    assert response.status_code == 422
    assert "source URL or excerpt" in response.text


def test_duplicate_availability_evidence_is_idempotent(client, db):
    headers = _admin_headers(db)
    parcel = _parcel(db)
    payload = {
        "status": "for_sale",
        "evidence_type": "listing",
        "source_url": "https://listing.example/P-AVAILABLE",
        "excerpt": "Listing marks the parcel available for sale.",
        "confidence": 0.92,
    }

    first = client.post(f"/parcels/{parcel.id}/availability-evidence", headers=headers, json=payload)
    second = client.post(f"/parcels/{parcel.id}/availability-evidence", headers=headers, json=payload)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]
    assert db.query(ParcelFact).filter(ParcelFact.parcel_id == parcel.id).count() == 1
    assert db.query(RawSourceRecord).filter(RawSourceRecord.record_type == "parcel_availability").count() == 1
    manual_source = db.query(IngestionSource).filter(
        IngestionSource.key == "manual_availability_evidence",
    ).one()
    assert db.query(IngestionRun).filter(IngestionRun.source_id == manual_source.id).count() == 1


def test_availability_observed_at_must_not_be_future(client, db):
    headers = _admin_headers(db)
    parcel = _parcel(db)

    response = client.post(
        f"/parcels/{parcel.id}/availability-evidence",
        headers=headers,
        json={
            "status": "for_sale",
            "evidence_type": "listing",
            "source_url": "https://listing.example/future",
            "confidence": 0.92,
            "observed_at": "2099-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 422
    assert "cannot be in the future" in response.text


def test_older_availability_evidence_is_retained_but_not_promoted(client, db):
    headers = _admin_headers(db)
    parcel = _parcel(db)
    newer = {
        "status": "listed",
        "evidence_type": "listing",
        "source_url": "https://listing.example/newer",
        "excerpt": "Newer listing evidence.",
        "confidence": 0.95,
        "observed_at": "2026-10-20T00:00:00Z",
    }
    older = {
        "status": "for_sale",
        "evidence_type": "broker",
        "source_url": "https://broker.example/older",
        "excerpt": "Older broker evidence.",
        "confidence": 0.9,
        "observed_at": "2026-10-19T00:00:00Z",
    }

    assert client.post(f"/parcels/{parcel.id}/availability-evidence", headers=headers, json=newer).status_code == 201
    older_response = client.post(
        f"/parcels/{parcel.id}/availability-evidence", headers=headers, json=older
    )

    assert older_response.status_code == 201, older_response.text
    facts = db.query(ParcelFact).filter(ParcelFact.parcel_id == parcel.id).all()
    assert len(facts) == 2
    current = [fact for fact in facts if fact.is_current]
    assert len(current) == 1
    assert current[0].value["status"] == "listed"
    stale = next(fact for fact in facts if not fact.is_current)
    assert stale.value["status"] == "for_sale"
    assert stale.valid_to is not None


def test_bulk_availability_import_matches_only_source_and_external_id(client, db):
    headers = _admin_headers(db)
    parcel = _parcel(db)

    response = client.post(
        "/parcel-availability/import",
        headers=headers,
        json={
            "rows": [
                {
                    "source_id": parcel.source_id,
                    "external_parcel_id": parcel.external_parcel_id,
                    "status": "for_sale",
                    "evidence_type": "listing",
                    "source_url": "https://listing.example/P-AVAILABLE",
                    "confidence": 0.92,
                },
                {
                    "source_id": parcel.source_id,
                    "external_parcel_id": "STALE-PARCEL-ID",
                    "status": "for_sale",
                    "evidence_type": "listing",
                    "source_url": "https://listing.example/STALE-PARCEL-ID",
                    "confidence": 0.92,
                },
            ],
        },
    )

    assert response.status_code == 201, response.text
    assert response.json() == {
        "imported": 1,
        "skipped": 1,
        "errors": [{
            "row": 1,
            "reason": "No active parcel matches source_id and external_parcel_id",
        }],
    }
    fact = db.query(ParcelFact).filter(ParcelFact.parcel_id == parcel.id).one()
    assert fact.value["status"] == "for_sale"


def test_availability_evidence_import_flows_into_zip3_heatmap(client, db, tmp_path):
    headers = _admin_headers(db)
    deal, source_data, match = _setup_confirmed_signal(client, db, tmp_path, headers=headers)
    raw = db.query(RawSourceRecord).one()
    parcel = _add_parcel(db, source_data["id"], raw.id, "P-LIVE-LISTING", -97.735)
    db.commit()
    created = client.post(f"/deals/{deal['id']}/nearby-parcel-searches", headers=headers, json={
        "anchor_brand_match_id": match.id,
        "radius_miles": 2,
        "persona": "developer",
    })
    assert created.status_code == 201, created.text
    response = client.post(
        f"/parcels/{parcel.id}/availability-evidence",
        headers=headers,
        json={
            "status": "listed",
            "evidence_type": "listing",
            "source_url": "https://listing.example/P-LIVE-LISTING",
            "confidence": 0.91,
        },
    )
    assert response.status_code == 201, response.text

    top = zip3_heatmap(db)["items"][0]
    assert top["verified_for_sale_count"] == 1
    assert top["sample_parcels"][0]["availability_label"] == "verified_for_sale"
    verified = client.get("/acquisition-radar?availability=verified", headers=headers)
    assert verified.status_code == 200, verified.text
    assert verified.json()["total"] == 1
    assert verified.json()["items"][0]["parcel"]["external_parcel_id"] == "P-LIVE-LISTING"
    unverified = client.get("/acquisition-radar?availability=unverified", headers=headers)
    assert unverified.status_code == 200, unverified.text
    assert unverified.json()["items"] == []
