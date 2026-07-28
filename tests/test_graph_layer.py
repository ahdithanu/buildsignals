from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.brand import BrandProfile, PermitBrandMatch
from app.models.contact import Contact
from app.models.graph import (
    GraphEntity,
    GraphEntityAlias,
    GraphEntityType,
    GraphRelationship,
    GraphRelationshipEvidence,
)
from app.models.ingestion import IngestionRun, IngestionSource, PermitRecord, RawSourceRecord
from app.models.parcel import NearbyParcelCandidate, NearbyParcelSearch, ParcelRecord
from app.services.graph_service import normalize_address
from app.services.ingestion.service import _project_permit_to_graph


def _entity(client, **overrides):
    payload = {
        "entity_type": "developer",
        "display_name": "Acme Development LLC",
        "source_system": "official_registry",
        "source_id": "developer-100",
        "aliases": ["Acme Dev"],
        **overrides,
    }
    response = client.post("/graph/entities", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_entity_creation_deduplicates_source_identity_and_aliases(client, db):
    first = _entity(client)
    second = _entity(
        client,
        display_name="ACME DEVELOPMENT, INC.",
        aliases=["Acme Development Company"],
        confidence=0.8,
    )

    assert second["id"] == first["id"]
    assert db.query(GraphEntity).count() == 1
    aliases = {
        row.normalized_alias for row in db.query(GraphEntityAlias).all()
    }
    assert {"acme development", "acme dev"}.issubset(aliases)
    assert db.query(GraphEntity).one().confidence == 1.0


def test_property_resolution_uses_normalized_address(client, db):
    first = _entity(
        client,
        entity_type="property",
        display_name="Congress Retail Center",
        source_system=None,
        source_id=None,
        address="100 Congress Avenue",
        city="Austin",
        state="TX",
        zip_code="78701",
    )
    second = _entity(
        client,
        entity_type="property",
        display_name="Future Retail Site",
        source_system="assessor",
        source_id="parcel-100",
        address="100 Congress Ave.",
        city="Austin",
        state="TX",
        zip_code="78701",
    )

    assert second["id"] == first["id"]
    assert db.query(GraphEntity).count() == 1


def test_address_normalization_accepts_numeric_postal_codes():
    assert normalize_address("117 W Duval St", "Jacksonville", "FL", 32202) == (
        "117 w duval st jacksonville fl 32202"
    )


def test_official_parcel_ids_remain_distinct_at_a_shared_condo_address(client, db):
    first = _entity(
        client,
        entity_type="parcel",
        display_name="FOLIO-UNIT-101",
        source_system="county_assessor",
        source_id="folio-101",
        address="400 Market Street Unit 101",
        city="Miami",
        state="FL",
        zip_code="33131",
    )
    second = _entity(
        client,
        entity_type="parcel",
        display_name="FOLIO-UNIT-102",
        source_system="county_assessor",
        source_id="folio-102",
        address="400 Market Street Unit 101",
        city="Miami",
        state="FL",
        zip_code="33131",
    )
    repeated = _entity(
        client,
        entity_type="parcel",
        display_name="FOLIO-UNIT-101 UPDATED",
        source_system="county_assessor",
        source_id="folio-101",
        address="400 Market Street Unit 101",
        city="Miami",
        state="FL",
        zip_code="33131",
    )

    assert first["id"] != second["id"]
    assert repeated["id"] == first["id"]
    assert db.query(GraphEntity).count() == 2


def test_alias_source_identity_does_not_merge_different_entity_types(client, db):
    developer = _entity(
        client,
        entity_type="developer",
        display_name="Shared Name Development",
        source_system="permit_feed",
        source_id="party-42",
    )
    owner = _entity(
        client,
        entity_type="owner",
        display_name="Shared Name Owner",
        source_system="permit_feed",
        source_id="party-42",
    )

    assert developer["id"] != owner["id"]
    assert db.query(GraphEntity).count() == 2


def test_fuzzy_resolution_uses_name_blocking_beyond_first_page(client, db):
    for index in range(120):
        db.add(
            GraphEntity(
                organization_id="default-org",
                entity_type=GraphEntityType.developer,
                display_name=f"Seed Entity {index}",
                normalized_name=f"seed entity {index}",
                confidence=1.0,
            )
        )
    db.flush()
    target = _entity(
        client,
        display_name="Northstar Development Holdings",
        source_system=None,
        source_id=None,
    )
    duplicate = _entity(
        client,
        display_name="Northstar Developments Holding",
        source_system=None,
        source_id=None,
    )

    assert duplicate["id"] == target["id"]
    assert db.query(GraphEntity).count() == 121


@pytest.mark.parametrize(
    ("entity_type", "first_name", "duplicate_name"),
    [
        ("developer", "Summit Development Group LLC", "Summit Development Group, Inc."),
        ("owner", "Summit Property Holdings LLC", "Summit Property Holding, Inc."),
        ("general_contractor", "Crest Builders Group LLC", "Crest Builder Group Inc."),
        ("architect", "Horizon Design Studio LLC", "Horizon Design Studios, Inc."),
        ("engineer", "Northline Engineering Group LLC", "Northline Engineering Grp"),
    ],
)
def test_address_aware_core_roles_dedupe_on_normalized_address_and_name(
    client,
    db,
    entity_type,
    first_name,
    duplicate_name,
):
    first = _entity(
        client,
        entity_type=entity_type,
        display_name=first_name,
        source_system=None,
        source_id=None,
        address="500 Commerce Drive Suite 200",
        city="Austin",
        state="TX",
        zip_code="78701",
    )
    duplicate = _entity(
        client,
        entity_type=entity_type,
        display_name=duplicate_name,
        source_system="state_registry",
        source_id=f"{entity_type}-500",
        address="500 Commerce Dr. #200",
        city="Austin",
        state="TX",
        zip_code="78701",
    )

    assert duplicate["id"] == first["id"]
    assert db.query(GraphEntity).count() == 1


def test_relationship_upsert_preserves_evidence_and_supports_graph_queries(client, db):
    property_entity = _entity(
        client,
        entity_type="property",
        display_name="Main Street Site",
        source_system="assessor",
        source_id="parcel-200",
        address="200 Main Street",
        city="Austin",
        state="TX",
        zip_code="78701",
    )
    developer = _entity(client)
    payload = {
        "source_entity_id": property_entity["id"],
        "target_entity_id": developer["id"],
        "relationship_type": "developed_by",
        "confidence": 0.85,
        "source_system": "city_planning",
        "source_id": "case-22",
        "evidence": [{
            "source_system": "city_planning",
            "source_id": "filing-1",
            "source_url": "https://example.gov/planning/case-22",
            "evidence_type": "official_filing",
            "excerpt": "Developer: Acme Development LLC",
            "confidence": 0.85,
        }],
    }
    created = client.post("/graph/relationships", json=payload)
    assert created.status_code == 201, created.text
    relationship = created.json()
    assert relationship["created_at"]
    assert relationship["last_verified_at"]
    assert relationship["evidence"][0]["source_url"].startswith("https://")

    repeated = client.post("/graph/relationships", json={
        **payload,
        "confidence": 0.95,
        "evidence": [{
            **payload["evidence"][0],
            "confidence": 0.95,
        }],
    })
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["id"] == relationship["id"]
    assert repeated.json()["confidence"] == 0.95
    assert db.query(GraphRelationship).count() == 1
    assert db.query(GraphRelationshipEvidence).count() == 1

    detail = client.get(f"/graph/entities/{property_entity['id']}")
    assert detail.status_code == 200
    assert detail.json()["related"][0]["entity"]["id"] == developer["id"]
    related = client.get(f"/graph/entities/{property_entity['id']}/related")
    assert related.status_code == 200
    assert related.json()[0]["direction"] == "outgoing"
    paths = client.get("/graph/paths", params={
        "source_entity_id": property_entity["id"],
        "target_entity_id": developer["id"],
        "max_depth": 3,
    })
    assert paths.status_code == 200
    assert [entity["id"] for entity in paths.json()[0]["entities"]] == [
        property_entity["id"], developer["id"],
    ]
    assert paths.json()[0]["relationships"][0]["id"] == relationship["id"]


def test_relationship_requires_source_evidence(client):
    source = _entity(client, source_id="source")
    target = _entity(client, source_id="target", display_name="Other Developer")

    response = client.post("/graph/relationships", json={
        "source_entity_id": source["id"],
        "target_entity_id": target["id"],
        "relationship_type": "related_to",
        "evidence": [],
    })

    assert response.status_code == 422


def test_opportunity_graph_context_creates_a_linked_property_root(client):
    deal = client.post("/deals", json={
        "name": "Signal Site",
        "address": "300 Market Street",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
        "property_type": "retail",
    })
    assert deal.status_code == 201, deal.text

    context = client.get(f"/deals/{deal.json()['id']}/graph-context")

    assert context.status_code == 200, context.text
    assert context.json()["opportunity_id"] == deal.json()["id"]
    assert len(context.json()["root_entities"]) == 1
    assert context.json()["root_entities"][0]["entity_type"] == "property"


def test_graph_entity_search_matches_aliases_and_filters_type(client):
    developer = _entity(
        client,
        display_name="Acme Development Group",
        aliases=["Acme Dev Group"],
        source_system="registry",
        source_id="dev-1",
    )
    _entity(
        client,
        entity_type="owner",
        display_name="Acme Holdings",
        aliases=["Acme Dev Holdings"],
        source_system="registry",
        source_id="owner-1",
    )

    response = client.get("/graph/entities", params={"q": "Acme Dev Group"})
    assert response.status_code == 200, response.text
    assert response.json()[0]["id"] == developer["id"]
    assert "Acme Dev Group" in response.json()[0]["aliases"]

    filtered = client.get("/graph/entities", params={"q": "Acme", "entity_type": "owner"})
    assert filtered.status_code == 200, filtered.text
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["entity_type"] == "owner"


def test_graph_detail_related_entities_and_paths_are_exposed_via_api(client):
    property_entity = _entity(
        client,
        entity_type="property",
        display_name="Main Street Site",
        source_system="assessor",
        source_id="parcel-300",
        address="300 Main Street",
        city="Austin",
        state="TX",
        zip_code="78701",
        aliases=["300 Main St Site"],
    )
    developer = _entity(
        client,
        entity_type="developer",
        display_name="Acme Development LLC",
        source_system="official_registry",
        source_id="dev-300",
    )
    relationship = client.post("/graph/relationships", json={
        "source_entity_id": property_entity["id"],
        "target_entity_id": developer["id"],
        "relationship_type": "developed_by",
        "confidence": 0.91,
        "source_system": "city_planning",
        "source_id": "filing-300",
        "evidence": [{
            "source_system": "city_planning",
            "source_id": "filing-300-evidence",
            "source_url": "https://example.gov/planning/300",
            "evidence_type": "official_filing",
            "excerpt": "Developer: Acme Development LLC",
            "confidence": 0.91,
        }],
    })
    assert relationship.status_code == 201, relationship.text

    detail = client.get(f"/graph/entities/{property_entity['id']}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert "300 Main St Site" in body["aliases"]
    assert body["related"][0]["entity"]["id"] == developer["id"]
    assert body["related"][0]["relationship"]["evidence"][0]["source_id"] == "filing-300-evidence"

    related = client.get(f"/graph/entities/{property_entity['id']}/related")
    assert related.status_code == 200, related.text
    assert related.json()[0]["entity"]["id"] == developer["id"]
    assert related.json()[0]["direction"] == "outgoing"

    paths = client.get("/graph/paths", params={
        "source_entity_id": property_entity["id"],
        "target_entity_id": developer["id"],
        "max_depth": 3,
    })
    assert paths.status_code == 200, paths.text
    assert paths.json()[0]["entities"][0]["id"] == property_entity["id"]
    assert paths.json()[0]["entities"][1]["id"] == developer["id"]
    assert paths.json()[0]["relationships"][0]["id"] == relationship.json()["id"]


def test_related_entities_are_sorted_by_confidence_then_recency(client):
    property_entity = _entity(
        client,
        entity_type="property",
        display_name="Sort Test Site",
        source_system="assessor",
        source_id="parcel-sort-1",
        address="900 Market Street",
        city="Austin",
        state="TX",
        zip_code="78701",
    )
    lower = _entity(
        client,
        entity_type="developer",
        display_name="Lower Confidence Developer",
        source_system="official_registry",
        source_id="dev-sort-1",
    )
    higher = _entity(
        client,
        entity_type="developer",
        display_name="Higher Confidence Developer",
        source_system="official_registry",
        source_id="dev-sort-2",
    )

    first_rel = client.post("/graph/relationships", json={
        "source_entity_id": property_entity["id"],
        "target_entity_id": lower["id"],
        "relationship_type": "developed_by",
        "confidence": 0.75,
        "source_system": "city_planning",
        "source_id": "sort-1",
        "evidence": [{
            "source_system": "city_planning",
            "source_id": "sort-1-evidence",
            "excerpt": "Developer: Lower Confidence Developer",
            "confidence": 0.75,
        }],
    })
    assert first_rel.status_code == 201, first_rel.text

    second_rel = client.post("/graph/relationships", json={
        "source_entity_id": property_entity["id"],
        "target_entity_id": higher["id"],
        "relationship_type": "developed_by",
        "confidence": 0.97,
        "source_system": "city_planning",
        "source_id": "sort-2",
        "evidence": [{
            "source_system": "city_planning",
            "source_id": "sort-2-evidence",
            "excerpt": "Developer: Higher Confidence Developer",
            "confidence": 0.97,
        }],
    })
    assert second_rel.status_code == 201, second_rel.text

    detail = client.get(f"/graph/entities/{property_entity['id']}")
    assert detail.status_code == 200, detail.text
    related = detail.json()["related"]
    assert [row["entity"]["id"] for row in related][:2] == [higher["id"], lower["id"]]

    paths = client.get("/graph/paths", params={
        "source_entity_id": property_entity["id"],
        "target_entity_id": higher["id"],
        "max_depth": 2,
    })
    assert paths.status_code == 200, paths.text
    assert paths.json()[0]["entities"][1]["id"] == higher["id"]


def test_deal_graph_context_includes_related_graph_entities(client):
    deal = client.post("/deals", json={
        "name": "Signal Site Context",
        "address": "400 Market Street",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
        "property_type": "retail",
    })
    assert deal.status_code == 201, deal.text

    first_context = client.get(f"/deals/{deal.json()['id']}/graph-context")
    assert first_context.status_code == 200, first_context.text
    root_entity = first_context.json()["root_entities"][0]

    developer = _entity(
        client,
        entity_type="developer",
        display_name="Looped Development Partners",
        source_system="official_registry",
        source_id="dev-400",
    )
    company = _entity(
        client,
        entity_type="company",
        display_name="Looped Retail Group",
        source_system="brand_catalog",
        source_id="looped_retail_group",
    )
    rel = client.post("/graph/relationships", json={
        "source_entity_id": root_entity["id"],
        "target_entity_id": developer["id"],
        "relationship_type": "developed_by",
        "confidence": 0.88,
        "source_system": "permit_ingestion",
        "source_id": "permit-400",
        "evidence": [{
            "source_system": "permit_ingestion",
            "source_id": "permit-400-evidence",
            "excerpt": "Developer: Looped Development Partners",
            "confidence": 0.88,
        }],
    })
    assert rel.status_code == 201, rel.text
    company_rel = client.post("/graph/relationships", json={
        "source_entity_id": root_entity["id"],
        "target_entity_id": company["id"],
        "relationship_type": "related_to",
        "confidence": 0.93,
        "source_system": "permit_ingestion",
        "source_id": "permit-400-company",
        "evidence": [{
            "source_system": "permit_ingestion",
            "source_id": "permit-400-company-evidence",
            "excerpt": "Retail brand: Looped Retail Group",
            "confidence": 0.93,
        }],
    })
    assert company_rel.status_code == 201, company_rel.text

    context = client.get(f"/deals/{deal.json()['id']}/graph-context")
    assert context.status_code == 200, context.text
    body = context.json()
    assert body["opportunity_id"] == deal.json()["id"]
    assert body["root_entities"][0]["id"] == root_entity["id"]
    assert body["developers"][0]["entity"]["id"] == developer["id"]
    assert body["companies"][0]["entity"]["id"] == company["id"]


def test_deal_graph_context_includes_permit_brand_matches(client, db):
    deal = client.post("/deals", json={
        "name": "Signal Site Retail Match",
        "address": "800 Market Street",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
        "property_type": "retail",
    })
    assert deal.status_code == 201, deal.text

    first_context = client.get(f"/deals/{deal.json()['id']}/graph-context")
    assert first_context.status_code == 200, first_context.text

    source = IngestionSource(
        organization_id="default-org",
        key="graph-brand-source",
        name="Graph Brand Source",
        adapter="csv",
        record_type="permit",
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
        external_record_id="permit-brand-1",
        record_type="permit",
        content_hash="graph-brand-hash",
        payload={},
    )
    db.add(raw)
    db.flush()
    permit = PermitRecord(
        organization_id="default-org",
        source_id=source.id,
        latest_raw_record_id=raw.id,
        external_record_id="permit-brand-1",
        normalization_hash="graph-brand-hash",
        approval_stage="pre_approval",
        address="800 Market Street",
        city="Austin",
        state="TX",
    )
    db.add(permit)
    db.flush()
    brand = BrandProfile(
        organization_id="default-org",
        key="chipotle",
        name="Chipotle",
        normalized_name="chipotle",
        priority=5,
        is_active=True,
    )
    db.add(brand)
    db.flush()
    db.add(PermitBrandMatch(
        organization_id="default-org",
        permit_id=permit.id,
        brand_id=brand.id,
        first_raw_record_id=raw.id,
        latest_raw_record_id=raw.id,
        review_status="candidate",
        confidence=0.94,
        matched_alias="Chipotle",
        matched_field="description",
        matched_fields=["description"],
        rule_ids=["pre_approval"],
        excerpt="Chipotle tenant improvement filing",
        detector_version="brand-alias-v1",
    ))
    db.commit()

    _project_permit_to_graph(db, source, permit, raw)
    db.commit()

    context = client.get(f"/deals/{deal.json()['id']}/graph-context")
    assert context.status_code == 200, context.text
    body = context.json()
    assert body["permit_brand_matches"][0]["brand"]["name"] == "Chipotle"
    assert body["permit_brand_matches"][0]["permit"]["approval_stage"] == "pre_approval"
    assert body["permit_brand_matches"][0]["signal_quality"] == "description_context"


def test_deal_graph_context_reports_nearby_parcel_search_count(client, db):
    deal = client.post("/deals", json={
        "name": "Signal Site Parcel Context",
        "address": "500 Market Street",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
        "property_type": "retail",
    })
    assert deal.status_code == 201, deal.text

    source = IngestionSource(
        organization_id="default-org",
        key="graph-parcel-source",
        name="Graph Parcel Source",
        adapter="csv",
        record_type="permit",
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
        external_record_id="permit-graph-1",
        record_type="permit",
        content_hash="graph-parcel-hash",
        payload={},
    )
    db.add(raw)
    db.flush()
    permit = PermitRecord(
        organization_id="default-org",
        source_id=source.id,
        latest_raw_record_id=raw.id,
        external_record_id="permit-graph-1",
        normalization_hash="graph-parcel-hash",
        approval_stage="approved",
    )
    db.add(permit)
    db.flush()
    db.add(NearbyParcelSearch(
        organization_id="default-org",
        deal_id=deal.json()["id"],
        anchor_permit_id=permit.id,
        anchor_latitude=30.2672,
        anchor_longitude=-97.7431,
        radius_miles=2.0,
        persona="developer",
        filters={},
        result_limit=25,
        as_of=datetime.now(timezone.utc),
        ranker_version="developer-v2",
    ))
    db.commit()

    context = client.get(f"/deals/{deal.json()['id']}/graph-context")
    assert context.status_code == 200, context.text
    assert context.json()["nearby_parcel_searches"] == 1
    assert context.json()["buyer_lenses"][0]["persona"] == "developer"


def test_deal_graph_context_reports_buyer_lenses(client, db):
    deal = client.post("/deals", json={
        "name": "Signal Site Buyer Lenses",
        "address": "600 Market Street",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
        "property_type": "retail",
    })
    assert deal.status_code == 201, deal.text

    source = IngestionSource(
        organization_id="default-org",
        key="graph-lens-source",
        name="Graph Lens Source",
        adapter="csv",
        record_type="permit",
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
        external_record_id="permit-graph-2",
        record_type="permit",
        content_hash="graph-lens-hash",
        payload={},
    )
    db.add(raw)
    db.flush()
    permit = PermitRecord(
        organization_id="default-org",
        source_id=source.id,
        latest_raw_record_id=raw.id,
        external_record_id="permit-graph-2",
        normalization_hash="graph-lens-hash",
        approval_stage="approved",
    )
    db.add(permit)
    db.flush()
    shared_parcel = ParcelRecord(
        organization_id="default-org",
        source_id=source.id,
        latest_raw_record_id=raw.id,
        external_parcel_id="SHARED-PARCEL",
        jurisdiction="Austin",
        county="Travis",
        state="TX",
        address="10 Shared Way",
        city="Austin",
        postal_code="78701",
        latitude=30.2672,
        longitude=-97.7431,
        land_area_sq_ft=80000,
        land_value=1000000,
        improvement_value=100000,
        last_verified_at=datetime.now(timezone.utc),
    )
    db.add(shared_parcel)
    db.flush()
    for persona, radius in [("developer", 2.0), ("broker", 1.5), ("realtor", 1.0), ("developer", 2.5)]:
        search = NearbyParcelSearch(
            organization_id="default-org",
            deal_id=deal.json()["id"],
            anchor_permit_id=permit.id,
            anchor_latitude=30.2672,
            anchor_longitude=-97.7431,
            radius_miles=radius,
            persona=persona,
            filters={},
            result_limit=25,
            as_of=datetime.now(timezone.utc),
            ranker_version=f"{persona}-v2",
        )
        db.add(search)
        db.flush()
        db.add(NearbyParcelCandidate(
            organization_id="default-org",
            search_id=search.id,
            parcel_id=shared_parcel.id,
            rank=1,
            distance_miles=1.25,
            score=82.5,
            score_confidence=0.9,
            explanation={"reasons": [f"{persona} fit"]},
            review_status="candidate",
            ranker_version=f"{persona}-v2",
        ))
    db.commit()

    context = client.get(f"/deals/{deal.json()['id']}/graph-context")
    assert context.status_code == 200, context.text
    body = context.json()
    assert body["nearby_parcel_searches"] == 4
    assert {row["persona"] for row in body["buyer_lenses"]} == {"developer", "broker", "realtor"}
    developer = next(row for row in body["buyer_lenses"] if row["persona"] == "developer")
    assert developer["search_count"] == 2
    assert developer["latest_radius_miles"] == 2.5
    assert developer["top_parcels"][0]["external_parcel_id"] == "SHARED-PARCEL"
    assert body["shared_parcels"][0]["external_parcel_id"] == "SHARED-PARCEL"
    assert body["shared_parcels"][0]["lens_count"] == 3
    assert body["shared_parcels"][0]["best_persona"] in {"developer", "broker", "realtor"}


def test_deal_graph_context_backfills_existing_contacts_into_graph(client, db):
    deal = client.post("/deals", json={
        "name": "Signal Site Contacts Backfill",
        "address": "700 Market Street",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
        "property_type": "retail",
    })
    assert deal.status_code == 201, deal.text

    db.add(Contact(
        organization_id="default-org",
        deal_id=deal.json()["id"],
        name="Jordan Capital",
        role="Lender",
        company="Jordan Capital Partners",
        email="jordan@example.com",
    ))
    db.commit()

    context = client.get(f"/deals/{deal.json()['id']}/graph-context")
    assert context.status_code == 200, context.text
    body = context.json()
    assert body["lenders"][0]["entity"]["display_name"] == "Jordan Capital Partners"
    assert body["lenders"][0]["relationship"]["relationship_type"] == "financed_by"
