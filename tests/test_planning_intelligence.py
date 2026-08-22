from __future__ import annotations

from app.models.brand import BrandAlias, BrandProfile
from app.models.graph import GraphEntityLink, GraphRelationship, GraphRelationshipEvidence
from app.models.planning import PlanningCompanyMatch, PlanningRecord


def _planning_source(csv_path: str) -> dict:
    fields = {
        "id": "source_record_id",
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
        "id,type,stage,title,summary,excerpt,item,meeting,body,project,address,city,state,parcel,applicant,meeting_at,published_at,url\n"
        'A-17,agenda_item,scheduled,"Microsoft data center development agreement",'
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
        "id,type,stage,title,summary,excerpt,item,meeting,body,project,address,city,state,parcel,applicant,meeting_at,published_at,url\n"
        "A-18,minutes,discussed,,No title,,,,,,,,,,,,,\n"
    )
    source = client.post("/ingestion/sources", json=_planning_source(str(csv_path))).json()
    run = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert run.status_code == 201
    assert run.json()["records_failed"] == 1
    assert "does not contain a title" in run.json()["error_message"]
    assert db.query(PlanningRecord).count() == 0
