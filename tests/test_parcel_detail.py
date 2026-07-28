from __future__ import annotations

from datetime import datetime, timezone

from app.models.deal import Deal
from app.models.graph import GraphEntityType, GraphRelationshipType
from app.models.ingestion import IngestionRun, IngestionSource, PermitRecord, RawSourceRecord
from app.models.parcel import NearbyParcelCandidate, NearbyParcelSearch
from app.models.parcel import ParcelFact, ParcelRecord
from app.schemas.graph import GraphEntityCreate, GraphEvidenceCreate, GraphRelationshipCreate
from app.services.graph_service import create_relationship, link_entity_to_record, resolve_entity


def test_parcel_detail_returns_facts_and_search_context(client, db):
    deal = client.post("/deals", json={
        "name": "Parcel Signal Deal",
        "address": "300 Main St",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
        "property_type": "retail",
    }).json()

    now = datetime.now(timezone.utc)
    source = IngestionSource(
        organization_id="default-org",
        key="test-parcels",
        name="Test Parcels",
        adapter="csv",
        record_type="parcel",
    )
    db.add(source)
    db.flush()
    run = IngestionRun(
        organization_id="default-org",
        source_id=source.id,
        status="completed",
    )
    db.add(run)
    db.flush()
    raw = RawSourceRecord(
        organization_id="default-org",
        source_id=source.id,
        run_id=run.id,
        external_record_id="parcel-1",
        record_type="parcel",
        content_hash="a" * 64,
        payload={"address": "125 Main St"},
        received_at=now,
    )
    db.add(raw)
    db.flush()

    parcel = ParcelRecord(
        organization_id="default-org",
        source_id=source.id,
        latest_raw_record_id=raw.id,
        external_parcel_id="PARCEL-001",
        jurisdiction="Austin",
        county="Travis",
        state="TX",
        address="125 Main St",
        city="Austin",
        postal_code="78701",
        latitude=30.2672,
        longitude=-97.7431,
        land_area_sq_ft=50000,
        total_assessed_value=1250000,
        land_use="Retail",
        zoning_code="CS",
        attributes={
            "geometry": {
                "rings": [[
                    [-97.7441, 30.2662],
                    [-97.7421, 30.2662],
                    [-97.7421, 30.2682],
                    [-97.7441, 30.2682],
                    [-97.7441, 30.2662],
                ]],
            },
        },
        last_verified_at=now,
    )
    db.add(parcel)
    db.flush()
    fact = ParcelFact(
        organization_id="default-org",
        parcel_id=parcel.id,
        raw_source_record_id=raw.id,
        fact_type="ownership",
        value={"owner_name": "Main Street Holdings"},
        source_system="assessor",
        source_url="https://example.gov/parcels/1",
        field_path="owner_name",
        excerpt="Main Street Holdings",
        confidence=0.98,
        observed_at=now,
        last_verified_at=now,
        valid_from=now,
        is_current=True,
    )
    db.add(fact)
    parcel_entity, _ = resolve_entity(db, GraphEntityCreate(
        entity_type=GraphEntityType.parcel,
        display_name="PARCEL-001",
        source_system="test-parcels",
        source_id="test-parcels:PARCEL-001",
        address="125 Main St",
        city="Austin",
        state="TX",
        zip_code="78701",
        confidence=1.0,
        attributes={"parcel_record_id": parcel.id},
    ))
    link_entity_to_record(db, parcel_entity.id, "parcel", parcel.id, "test-parcels")
    owner_entity, _ = resolve_entity(db, GraphEntityCreate(
        entity_type=GraphEntityType.owner,
        display_name="Main Street Holdings",
        confidence=0.9,
    ))
    create_relationship(
        db,
        GraphRelationshipCreate(
            source_entity_id=parcel_entity.id,
            target_entity_id=owner_entity.id,
            relationship_type=GraphRelationshipType.owned_by,
            confidence=0.98,
            source_system="test-parcels",
            source_id="parcel-1-owner",
            attributes={"role": "owner"},
            evidence=[
                GraphEvidenceCreate(
                    source_system="assessor",
                    source_id="fact-1",
                    source_url="https://example.gov/parcels/1",
                    evidence_type="parcel_ownership",
                    excerpt="Main Street Holdings",
                    confidence=0.98,
                )
            ],
        ),
        validate_entities=False,
    )
    permit_source = IngestionSource(
        organization_id="default-org",
        key="test-permits",
        name="Test Permits",
        adapter="csv",
        record_type="permit",
    )
    db.add(permit_source)
    db.flush()
    permit_raw = RawSourceRecord(
        organization_id="default-org",
        source_id=permit_source.id,
        run_id=run.id,
        external_record_id="permit-1",
        record_type="permit",
        content_hash="b" * 64,
        payload={"permit_number": "BP-1"},
        received_at=now,
    )
    db.add(permit_raw)
    db.flush()
    permit = PermitRecord(
        organization_id="default-org",
        source_id=permit_source.id,
        latest_raw_record_id=permit_raw.id,
        external_record_id="permit-1",
        normalization_hash="c" * 64,
        permit_number="BP-1",
        approval_stage="pre_approval",
        status="Under Review",
        address="300 Main St",
        city="Austin",
        state="TX",
        postal_code="78701",
        latitude=30.2672,
        longitude=-97.7431,
        is_active=True,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(permit)
    db.flush()
    search = NearbyParcelSearch(
        organization_id="default-org",
        deal_id=deal["id"],
        anchor_brand_match_id=None,
        anchor_permit_id=permit.id,
        anchor_latitude=30.2672,
        anchor_longitude=-97.7431,
        radius_miles=2.0,
        persona="developer",
        filters={},
        result_limit=10,
        as_of=now,
        ranker_version="developer-v2",
    )
    db.add(search)
    db.flush()
    db.add(NearbyParcelCandidate(
        organization_id="default-org",
        search_id=search.id,
        parcel_id=parcel.id,
        rank=1,
        distance_miles=0.42,
        score=91.5,
        score_confidence=0.88,
        explanation={"reasons": ["Retail zoning fits buyer lens"]},
        review_status="candidate",
        ranker_version="developer-v2",
    ))
    db.commit()

    response = client.get(f"/parcels/{parcel.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["parcel"]["external_parcel_id"] == "PARCEL-001"
    assert body["parcel"]["boundary_geometry"]["type"] == "Polygon"
    assert len(body["parcel"]["boundary_geometry"]["coordinates"][0]) == 5
    assert body["search_count"] == 1
    assert body["facts"][0]["source_url"] == "https://example.gov/parcels/1"
    assert body["search_hits"][0]["deal_name"] == "Parcel Signal Deal"
    assert body["search_hits"][0]["deal_id"] == deal["id"]
    assert body["graph_entity"]["display_name"] == "PARCEL-001"
    assert body["graph_related"][0]["entity"]["display_name"] == "Main Street Holdings"
