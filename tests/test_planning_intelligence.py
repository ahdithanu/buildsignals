from __future__ import annotations

from app.models.brand import BrandAlias, BrandProfile
from app.models.graph import GraphEntityLink, GraphRelationship, GraphRelationshipEvidence
from app.models.ingestion import PermitRecord
from app.models.planning import PlanningCompanyMatch, PlanningRecord


def _planning_source(csv_path: str) -> dict:
    fields = {
        "id": "source_record_id",
        "reference": "reference_number",
        "type": "event_type",
        "stage": "stage",
        "title": "title",
        "summary": "summary",
        "excerpt": "evidence_excerpt",
        "item": "agenda_item_number",
        "meeting": "meeting_name",
        "body": "governing_body",
        "project": "project_name",
        "address": "address",
        "city": "city",
        "state": "state",
        "parcel": "parcel_id",
        "applicant": "applicant_name",
        "meeting_at": "meeting_at",
        "published_at": "published_at",
        "url": "source_url",
    }
    return {
        "key": "test_city_agendas",
        "name": "Test City planning agendas",
        "adapter": "csv",
        "record_type": "planning",
        "jurisdiction": "Test City, TX",
        "base_url": csv_path,
        "settings": {"connector": {"page_size": 100}},
        "field_mappings": [
            {"source_field": source, "canonical_field": canonical}
            for source, canonical in fields.items()
        ],
    }


def test_planning_ingestion_detects_company_data_center_and_graph_evidence(client, db, tmp_path):
    brand = BrandProfile(
        organization_id="default-org",
        key="microsoft",
        name="Microsoft",
        normalized_name="microsoft",
        category="technology",
        scale="fortune_500",
        priority=5,
    )
    db.add(brand)
    db.flush()
    db.add(
        BrandAlias(
            organization_id="default-org",
            brand_id=brand.id,
            alias="Microsoft",
            normalized_alias="microsoft",
            confidence=1.0,
        )
    )
    db.commit()

    csv_path = tmp_path / "planning.csv"
    csv_path.write_text(
        "id,reference,type,stage,title,summary,excerpt,item,meeting,body,project,address,city,state,parcel,applicant,meeting_at,published_at,url\n"
        'A-17,,agenda_item,scheduled,"Microsoft data center development agreement",'
        '"Consider a tax incentive and rezoning for a new hyperscale data center campus",'
        '"Staff recommends setting a public hearing for the proposed cloud computing campus",'
        '17,"City Council Regular Meeting",City Council,"Project Meridian",'
        '"500 Innovation Way",Test City,TX,TX-8841,"Microsoft Corporation",'
        "2026-09-15T18:00:00Z,2026-08-22T12:00:00Z,https://example.test/agendas/A-17\n"
    )
    source = client.post("/ingestion/sources", json=_planning_source(str(csv_path)))
    assert source.status_code == 201, source.text

    canary = client.post(
        f"/ingestion/sources/{source.json()['id']}/canary", json={"sample_size": 10}
    )
    assert canary.status_code == 200, canary.text
    assert canary.json()["records_valid"] == 1
    assert canary.json()["approval_stages"] == {"scheduled": 1}

    run = client.post(f"/ingestion/sources/{source.json()['id']}/runs", json={"max_pages": 1})
    assert run.status_code == 201, run.text
    assert run.json()["records_inserted"] == 1
    assert run.json()["records_failed"] == 0

    record = db.query(PlanningRecord).one()
    assert record.stage == "scheduled"
    assert record.priority_score == 100
    assert set(record.signal_categories) == {
        "data_center",
        "economic_incentive",
        "land_use_action",
        "tracked_company",
        "parcel_locatable",
    }
    match = db.query(PlanningCompanyMatch).one()
    assert match.brand.name == "Microsoft"
    assert match.matched_field == "project_name" or match.matched_field == "title"
    assert match.confidence >= 0.95

    assert (
        db.query(GraphEntityLink)
        .filter(
            GraphEntityLink.record_type == "planning",
            GraphEntityLink.record_id == record.id,
        )
        .count()
        == 1
    )
    assert db.query(GraphRelationship).count() >= 2
    assert db.query(GraphRelationshipEvidence).count() >= 2

    response = client.get("/planning/events?category=data_center&minimum_priority=90")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["title"] == "Microsoft data center development agreement"
    assert len(body[0]["latest_raw_record"]["content_hash"]) == 64
    assert body[0]["company_matches"][0]["brand"]["name"] == "Microsoft"


def test_planning_ingestion_requires_title(client, db, tmp_path):
    csv_path = tmp_path / "planning.csv"
    csv_path.write_text(
        "id,reference,type,stage,title,summary,excerpt,item,meeting,body,project,address,city,state,parcel,applicant,meeting_at,published_at,url\n"
        "A-18,,minutes,discussed,,No title,,,,,,,,,,,,,\n"
    )
    source = client.post("/ingestion/sources", json=_planning_source(str(csv_path))).json()
    run = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert run.status_code == 201
    assert run.json()["records_failed"] == 1
    assert "does not contain a title" in run.json()["error_message"]
    assert db.query(PlanningRecord).count() == 0


def _permit_source(csv_path: str) -> dict:
    fields = {
        "id": "source_record_id",
        "application": "application_number",
        "permit": "permit_number",
        "description": "description",
        "address": "address",
        "city": "city",
        "state": "state",
        "url": "source_url",
    }
    return {
        "key": "test_city_permits",
        "name": "Test City permits",
        "adapter": "csv",
        "record_type": "permit",
        "jurisdiction": "Test City, TX",
        "base_url": csv_path,
        "settings": {"connector": {"page_size": 100}},
        "field_mappings": [
            {"source_field": source, "canonical_field": canonical}
            for source, canonical in fields.items()
        ],
    }


def _ingest_reference_pair(client, tmp_path, *, planning_city: str, permit_city: str, order: str):
    planning_path = tmp_path / "planning-reference.csv"
    planning_path.write_text(
        "id,reference,type,stage,title,summary,excerpt,item,meeting,body,project,address,city,state,parcel,applicant,meeting_at,published_at,url\n"
        f'ITEM-1,H23-014,agenda_item,scheduled,"Multifamily hearing",'
        f'"Permit H23-014 under review","Staff recommends approval",3.2,'
        f'"Planning Director Hearing",Planning Director,"Winchester Homes",'
        f'"741 South Winchester Boulevard",{planning_city},CA,,,2026-08-19T18:00:00Z,'
        f"2026-08-10T12:00:00Z,https://city.example.gov/agenda.pdf\n"
    )
    permit_path = tmp_path / "permit-reference.csv"
    permit_path.write_text(
        "id,application,permit,description,address,city,state,url\n"
        f'PERMIT-1,H23-014,,"264-unit multifamily building",'
        f'"741 South Winchester Boulevard",{permit_city},CA,'
        f"https://permits.example.gov/H23-014\n"
    )
    payloads = {
        "planning": _planning_source(str(planning_path)),
        "permit": _permit_source(str(permit_path)),
    }
    source_ids: dict[str, str] = {}
    for record_type in order.split("-"):
        response = client.post("/ingestion/sources", json=payloads[record_type])
        assert response.status_code == 201, response.text
        source_ids[record_type] = response.json()["id"]
        run = client.post(
            f"/ingestion/sources/{source_ids[record_type]}/runs",
            json={"max_pages": 1},
        )
        assert run.status_code == 201, run.text
        assert run.json()["records_failed"] == 0
    return source_ids


def _reference_relationships(db):
    return [
        relationship
        for relationship in db.query(GraphRelationship).all()
        if (relationship.attributes or {}).get("role") == "canonical_permit_reference_match"
    ]


def test_reference_scope_indexes_match_model_metadata():
    planning_indexes = {index.name for index in PlanningRecord.__table__.indexes}
    permit_indexes = {index.name for index in PermitRecord.__table__.indexes}

    assert "ix_planning_record_reference_scope" in planning_indexes
    assert {
        "ix_permit_record_application_scope",
        "ix_permit_record_number_scope",
    } <= permit_indexes


def test_planning_first_links_later_permit_with_provenance(client, db, tmp_path):
    _ingest_reference_pair(
        client,
        tmp_path,
        planning_city="San Jose",
        permit_city="San Jose",
        order="planning-permit",
    )

    planning = db.query(PlanningRecord).one()
    permit = db.query(PermitRecord).one()
    relationships = _reference_relationships(db)
    assert planning.reference_number == "H23-014"
    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.attributes == {
        "role": "canonical_permit_reference_match",
        "matched_reference": "H23-014",
        "planning_record_id": planning.id,
        "permit_record_id": permit.id,
    }
    assert relationship.confidence == planning.confidence
    assert relationship.created_at is not None
    assert relationship.last_verified_at is not None
    assert len(relationship.evidence) == 1
    evidence = relationship.evidence[0]
    assert evidence.source_url == "https://city.example.gov/agenda.pdf"
    assert evidence.confidence == planning.confidence
    assert evidence.observed_at == planning.published_at
    assert evidence.payload["content_hash"] == planning.latest_raw_record.content_hash
    assert evidence.payload["raw_record_id"] == planning.latest_raw_record_id
    assert evidence.payload["reference_number"] == "H23-014"
    assert evidence.payload["received_at"]


def test_permit_first_links_later_planning_idempotently(client, db, tmp_path):
    source_ids = _ingest_reference_pair(
        client,
        tmp_path,
        planning_city="San Jose",
        permit_city="San Jose",
        order="permit-planning",
    )
    first = _reference_relationships(db)
    assert len(first) == 1
    relationship_id = first[0].id
    evidence_id = first[0].evidence[0].id

    rerun = client.post(
        f"/ingestion/sources/{source_ids['planning']}/runs",
        json={"max_pages": 1},
    )
    assert rerun.status_code == 201, rerun.text
    db.expire_all()
    repeated = _reference_relationships(db)
    assert [(row.id, row.evidence[0].id) for row in repeated] == [(relationship_id, evidence_id)]


def test_exact_reference_does_not_link_across_cities(client, db, tmp_path):
    _ingest_reference_pair(
        client,
        tmp_path,
        planning_city="San Jose",
        permit_city="Santa Clara",
        order="planning-permit",
    )

    assert _reference_relationships(db) == []
