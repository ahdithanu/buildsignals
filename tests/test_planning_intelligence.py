from __future__ import annotations

from app.models.brand import BrandAlias, BrandProfile
from app.models.graph import GraphEntityLink, GraphRelationship, GraphRelationshipEvidence
from app.models.ingestion import IngestionSource, PermitRecord, RecordExternalReference
from app.models.planning import PlanningCompanyMatch, PlanningRecord
from app.services.ingestion.service import backfill_external_references_batch


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


def test_planning_company_appears_in_expansion_before_permit(client, db, tmp_path):
    brand = BrandProfile(
        organization_id="default-org",
        key="early_retailer",
        name="Early Retailer",
        normalized_name="early retailer",
        category="retail",
        scale="national",
        priority=5,
        attributes={"signal_cohort": "national_retail"},
    )
    db.add(brand)
    db.flush()
    db.add(
        BrandAlias(
            organization_id="default-org",
            brand_id=brand.id,
            alias="Early Retailer",
            normalized_alias="early retailer",
            confidence=1.0,
        )
    )
    db.commit()

    csv_path = tmp_path / "early-retailer-planning.csv"
    csv_path.write_text(
        "id,reference,type,stage,title,summary,excerpt,item,meeting,body,project,address,city,state,parcel,applicant,meeting_at,published_at,url\n"
        'A-20,,agenda_item,scheduled,"Early Retailer site plan hearing",'
        '"Conditional use review for a new location","Staff review is pending",'
        '20,"Planning Commission",Planning Commission,"Early Retailer",'
        '"100 Market Street",Austin,TX,TX-100,"Early Retailer",'
        "2026-09-15T18:00:00Z,2026-08-22T12:00:00Z,https://example.test/agendas/A-20\n"
    )
    source = client.post("/ingestion/sources", json=_planning_source(str(csv_path))).json()
    run = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert run.status_code == 201, run.text

    response = client.get("/brand-expansion?days=365&cohort=national_retail")
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result) == 1
    assert result[0]["brand"]["key"] == "early_retailer"
    assert result[0]["signal_count"] == 1
    assert result[0]["planning_count"] == 1
    assert result[0]["pre_approval_count"] == 0
    assert result[0]["approved_count"] == 0
    assert result[0]["markets"][0]["planning_count"] == 1

    filtered = client.get(f"/planning/events?brand_id={brand.id}")
    assert filtered.status_code == 200, filtered.text
    assert [record["external_record_id"] for record in filtered.json()] == ["A-20"]

    unrelated = client.get("/planning/events?brand_id=00000000-0000-0000-0000-000000000000")
    assert unrelated.status_code == 200, unrelated.text
    assert unrelated.json() == []


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


def _ingest_external_reference_pair(
    client, tmp_path, *, order: str, configure_references: bool = True
):
    planning_path = tmp_path / "planning-external-reference.csv"
    planning_path.write_text(
        "id,reference,matter_id,type,stage,title,summary,excerpt,item,meeting,body,project,address,city,state,parcel,applicant,meeting_at,published_at,url\n"
        'ITEM-EXT,AGENDA-99,155772,agenda_item,scheduled,"Project hearing",'
        '"Official legislative matter","Staff report",9,"Plan Commission",'
        '"Plan Commission","Project North","100 Main Street",Madison,WI,,,'
        "2026-09-01T18:00:00Z,2026-08-25T12:00:00Z,"
        "https://madison.legistar.com/LegislationDetail.aspx?ID=155772\n"
    )
    permit_path = tmp_path / "permit-external-reference.csv"
    permit_path.write_text(
        "id,application,permit,description,address,city,state,url,legislative_url\n"
        'PROJECT-EXT,LNDUSE-2026-1,,"Current planning project",'
        '"100 Main Street",Madison,WI,https://city.example.gov/projects/PROJECT-EXT,'
        "https://madison.legistar.com/LegislationDetail.aspx?ID=155772\n"
    )
    planning_source = _planning_source(str(planning_path))
    planning_extractors = [
        {
            "source_field": "matter_id",
            "namespace": "legistar:madison:legislation",
            "transform": "scalar",
        }
    ]
    permit_source = _permit_source(str(permit_path))
    permit_extractors = [
        {
            "source_field": "legislative_url",
            "namespace": "legistar:madison:legislation",
            "transform": "url_query_parameter",
            "parameter": "ID",
            "allowed_hosts": ["madison.legistar.com"],
        }
    ]
    if configure_references:
        planning_source["settings"]["external_reference_extractors"] = planning_extractors
        permit_source["settings"]["external_reference_extractors"] = permit_extractors
    payloads = {"planning": planning_source, "permit": permit_source}
    source_ids = {}
    for record_type in order.split("-"):
        source = client.post("/ingestion/sources", json=payloads[record_type])
        assert source.status_code == 201, source.text
        source_ids[record_type] = source.json()["id"]
        run = client.post(
            f"/ingestion/sources/{source_ids[record_type]}/runs",
            json={"max_pages": 1},
        )
        assert run.status_code == 201, run.text
        assert run.json()["records_failed"] == 0
    return source_ids


def _external_reference_relationships(db):
    return [
        relationship
        for relationship in db.query(GraphRelationship).all()
        if (relationship.attributes or {}).get("role") == "official_external_reference_match"
    ]


def test_planning_first_links_project_by_configured_official_reference(client, db, tmp_path):
    _ingest_external_reference_pair(client, tmp_path, order="planning-permit")

    references = db.query(RecordExternalReference).all()
    assert {(row.record_type, row.namespace, row.normalized_value) for row in references} == {
        ("planning", "legistar:madison:legislation", "155772"),
        ("permit", "legistar:madison:legislation", "155772"),
    }
    relationships = _external_reference_relationships(db)
    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.attributes["matched_reference"] == "155772"
    assert relationship.attributes["reference_namespace"] == "legistar:madison:legislation"
    assert relationship.created_at is not None
    assert relationship.last_verified_at is not None
    evidence = relationship.evidence[0]
    assert evidence.evidence_type == "official_external_reference_match"
    assert evidence.payload["planning_reference_field"] == "matter_id"
    assert evidence.payload["permit_reference_field"] == "legislative_url"
    assert evidence.payload["permit_reference_raw_record_id"]


def test_permit_first_external_reference_join_is_idempotent(client, db, tmp_path):
    source_ids = _ingest_external_reference_pair(client, tmp_path, order="permit-planning")
    first = _external_reference_relationships(db)
    assert len(first) == 1
    relationship_id = first[0].id
    evidence_id = first[0].evidence[0].id

    rerun = client.post(
        f"/ingestion/sources/{source_ids['permit']}/runs",
        json={"max_pages": 1},
    )
    assert rerun.status_code == 201, rerun.text
    db.expire_all()
    repeated = _external_reference_relationships(db)
    assert [(row.id, row.evidence[0].id) for row in repeated] == [(relationship_id, evidence_id)]


def test_corrected_external_reference_retires_stale_graph_link(client, db, tmp_path):
    source_ids = _ingest_external_reference_pair(client, tmp_path, order="planning-permit")
    relationship = _external_reference_relationships(db)[0]
    assert relationship.is_current is True

    permit_path = tmp_path / "permit-external-reference.csv"
    permit_path.write_text(
        "id,application,permit,description,address,city,state,url,legislative_url\n"
        'PROJECT-EXT,LNDUSE-2026-1,,"Current planning project",'
        '"100 Main Street",Madison,WI,https://city.example.gov/projects/PROJECT-EXT,'
        "https://madison.legistar.com/LegislationDetail.aspx?ID=999999\n"
    )
    rerun = client.post(
        f"/ingestion/sources/{source_ids['permit']}/runs",
        json={"max_pages": 1},
    )
    assert rerun.status_code == 201, rerun.text
    db.expire_all()

    corrected = db.query(RecordExternalReference).filter_by(record_type="permit").one()
    assert corrected.normalized_value == "999999"
    stale = db.query(GraphRelationship).filter_by(id=relationship.id).one()
    assert stale.is_current is False
    assert stale.valid_to is not None


def test_bounded_backfill_indexes_existing_records_without_refetching(client, db, tmp_path):
    source_ids = _ingest_external_reference_pair(
        client,
        tmp_path,
        order="permit-planning",
        configure_references=False,
    )
    assert db.query(RecordExternalReference).count() == 0
    assert _external_reference_relationships(db) == []

    planning_source = db.query(IngestionSource).filter_by(id=source_ids["planning"]).one()
    planning_source.settings = {
        **(planning_source.settings or {}),
        "external_reference_extractors": [
            {
                "source_field": "matter_id",
                "namespace": "legistar:madison:legislation",
                "transform": "scalar",
            }
        ],
    }
    permit_source = db.query(IngestionSource).filter_by(id=source_ids["permit"]).one()
    permit_source.settings = {
        **(permit_source.settings or {}),
        "external_reference_extractors": [
            {
                "source_field": "legislative_url",
                "namespace": "legistar:madison:legislation",
                "transform": "url_query_parameter",
                "parameter": "ID",
                "allowed_hosts": ["madison.legistar.com"],
            }
        ],
    }
    db.commit()

    permit_result = backfill_external_references_batch(
        db,
        record_type="permit",
        source_key=permit_source.key,
        batch_size=1,
    )
    planning_result = backfill_external_references_batch(
        db,
        record_type="planning",
        source_key=planning_source.key,
        batch_size=1,
    )
    db.commit()

    assert permit_result.scanned == permit_result.references_created == 1
    assert permit_result.references_removed == 0
    assert permit_result.records_linked == 0
    assert planning_result.scanned == planning_result.references_created == 1
    assert planning_result.records_linked == 1
    assert len(_external_reference_relationships(db)) == 1

    repeated = backfill_external_references_batch(
        db,
        record_type="planning",
        source_key=planning_source.key,
        batch_size=1,
    )
    assert repeated.references_created == 0
    assert repeated.references_refreshed == 1
    assert repeated.references_removed == 0
    assert repeated.records_linked == 1
    assert len(_external_reference_relationships(db)) == 1
