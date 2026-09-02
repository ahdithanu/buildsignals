from __future__ import annotations

from datetime import datetime, timedelta, timezone

import app.services.ingestion.service as ingestion_service
from app.models.brand import BrandAlias, BrandPartyFingerprint, BrandProfile, PermitBrandMatch
from app.models.graph import GraphEntity, GraphRelationship, GraphRelationshipEvidence
from app.models.ingestion import PermitRecord
from app.models.parcel import NearbyParcelSearch
from app.models.signal import Signal
from app.services.brand_intelligence import load_brand_catalog, sync_brand_catalog
from app.services.ingestion.catalog import load_catalog
from app.services.ingestion.connectors import FetchEnvelope
from app.services.ingestion.service import _project_permit_to_graph


class _StaticConnector:
    def __init__(self, records):
        self.records = records

    def fetch_page(self, checkpoint=None):
        return FetchEnvelope(
            source="test",
            records=tuple(self.records),
            checkpoint=None,
            has_more=False,
            metadata={},
        )


def _source_payload(
    csv_path: str,
    key: str = "retail_filings",
    *,
    applicant_semantics: str = "legal_entity",
) -> dict:
    fields = {
        "id": "source_record_id",
        "application_no": "application_number",
        "stage": "approval_stage",
        "type": "permit_type",
        "status": "status",
        "project": "project_name",
        "description": "description",
        "address": "address",
        "city": "city",
        "state": "state",
        "parcel": "parcel_id",
        "filed": "filed_at",
        "applicant": "applicant_name",
        "contractor": "contractor_name",
        "architect": "architect_name",
    }
    return {
        "key": key,
        "name": "Retail filing test source",
        "adapter": "csv",
        "record_type": "permit",
        "jurisdiction": "Austin, TX",
        "base_url": csv_path,
        "settings": {"connector": {"page_size": 100}},
        "field_mappings": [
            {
                "source_field": source,
                "canonical_field": canonical,
                **(
                    {"value_semantics": applicant_semantics}
                    if canonical == "applicant_name"
                    else {}
                ),
            }
            for source, canonical in fields.items()
        ],
    }


def _write_filing(
    path,
    *,
    project: str = "Coffee tenant improvement",
    description: str = "Interior retail build-out for Starbucks Coffee",
    owner: str = "",
    applicant: str = "",
    contractor: str = "",
    architect: str = "",
    stage: str = "pre_approval",
) -> None:
    path.write_text(
        "id,application_no,stage,type,status,project,description,address,city,state,parcel,filed,owner,applicant,contractor,architect\n"
        f'1,APP-1,{stage},Commercial Retail,Under Review,"{project}","{description}",100 Main St,Austin,TX,P-1,2026-07-01,"{owner}","{applicant}","{contractor}","{architect}"\n'
    )


def _ingest(client, csv_path, key: str = "retail_filings"):
    source = client.post("/ingestion/sources", json=_source_payload(str(csv_path), key=key))
    assert source.status_code == 201, source.text
    run = client.post(f"/ingestion/sources/{source.json()['id']}/runs", json={"max_pages": 1})
    assert run.status_code == 201, run.text
    return run.json()


def _catalog_source_payload(key: str) -> dict:
    entry = next(entry for entry in load_catalog() if entry.key == key)
    return entry.model_dump(mode="json")


def test_brand_catalog_sync_is_idempotent(db):
    entries = load_brand_catalog()
    first = sync_brand_catalog(db, entries)
    db.commit()
    brand_ids = {brand.key: brand.id for brand in db.query(BrandProfile).all()}
    alias_count = db.query(BrandAlias).count()

    second = sync_brand_catalog(db, entries)
    db.commit()

    expected_profiles = len(entries)
    expected_aliases = sum(len(entry.aliases) for entry in entries)
    assert first.created == expected_profiles
    assert second.unchanged == expected_profiles
    assert {brand.key: brand.id for brand in db.query(BrandProfile).all()} == brand_ids
    assert db.query(BrandAlias).count() == alias_count == expected_aliases


def test_preapproval_brand_match_is_evidence_backed_and_reviewable(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    deal = client.post("/deals", json={
        "name": "Main Street Retail",
        "address": "100 Main St",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
        "property_type": "retail",
    })
    assert deal.status_code == 201, deal.text
    csv_path = tmp_path / "starbucks.csv"
    _write_filing(csv_path)

    _ingest(client, csv_path)

    match = db.query(PermitBrandMatch).one()
    assert match.brand.key == "starbucks"
    assert match.matched_field == "description"
    assert match.confidence == 0.92
    assert match.detector_version == "brand-alias-v2"
    assert "Starbucks" in match.excerpt
    assert match.first_raw_record_id == match.latest_raw_record_id
    company = db.query(GraphEntity).filter(GraphEntity.entity_type == "company").one()
    assert company.display_name == "Starbucks"
    relationship = db.query(GraphRelationship).filter(
        GraphRelationship.attributes["brand_match_id"].as_string() == match.id
    ).one()
    assert relationship.is_current is True
    assert db.query(GraphRelationshipEvidence).filter(
        GraphRelationshipEvidence.relationship_id == relationship.id
    ).count() == 1

    listed = client.get("/permit-brand-matches?approval_stage=pre_approval")
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["brand"]["name"] == "Starbucks"
    assert listed.json()[0]["permit"]["application_number"] == "APP-1"
    assert listed.json()[0]["signal_quality"] == "description_context"
    assert listed.json()[0]["freshness"] in {"fresh", "active", "aging", "stale"}
    assert listed.json()[0]["signal_age_days"] >= 0
    assert listed.json()[0]["freshness_date"]
    assert listed.json()[0]["linked_deals"] == [{
        "id": deal.json()["id"],
        "name": "Main Street Retail",
    }]
    deal_matches = client.get(
        f"/deals/{deal.json()['id']}/permit-brand-matches"
    )
    assert deal_matches.status_code == 200, deal_matches.text
    assert [row["brand"]["key"] for row in deal_matches.json()] == ["starbucks"]

    dismissed = client.patch(
        f"/permit-brand-matches/{match.id}", json={"review_status": "dismissed"}
    )
    assert dismissed.status_code == 200, dismissed.text
    db.expire_all()
    assert db.query(PermitBrandMatch).one().review_status == "dismissed"
    assert db.query(GraphRelationship).filter(
        GraphRelationship.attributes["brand_match_id"].as_string() == match.id
    ).one().is_current is False


def test_review_queue_ranks_recent_source_activity_before_confidence(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    old_path = tmp_path / "old-brand.csv"
    recent_path = tmp_path / "recent-brand.csv"
    _write_filing(old_path)
    _write_filing(recent_path)
    _ingest(client, old_path, key="old_brand_signal")
    _ingest(client, recent_path, key="recent_brand_signal")

    permits = {permit.source.key: permit for permit in db.query(PermitRecord).all()}
    old_permit = permits["old_brand_signal"]
    recent_permit = permits["recent_brand_signal"]
    old_permit.filed_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    recent_permit.filed_at = datetime.now(timezone.utc) - timedelta(days=7)
    old_match = db.query(PermitBrandMatch).filter_by(permit_id=old_permit.id).one()
    recent_match = db.query(PermitBrandMatch).filter_by(permit_id=recent_permit.id).one()
    old_match.confidence = 0.99
    recent_match.confidence = 0.70
    db.commit()

    response = client.get(
        "/permit-brand-matches?review_status=candidate&sort_by=freshness"
    )

    assert response.status_code == 200, response.text
    assert [row["permit_id"] for row in response.json()] == [recent_permit.id, old_permit.id]
    assert response.json()[0]["freshness"] == "fresh"
    assert response.json()[1]["freshness"] == "stale"

    fresh_only = client.get("/permit-brand-matches?freshness=fresh")
    assert fresh_only.status_code == 200, fresh_only.text
    assert [row["permit_id"] for row in fresh_only.json()] == [recent_permit.id]

    recent_permit.filed_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
    db.commit()
    future_dated = client.get("/permit-brand-matches?freshness=fresh")
    assert future_dated.status_code == 200, future_dated.text
    future_row = next(
        row for row in future_dated.json() if row["permit_id"] == recent_permit.id
    )
    assert not future_row["freshness_date"].startswith("2099-")


def test_brand_expansion_ranks_active_signals_by_stage_and_market(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    for key in ("starbucks_early", "starbucks_approved", "starbucks_dismissed"):
        csv_path = tmp_path / f"{key}.csv"
        _write_filing(csv_path)
        _ingest(client, csv_path, key=key)

    builder_path = tmp_path / "toll_brothers.csv"
    _write_filing(
        builder_path,
        project="Toll Brothers residential subdivision",
        description="Site development for a new single-family subdivision",
        applicant="Toll Brothers",
    )
    _ingest(client, builder_path, key="toll_brothers_builder")

    approved = db.query(PermitRecord).filter(
        PermitRecord.source.has(key="starbucks_approved")
    ).one()
    approved.approval_stage = "approved"
    dismissed = db.query(PermitBrandMatch).join(PermitRecord).filter(
        PermitRecord.source.has(key="starbucks_dismissed")
    ).one()
    dismissed.review_status = "dismissed"
    db.commit()

    response = client.get("/brand-expansion?days=365&limit=10")

    assert response.status_code == 200, response.text
    starbucks = next(row for row in response.json() if row["brand"]["key"] == "starbucks")
    assert starbucks["signal_count"] == 2
    assert starbucks["pre_approval_count"] == 1
    assert starbucks["approved_count"] == 1
    assert starbucks["market_count"] == 1
    assert starbucks["parcel_candidate_count"] == 0
    assert starbucks["brand"]["signal_cohort"] == "national_retail"
    assert starbucks["markets"] == [
        {
            "city": "Austin",
            "state": "TX",
            "signal_count": 2,
            "planning_count": 0,
            "pre_approval_count": 1,
            "approved_count": 1,
            "latest_signal_at": starbucks["markets"][0]["latest_signal_at"],
        }
    ]

    filtered = client.get(f"/permit-brand-matches?brand_id={starbucks['brand']['id']}")
    assert filtered.status_code == 200, filtered.text
    assert {row["brand"]["key"] for row in filtered.json()} == {"starbucks"}

    builder_response = client.get(
        "/brand-expansion?days=365&limit=10&cohort=major_builder"
    )
    assert builder_response.status_code == 200, builder_response.text
    assert [row["brand"]["key"] for row in builder_response.json()] == [
        "toll_brothers"
    ]
    assert builder_response.json()[0]["pre_approval_count"] == 1

    builder_matches = client.get("/permit-brand-matches?cohort=major_builder")
    assert builder_matches.status_code == 200, builder_matches.text
    assert [row["brand"]["key"] for row in builder_matches.json()] == [
        "toll_brothers"
    ]

    invalid_response = client.get("/brand-expansion?cohort=technology")
    assert invalid_response.status_code == 422


def test_applicant_company_alias_is_high_confidence_direct_evidence(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    csv_path = tmp_path / "applicant-brand.csv"
    _write_filing(
        csv_path,
        project="Confidential tenant improvement",
        description="Commercial retail tenant build out",
        applicant="Starbucks Coffee Company",
    )

    _ingest(client, csv_path, key="applicant_brand")

    match = db.query(PermitBrandMatch).one()
    assert match.brand.key == "starbucks"
    assert match.matched_field == "applicant_name"
    assert match.matched_fields == ["applicant_name"]
    assert match.confidence == 0.92
    assert "Starbucks" in match.excerpt
    assert "exact_alias" in match.rule_ids
    assert "exact_applicant_alias" in match.rule_ids
    response = client.get("/permit-brand-matches?detection_method=direct_alias")
    assert response.status_code == 200, response.text
    assert response.json()[0]["signal_quality"] == "applicant_legal_entity"
    assert response.json()[0]["signal_quality_label"] == "Applicant legal entity"
    assert response.json()[0]["detection_method"] == "direct_alias"
    assert response.json()[0]["permit"]["applicant_name"] == "Starbucks Coffee Company"

    evidence = client.get(f"/permit-brand-matches/{match.id}/evidence")
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["matched_field"] == "applicant_name"
    assert evidence.json()["signal_quality"] == "applicant_legal_entity"
    assert evidence.json()["permit"]["applicant_name"] == "Starbucks Coffee Company"
    assert evidence.json()["latest_evidence"]["payload_excerpt"]["applicant"] == "Starbucks Coffee Company"


def test_applicant_alias_in_negative_context_does_not_create_candidate(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    csv_path = tmp_path / "former-applicant-brand.csv"
    _write_filing(
        csv_path,
        project="Confidential tenant improvement",
        description="Commercial retail tenant build out",
        applicant="Formerly Starbucks Coffee Company",
    )

    _ingest(client, csv_path, key="former_applicant_brand")

    assert db.query(PermitBrandMatch).count() == 0


def test_person_semantic_suppresses_applicant_brand_match(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    csv_path = tmp_path / "person-applicant-brand.csv"
    _write_filing(
        csv_path,
        project="Confidential tenant improvement",
        description="Commercial retail tenant build out",
        applicant="Starbucks Coffee Company",
    )
    payload = _source_payload(
        str(csv_path),
        key="person_applicant_brand",
        applicant_semantics="person",
    )
    source = client.post("/ingestion/sources", json=payload)
    assert source.status_code == 201, source.text
    run = client.post(f"/ingestion/sources/{source.json()['id']}/runs", json={"max_pages": 1})
    assert run.status_code == 201, run.text

    assert db.query(PermitBrandMatch).count() == 0


def test_unknown_applicant_semantic_is_supporting_only(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    csv_path = tmp_path / "mixed-applicant-brand.csv"
    _write_filing(
        csv_path,
        project="Confidential tenant improvement",
        description="Commercial retail tenant build out",
        applicant="Starbucks Coffee Company",
    )
    payload = _source_payload(
        str(csv_path),
        key="unknown_applicant_brand",
        applicant_semantics="unknown",
    )
    source = client.post("/ingestion/sources", json=payload)
    assert source.status_code == 201, source.text
    run = client.post(f"/ingestion/sources/{source.json()['id']}/runs", json={"max_pages": 1})
    assert run.status_code == 201, run.text

    assert db.query(PermitBrandMatch).count() == 0


def test_applicant_semantic_reclassification_retracts_stale_candidate(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    csv_path = tmp_path / "reclassified-applicant-brand.csv"
    _write_filing(
        csv_path,
        project="Confidential tenant improvement",
        description="Commercial retail tenant build out",
        applicant="Starbucks Coffee Company",
    )
    source_payload = _source_payload(str(csv_path), key="reclassified_applicant_brand")
    source = client.post("/ingestion/sources", json=source_payload)
    assert source.status_code == 201, source.text
    source_id = source.json()["id"]
    first_run = client.post(f"/ingestion/sources/{source_id}/runs", json={"max_pages": 1})
    assert first_run.status_code == 201, first_run.text
    assert db.query(PermitBrandMatch).one().review_status == "candidate"

    unknown_mappings = _source_payload(
        str(csv_path),
        key="reclassified_applicant_brand",
        applicant_semantics="unknown",
    )["field_mappings"]
    updated = client.patch(
        f"/ingestion/sources/{source_id}",
        json={"field_mappings": unknown_mappings},
    )
    assert updated.status_code == 200, updated.text
    second_run = client.post(f"/ingestion/sources/{source_id}/runs", json={"max_pages": 1})
    assert second_run.status_code == 201, second_run.text

    db.expire_all()
    assert db.query(PermitBrandMatch).one().review_status == "retracted"


def test_business_dba_semantic_is_highest_applicant_evidence(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    csv_path = tmp_path / "dba-applicant-brand.csv"
    _write_filing(
        csv_path,
        project="Confidential tenant improvement",
        description="Commercial retail tenant build out",
        applicant="Starbucks Coffee Company",
    )
    payload = _source_payload(
        str(csv_path), key="dba_applicant_brand", applicant_semantics="business_dba"
    )
    source = client.post("/ingestion/sources", json=payload)
    assert source.status_code == 201, source.text
    run = client.post(f"/ingestion/sources/{source.json()['id']}/runs", json={"max_pages": 1})
    assert run.status_code == 201, run.text

    match = db.query(PermitBrandMatch).one()
    assert match.confidence == 0.97
    assert "applicant_business_dba_source" in match.rule_ids
    response = client.get("/permit-brand-matches")
    assert response.status_code == 200, response.text
    assert response.json()[0]["signal_quality"] == "applicant_dba"


def test_applicant_alias_must_be_the_business_identity(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    csv_path = tmp_path / "applicant-incidental-brand.csv"
    _write_filing(
        csv_path,
        project="Confidential tenant improvement",
        description="Commercial retail tenant build out",
        applicant="Starbucks Permit Services LLC",
    )

    _ingest(client, csv_path, key="applicant_incidental_brand")

    assert db.query(PermitBrandMatch).count() == 0


def test_confirmed_party_history_detects_unnamed_stealth_retailer(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()

    for index in range(2):
        csv_path = tmp_path / f"confirmed-starbucks-{index}.csv"
        _write_filing(
            csv_path,
            description="Starbucks coffee tenant improvement",
            contractor="Northstar Retail Builders",
            architect="Studio Twenty One",
        )
        _ingest(client, csv_path, key=f"confirmed_starbucks_{index}")
        match = db.query(PermitBrandMatch).filter(
            PermitBrandMatch.matched_field == "description",
            PermitBrandMatch.review_status == "candidate",
        ).one()
        response = client.patch(
            f"/permit-brand-matches/{match.id}", json={"review_status": "confirmed"}
        )
        assert response.status_code == 200, response.text

    fingerprints = db.query(BrandPartyFingerprint).filter(
        BrandPartyFingerprint.evidence_count == 2,
        BrandPartyFingerprint.is_active.is_(True),
    ).all()
    assert {row.party_type for row in fingerprints} >= {"contractor_name", "architect_name"}
    assert all(len(row.source_match_ids) == 2 for row in fingerprints)

    stealth_path = tmp_path / "unnamed-retailer.csv"
    _write_filing(
        stealth_path,
        project="Confidential tenant improvement",
        description="Retail tenant build out with drive-through service",
        contractor="Northstar Retail Builders",
        architect="Studio Twenty One",
    )
    _ingest(client, stealth_path, key="unnamed_retailer")

    inferred = db.query(PermitBrandMatch).filter(
        PermitBrandMatch.matched_field == "historical_parties"
    ).one()
    assert inferred.brand.key == "starbucks"
    assert inferred.detector_version == "stealth-retailer-v1"
    assert inferred.confidence < 0.90
    assert inferred.matched_fields == ["architect_name", "contractor_name"]
    assert "multiple_independent_parties" in inferred.rule_ids

    listed = client.get(
        "/permit-brand-matches?detection_method=historical_party&review_status=candidate"
    )
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [inferred.id]
    assert listed.json()[0]["detection_method"] == "historical_party"
    assert listed.json()[0]["signal_quality"] == "historical_party"

    evidence = client.get(f"/permit-brand-matches/{inferred.id}/evidence")
    assert evidence.status_code == 200, evidence.text
    history = evidence.json()["inference_evidence"]
    assert {row["party_type"] for row in history} == {"architect_name", "contractor_name"}
    assert all(row["evidence_count"] == 2 for row in history)
    assert all(len(row["source_match_ids"]) == 2 for row in history)


def test_single_historical_party_never_surfaces_prediction(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    brand = db.query(BrandProfile).filter(BrandProfile.key == "starbucks").one()
    db.add(BrandPartyFingerprint(
        organization_id="default-org",
        brand_id=brand.id,
        party_type="contractor_name",
        normalized_name="northstar retail builders",
        display_name="Northstar Retail Builders",
        state="TX",
        evidence_count=4,
        source_match_ids=["one", "two", "three", "four"],
        confidence=0.84,
    ))
    db.commit()

    csv_path = tmp_path / "one-party-only.csv"
    _write_filing(
        csv_path,
        project="Confidential retail tenant",
        description="Retail tenant build out",
        contractor="Northstar Retail Builders",
    )
    _ingest(client, csv_path, key="one_party_only")
    assert db.query(PermitBrandMatch).count() == 0


def test_expanded_catalog_detects_named_preapproval_retailers(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()

    filings = (
        ("dutch_bros", "Dutch Bros Coffee drive-through tenant build-out"),
        ("tractor_supply", "New Tractor Supply retail store and garden center"),
        ("scooters_coffee", "Scooters Coffee drive-through tenant finish"),
        ("floor_and_decor", "New Floor and Decor retail shell improvement"),
        ("homesense", "HomeSense home furnishings tenant improvement"),
        ("kohls", "Kohl's retail store tenant build-out"),
        ("dicks_sporting_goods", "DICK'S Sporting Goods retail shell and sign package"),
        ("macys", "Macy's department store tenant improvement"),
        ("panda_express", "Panda Express restaurant tenant finish"),
        ("buffalo_wild_wings", "Buffalo Wild Wings restaurant build-out"),
    )
    for index, (key, description) in enumerate(filings, start=1):
        csv_path = tmp_path / f"{key}.csv"
        _write_filing(csv_path, description=description)
        _ingest(client, csv_path, key=f"expanded_catalog_{index}")

    matches = db.query(PermitBrandMatch).all()
    assert {match.brand.key for match in matches} == {key for key, _ in filings}
    assert all(match.permit.approval_stage == "pre_approval" for match in matches)
    assert all(match.matched_field == "description" for match in matches)


def test_telecom_retail_brands_require_storefront_context(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()

    csv_path = tmp_path / "verizon.csv"
    _write_filing(
        csv_path,
        description="Verizon Wireless authorized retailer storefront sign",
    )
    _ingest(client, csv_path, key="telecom_retail_signage")

    match = db.query(PermitBrandMatch).one()
    assert match.brand.key == "verizon"
    assert match.matched_field == "description"
    assert "Verizon Wireless" in match.excerpt


def test_los_angeles_catalog_run_creates_preapproval_brand_candidate(
    client, db, monkeypatch
):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    monkeypatch.setattr(
        ingestion_service,
        "build_connector",
        lambda *_args, **_kwargs: _StaticConnector([
            {
                "permit_nbr": "26016-10000-15835",
                "primary_address": "6081 W CENTER DR 202B-202C",
                "zip_code": "90045",
                "apn": "4104001035",
                "zone": "C2-1",
                "permit_type": "Bldg-Alter/Repair",
                "permit_sub_type": "Commercial",
                "use_desc": "Retail",
                "submitted_date": "2026-07-10T00:00:00.000",
                "issue_date": None,
                "status_desc": "Submitted",
                "status_date": "2026-07-10T00:00:00.000",
                "valuation": "50000",
                "square_footage": "2400",
                "business_unit": "Regular Plan Check",
                "work_desc": "Tenant build out for Planet Fitness gym",
                "lat": "33.97811",
                "lon": "-118.39245",
                "refresh_time": "2026-07-12T00:00:00.000",
            }
        ]),
    )
    source = client.post(
        "/ingestion/sources",
        json=_catalog_source_payload("los_angeles_ca_building_permits_submitted"),
    )
    assert source.status_code == 201, source.text

    run = client.post(f"/ingestion/sources/{source.json()['id']}/runs", json={"max_pages": 1})

    assert run.status_code == 201, run.text
    assert run.json()["records_inserted"] == 1
    permit = db.query(PermitRecord).one()
    assert permit.approval_stage == "pre_approval"
    assert permit.status == "Submitted"
    assert permit.description == "Tenant build out for Planet Fitness gym"
    match = db.query(PermitBrandMatch).one()
    assert match.brand.key == "planet_fitness"
    assert match.matched_field == "description"
    assert match.confidence == 0.92
    assert "Planet Fitness" in match.excerpt
    assert db.query(GraphRelationshipEvidence).count() >= 1


def test_hartford_catalog_run_creates_preapproval_chain_candidate(
    client, db, monkeypatch
):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    monkeypatch.setattr(
        ingestion_service,
        "build_connector",
        lambda *_args, **_kwargs: _StaticConnector([
            {
                "OBJECTID": 3553,
                "RECORD_ID": "COM-ALT-26-000302",
                "DESCRIPTION": "STARBUCKS tenant plumbing and sign fit-out",
                "DATE_OPENED": "2026-06-29 ",
                "DATE_CLOSED": None,
                "RECORD_TYPE_TYPE": "Commercial",
                "B1_APP_TYPE_ALIAS": "Commercial Alteration Permit",
                "RECORD_STATUS": "Pending",
                "PROPERTY_ADDRESS": "317 WEST SERVICE RD, HARTFORD, CT 06120",
                "Location": "317 WEST SERVICE RD ",
                "UNIT": None,
                "PROPERTY_CITY": "HARTFORD",
                "PROPERTY_STATE": "CT",
                "PROPERTY_ZIP": "06120",
                "PARCEL_ID": "304074015",
                "Total_Construction_Cost": 7500.0,
                "DateIssued": None,
                "GlobalID": "{CBB433C4-0ADD-4B50-94AB-1123A3EACC5F}",
            }
        ]),
    )
    source = client.post(
        "/ingestion/sources",
        json=_catalog_source_payload("hartford_ct_building_permits_lifecycle"),
    )
    assert source.status_code == 201, source.text

    run = client.post(f"/ingestion/sources/{source.json()['id']}/runs", json={"max_pages": 1})

    assert run.status_code == 201, run.text
    assert run.json()["records_inserted"] == 1
    permit = db.query(PermitRecord).one()
    assert permit.approval_stage == "pre_approval"
    assert permit.status == "Pending"
    assert permit.parcel_id == "304074015"
    match = db.query(PermitBrandMatch).one()
    assert match.brand.key == "starbucks"
    assert match.matched_field == "project_name"
    assert match.confidence == 0.98
    assert "STARBUCKS" in match.excerpt
    assert db.query(GraphRelationshipEvidence).count() >= 1


def test_nyc_dob_now_job_run_creates_preapproval_signage_brand_candidate(
    client, db, monkeypatch
):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    monkeypatch.setattr(
        ingestion_service,
        "build_connector",
        lambda *_args, **_kwargs: _StaticConnector([
            {
                ":id": "row-test-tmobile",
                "job_filing_number": "M01000000-I1",
                "filing_status": "Plan Examiner Review",
                "house_no": "418",
                "street_name": "EAST 14 STREET",
                "borough": "Manhattan",
                "postcode": "10009",
                "block": "00440",
                "lot": "0001",
                "bin": "1000001",
                "bbl": "1004400001",
                "commmunity_board": "103",
                "work_on_floor": "1",
                "job_type": "Alteration",
                "filing_review_type": "Standard Plan Examination",
                "building_type": "Mixed",
                "job_description": "Install accessory business sign for T-Mobile authorized retailer.",
                "applicant_business_name": "Sign Engineer LLC",
                "owner_s_business_name": "Retail Property Owner LLC",
                "initial_cost": "18000",
                "total_construction_floor_area": "400",
                "proposed_dwelling_units": "0",
                "latitude": "40.731",
                "longitude": "-73.989",
                "filing_date": "2026-07-01T00:00:00.000",
                "current_status_date": "2026-07-17T04:32:49.000",
                "approved_date": None,
            }
        ]),
    )
    source = client.post(
        "/ingestion/sources",
        json=_catalog_source_payload("new_york_ny_dob_now_job_applications"),
    )
    assert source.status_code == 201, source.text

    run = client.post(f"/ingestion/sources/{source.json()['id']}/runs", json={"max_pages": 1})

    assert run.status_code == 201, run.text
    assert run.json()["records_inserted"] == 1
    permit = db.query(PermitRecord).one()
    assert permit.approval_stage == "pre_approval"
    assert permit.status == "Plan Examiner Review"
    match = db.query(PermitBrandMatch).one()
    assert match.brand.key == "t_mobile"
    assert match.matched_field == "description"
    assert match.confidence == 0.92
    assert "T-Mobile" in match.excerpt
    assert db.query(GraphRelationshipEvidence).count() >= 1


def test_nyc_dohmh_catalog_run_creates_preinspection_dba_brand_candidate(
    client, db, monkeypatch
):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    monkeypatch.setattr(
        ingestion_service,
        "build_connector",
        lambda *_args, **_kwargs: _StaticConnector([
            {
                ":id": "row-shake-shack",
                "camis": "50199999",
                "dba": "SHAKE SHACK",
                "boro": "Manhattan",
                "building": "235",
                "street": "WEST   46 STREET",
                "zipcode": "10036",
                "cuisine_description": "Hamburgers",
                "inspection_date": "1900-01-01T00:00:00.000",
                "action": None,
                "inspection_type": None,
                "record_date": "2026-07-17T06:00:15.000",
                "bin": "1024737",
                "bbl": "1010180006",
                "latitude": "40.759124635911",
                "longitude": "-73.986348218206",
            }
        ]),
    )
    source = client.post(
        "/ingestion/sources",
        json=_catalog_source_payload("new_york_ny_dohmh_restaurant_permit_applicants"),
    )
    assert source.status_code == 201, source.text

    run = client.post(f"/ingestion/sources/{source.json()['id']}/runs", json={"max_pages": 1})

    assert run.status_code == 201, run.text
    assert run.json()["records_inserted"] == 1
    permit = db.query(PermitRecord).one()
    assert permit.approval_stage == "pre_approval"
    assert permit.project_name == "SHAKE SHACK"
    assert permit.address == "235 WEST 46 STREET"
    match = db.query(PermitBrandMatch).one()
    assert match.brand.key == "shake_shack"
    assert match.matched_field == "project_name"
    assert match.confidence == 0.98
    assert "SHAKE SHACK" in match.excerpt
    company = db.query(GraphEntity).filter(GraphEntity.entity_type == "company").one()
    assert company.display_name == "Shake Shack"
    listed = client.get("/permit-brand-matches?approval_stage=pre_approval")
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["signal_quality"] == "applicant_dba"
    assert listed.json()[0]["signal_quality_label"] == "Applicant DBA"
    assert "establishment name" in listed.json()[0]["signal_quality_note"]

    evidence = client.get(f"/permit-brand-matches/{match.id}/evidence")
    assert evidence.status_code == 200, evidence.text
    body = evidence.json()
    assert body["signal_quality"] == "applicant_dba"
    assert body["latest_evidence"]["source_key"] == "new_york_ny_dohmh_restaurant_permit_applicants"
    assert body["latest_evidence"]["external_record_id"] == "row-shake-shack"
    assert body["latest_evidence"]["received_age_hours"] >= 0
    assert body["latest_evidence"]["last_observed_at"] >= body["latest_evidence"]["received_at"]
    assert body["latest_evidence"]["last_observed_age_hours"] >= 0
    assert body["latest_evidence"]["observation_recorded"] is True
    assert body["latest_evidence"]["source_lag_hours"] is None
    assert body["latest_evidence"]["source_timestamp_semantics"] == "ingestion_observed_at"
    assert body["latest_evidence"]["source_timestamp_label"] == "Source timestamp"
    assert body["latest_evidence"]["payload_excerpt"]["dba"] == "SHAKE SHACK"
    assert body["latest_evidence"]["payload_excerpt"]["camis"] == "50199999"
    assert "phone" not in body["latest_evidence"]["payload_excerpt"]
    assert body["first_evidence"]["raw_record_id"] == body["latest_evidence"]["raw_record_id"]
    assert body["linked_deals"] == []
    assert body["graph_context"][0]["relationship_type"] == "related_to"
    assert body["graph_context"][0]["review_status"] == "candidate"
    assert body["graph_context"][0]["is_current"] is True
    assert body["graph_context"][0]["evidence_count"] == 1
    assert body["graph_context"][0]["related_entity"]["display_name"] == "Shake Shack"
    assert body["graph_context"][0]["related_entity"]["entity_type"] == "company"
    assert body["graph_context"][0]["evidence_preview"]["source_system"] == "new_york_ny_dohmh_restaurant_permit_applicants"
    assert "SHAKE SHACK" in body["graph_context"][0]["evidence_preview"]["excerpt"]


def test_new_york_sla_pending_license_creates_preopening_brand_candidate(
    client, db, monkeypatch
):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    monkeypatch.setattr(
        ingestion_service,
        "build_connector",
        lambda *_args, **_kwargs: _StaticConnector([
            {
                "application_id": "NA-0340-26-120427",
                "premises_county": "Nassau",
                "type": "1",
                "class": "340",
                "description": "Restaurant",
                "legalname": "Chipotle Mexican Grill of Colorado LLC",
                "dba": "Chipotle Mexican Grill",
                "actual_address_of_premises": "85 Henry St",
                "additional_address_information": None,
                "city": "Freeport",
                "state_name": "New York",
                "zip_code": "11520",
                "received_date": "2026-07-17T15:37:00.000",
                "status": "Under Review",
                "aka_address": None,
                "georeference": {
                    "type": "Point",
                    "coordinates": [-73.5792, 40.65521],
                },
            }
        ]),
    )
    source = client.post(
        "/ingestion/sources",
        json=_catalog_source_payload("new_york_state_sla_pending_licenses"),
    )
    assert source.status_code == 201, source.text

    run = client.post(f"/ingestion/sources/{source.json()['id']}/runs", json={"max_pages": 1})

    assert run.status_code == 201, run.text
    assert run.json()["records_inserted"] == 1
    permit = db.query(PermitRecord).one()
    assert permit.approval_stage == "pre_approval"
    assert permit.project_name == "Chipotle Mexican Grill"
    assert permit.proposed_use == "Restaurant"
    match = db.query(PermitBrandMatch).one()
    assert match.brand.key == "chipotle"
    assert match.matched_field == "project_name"
    assert match.confidence == 0.98
    assert "Chipotle" in match.excerpt
    assert db.query(GraphRelationshipEvidence).count() >= 1


def test_texas_sales_tax_future_first_sale_creates_retailer_opening_candidate(
    client, db, monkeypatch
):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    monkeypatch.setattr(
        ingestion_service,
        "build_connector",
        lambda *_args, **_kwargs: _StaticConnector([
            {
                "tp_number": "17418232123",
                "tp_name": "STARBUCKS CORPORATION",
                "org_type": "CORPORATION",
                "loc_number": "9812",
                "loc_name": "STARBUCKS",
                "address_number": "1000",
                "address_text": "MAIN ST STE 120",
                "permit_date": "2026-07-09T00:00:00.000",
                "juris_city": "HOUSTON",
                "loc_city": "HOUSTON",
                "loc_state": "TX",
                "loc_zip": "77002",
                "loc_county": "101",
                "naics": "722515",
                "first_sale_date": "2099-08-01T00:00:00.000",
                "out_of_business_date": None,
            }
        ]),
    )
    source = client.post(
        "/ingestion/sources",
        json=_catalog_source_payload("texas_comptroller_sales_tax_locations"),
    )
    assert source.status_code == 201, source.text

    run = client.post(f"/ingestion/sources/{source.json()['id']}/runs", json={"max_pages": 1})

    assert run.status_code == 201, run.text
    assert run.json()["records_inserted"] == 1
    permit = db.query(PermitRecord).one()
    assert permit.approval_stage == "approved"
    assert permit.permit_type == "Sales tax permit"
    assert permit.attributes["first_sale_date"] == "2099-08-01T00:00:00.000"
    match = db.query(PermitBrandMatch).one()
    assert match.brand.key == "starbucks"
    assert match.matched_field == "project_name"
    assert match.confidence == 0.98
    assert "approved_retailer_opening" in match.rule_ids
    assert "future_first_sale_date" in match.rule_ids


def test_preapproval_future_first_sale_also_creates_retailer_opening_candidate(
    client, db, monkeypatch, tmp_path
):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    monkeypatch.setattr(
        ingestion_service,
        "build_connector",
        lambda *_args, **_kwargs: _StaticConnector([
            {
                "id": "17418232124",
                "application_no": "APP-2",
                "stage": "pre_approval",
                "type": "Commercial Retail",
                "status": "Under Review",
                "project": "Dutch Bros Coffee tenant improvement",
                "description": "Pre-approval tenant improvement for Dutch Bros Coffee",
                "address": "1002 Main St Ste 130",
                "city": "Houston",
                "state": "TX",
                "parcel": "P-2",
                "filed": "2026-07-09T00:00:00.000",
                "first_sale_date": "2099-08-01T00:00:00.000",
                "out_of_business_date": None,
            }
        ]),
    )
    payload = _source_payload(str(tmp_path / "preapproval-retailer.csv"), key="preapproval_retail_opening")
    payload["settings"] = {
        "connector": {"page_size": 100},
        "retailer_opening_signal": True,
        "opening_signal_date_field": "first_sale_date",
    }
    source = client.post("/ingestion/sources", json=payload)
    assert source.status_code == 201, source.text

    run = client.post(f"/ingestion/sources/{source.json()['id']}/runs", json={"max_pages": 1})

    assert run.status_code == 201, run.text
    assert run.json()["records_inserted"] == 1
    permit = db.query(PermitRecord).one()
    assert permit.approval_stage == "pre_approval"
    assert permit.project_name == "Dutch Bros Coffee tenant improvement"
    match = db.query(PermitBrandMatch).one()
    assert match.brand.key == "dutch_bros"
    assert match.matched_field == "project_name"
    assert match.confidence == 0.98
    assert "approved_retailer_opening" in match.rule_ids
    assert "future_first_sale_date" in match.rule_ids


def test_owner_only_and_approved_records_do_not_create_candidates(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()

    owner_only = tmp_path / "owner-only.csv"
    _write_filing(
        owner_only,
        project="Unidentified tenant improvement",
        description="Interior commercial retail remodel",
        owner="Starbucks Coffee Company",
    )
    payload = _source_payload(str(owner_only), key="owner_only")
    payload["field_mappings"].append(
        {"source_field": "owner", "canonical_field": "owner_name"}
    )
    source = client.post("/ingestion/sources", json=payload).json()
    client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert db.query(PermitBrandMatch).count() == 0


def test_terminal_preapproval_record_does_not_create_candidate(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    withdrawn = tmp_path / "withdrawn.csv"
    _write_filing(withdrawn)
    contents = withdrawn.read_text().replace("Under Review", "Withdrawn")
    withdrawn.write_text(contents)

    _ingest(client, withdrawn, key="withdrawn_filing")

    assert db.query(PermitBrandMatch).count() == 0

    approved = tmp_path / "approved.csv"
    _write_filing(approved, stage="approved")
    _ingest(client, approved, key="approved_only")
    assert db.query(PermitBrandMatch).count() == 0


def test_ambiguous_and_negative_context_controls(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()

    ambiguous = tmp_path / "ambiguous.csv"
    _write_filing(
        ambiguous,
        project="Target",
        description="Commercial retail remodel for an unidentified tenant",
    )
    _ingest(client, ambiguous, key="ambiguous_target")
    assert db.query(PermitBrandMatch).count() == 0

    adjacent = tmp_path / "adjacent.csv"
    _write_filing(
        adjacent,
        project="Coffee tenant improvement",
        description="Retail remodel adjacent to Starbucks",
    )
    _ingest(client, adjacent, key="adjacent_starbucks")
    assert db.query(PermitBrandMatch).count() == 0

    ambiguous_contextless = tmp_path / "first-watch-contextless.csv"
    _write_filing(
        ambiguous_contextless,
        project="Monitoring equipment",
        description="First watch equipment replacement for industrial system",
    )
    _ingest(client, ambiguous_contextless, key="first_watch_contextless")
    assert db.query(PermitBrandMatch).count() == 0


def test_correction_retracts_candidate_without_deleting_evidence(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    csv_path = tmp_path / "corrected.csv"
    _write_filing(csv_path)
    source = client.post(
        "/ingestion/sources", json=_source_payload(str(csv_path), key="corrected")
    ).json()
    client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    match_id = db.query(PermitBrandMatch).one().id

    _write_filing(
        csv_path,
        project="Unidentified tenant improvement",
        description="Interior commercial retail build-out",
    )
    rerun = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert rerun.status_code == 201, rerun.text
    db.expire_all()

    match = db.query(PermitBrandMatch).one()
    assert match.id == match_id
    assert match.review_status == "retracted"
    assert match.first_raw_record_id != match.latest_raw_record_id
    relationship = db.query(GraphRelationship).filter(
        GraphRelationship.attributes["brand_match_id"].as_string() == match.id
    ).one()
    assert relationship.is_current is False


def test_snapshot_retirement_retracts_brand_signal_and_reappearance_restores_candidate(
    client, db, tmp_path
):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    csv_path = tmp_path / "retired-brand.csv"
    _write_filing(csv_path)
    payload = _source_payload(str(csv_path), key="retired_brand")
    payload["settings"]["reconciliation_mode"] = "daily_full_snapshot"
    payload["settings"]["allow_empty_snapshot"] = True
    payload["settings"]["max_snapshot_retirement_fraction"] = 1.0
    source = client.post("/ingestion/sources", json=payload).json()
    client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    match = db.query(PermitBrandMatch).one()
    relationship = db.query(GraphRelationship).filter(
        GraphRelationship.attributes["brand_match_id"].as_string() == match.id
    ).one()

    csv_path.write_text(
        "id,application_no,stage,type,status,project,description,address,city,state,parcel,filed,owner\n"
    )
    client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    db.expire_all()
    assert db.query(PermitBrandMatch).one().review_status == "retracted"
    assert db.get(GraphRelationship, relationship.id).is_current is False

    _write_filing(csv_path)
    client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    db.expire_all()
    assert db.query(PermitBrandMatch).one().review_status == "candidate"
    assert db.get(GraphRelationship, relationship.id).is_current is True


def test_snapshot_retirement_preserves_confirmed_match_for_reverification(
    client, db, tmp_path
):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    csv_path = tmp_path / "confirmed-retired-brand.csv"
    _write_filing(
        csv_path,
        owner="Stealth Coffee Holdings LLC",
        contractor="Northstar Retail Builders",
    )
    payload = _source_payload(str(csv_path), key="confirmed_retired_brand")
    payload["settings"]["reconciliation_mode"] = "daily_full_snapshot"
    payload["settings"]["allow_empty_snapshot"] = True
    payload["settings"]["max_snapshot_retirement_fraction"] = 1.0
    source = client.post("/ingestion/sources", json=payload).json()
    client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    match = db.query(PermitBrandMatch).one()
    confirmed = client.patch(
        f"/permit-brand-matches/{match.id}", json={"review_status": "confirmed"}
    )
    assert confirmed.status_code == 200, confirmed.text
    relationship = db.query(GraphRelationship).filter(
        GraphRelationship.attributes["brand_match_id"].as_string() == match.id
    ).one()
    assert any(row.is_active for row in db.query(BrandPartyFingerprint).all())

    csv_path.write_text(
        "id,application_no,stage,type,status,project,description,address,city,state,parcel,filed,owner\n"
    )
    retired = client.post(
        f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1}
    )
    assert retired.status_code == 201, retired.text
    db.expire_all()

    preserved = db.query(PermitBrandMatch).one()
    assert preserved.review_status == "confirmed"
    assert preserved.permit.is_active is False
    retired_relationship = db.get(GraphRelationship, relationship.id)
    assert retired_relationship.is_current is False
    assert retired_relationship.attributes["source_record_active"] is False
    assert retired_relationship.attributes["retired_from_source_snapshot"] is True
    assert all(not row.is_active for row in db.query(BrandPartyFingerprint).all())
    listed = client.get("/permit-brand-matches?review_status=confirmed")
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["needs_reverification"] is True
    evidence = client.get(f"/permit-brand-matches/{match.id}/evidence")
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["needs_reverification"] is True

    _write_filing(
        csv_path,
        owner="Stealth Coffee Holdings LLC",
        contractor="Northstar Retail Builders",
    )
    restored = client.post(
        f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1}
    )
    assert restored.status_code == 201, restored.text
    db.expire_all()
    assert db.query(PermitBrandMatch).one().review_status == "confirmed"
    assert db.query(PermitRecord).one().is_active is True
    restored_relationship = db.get(GraphRelationship, relationship.id)
    assert restored_relationship.is_current is True
    assert restored_relationship.attributes["source_record_active"] is True
    assert restored_relationship.attributes["retired_from_source_snapshot"] is False
    assert any(row.is_active for row in db.query(BrandPartyFingerprint).all())
    relisted = client.get("/permit-brand-matches?review_status=confirmed")
    assert relisted.json()[0]["needs_reverification"] is False


def test_brand_match_can_create_evidence_backed_opportunity(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    csv_path = tmp_path / "chipotle.csv"
    _write_filing(
        csv_path,
        project="Chipotle tenant improvement",
        description="Interior retail build-out for Chipotle Mexican Grill",
    )
    _ingest(client, csv_path, key="chipotle_opportunity")

    match = db.query(PermitBrandMatch).one()
    created = client.post(f"/permit-brand-matches/{match.id}/opportunity", json={})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["created"] is True
    assert body["deal"]["name"] == "Chipotle at 100 Main St"
    assert body["deal"]["source"] == "Permit brand match"
    assert body["deal"]["status"] == "new"
    assert body["nearby_parcel_search"] is None
    assert body["nearby_parcel_searches"] == []

    db.expire_all()
    assert db.query(PermitBrandMatch).one().review_status == "confirmed"
    assert db.query(Signal).count() == 1
    signal = db.query(Signal).one()
    assert signal.signal_type == "Permit Activity"
    assert "Chipotle" in (signal.description or "")

    listed = client.get("/permit-brand-matches?approval_stage=pre_approval")
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["linked_deals"][0]["name"] == "Chipotle at 100 Main St"

    repeated = client.post(f"/permit-brand-matches/{match.id}/opportunity", json={})
    assert repeated.status_code == 200, repeated.text
    repeated_body = repeated.json()
    assert repeated_body["created"] is False
    assert repeated_body["deal"]["id"] == body["deal"]["id"]
    assert db.query(Signal).count() == 1


def test_confirming_linked_brand_match_seeds_nearby_parcel_searches(client, db):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()

    deal = client.post("/deals", json={
        "name": "Main Street Retail",
        "address": "100 Main St",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
        "property_type": "retail",
    })
    assert deal.status_code == 201, deal.text

    source = ingestion_service.IngestionSource(
        organization_id="default-org",
        key="brand-confirm-test-source",
        name="Brand Confirm Test Source",
        adapter="csv",
        record_type="permit",
    )
    db.add(source)
    db.flush()
    run = ingestion_service.IngestionRun(
        organization_id="default-org",
        source_id=source.id,
        status="completed",
    )
    db.add(run)
    db.flush()
    raw = ingestion_service.RawSourceRecord(
        organization_id="default-org",
        source_id=source.id,
        run_id=run.id,
        external_record_id="permit-confirm-1",
        record_type="permit",
        content_hash="brand-confirm-hash",
        payload={},
    )
    db.add(raw)
    db.flush()
    permit = PermitRecord(
        organization_id="default-org",
        source_id=source.id,
        latest_raw_record_id=raw.id,
        external_record_id="permit-confirm-1",
        normalization_hash="brand-confirm-hash",
        approval_stage="pre_approval",
        status="Under Review",
        project_name="Main Street Retail",
        address="100 Main St",
        city="Austin",
        state="TX",
        postal_code="78701",
        latitude=30.2672,
        longitude=-97.7431,
    )
    db.add(permit)
    db.flush()
    _project_permit_to_graph(db, source, permit, raw)

    brand = db.query(BrandProfile).filter(BrandProfile.key == "starbucks").one()
    match = PermitBrandMatch(
        organization_id="default-org",
        permit_id=permit.id,
        brand_id=brand.id,
        first_raw_record_id=raw.id,
        latest_raw_record_id=raw.id,
        review_status="candidate",
        confidence=0.92,
        matched_alias="Starbucks",
        matched_field="description",
        matched_fields=["description"],
        rule_ids=["pre_approval", "retail_context"],
        excerpt="Interior retail build-out for Starbucks Coffee",
        detector_version="brand-alias-v1",
    )
    db.add(match)
    db.commit()

    evidence = client.get(f"/permit-brand-matches/{match.id}/evidence")
    assert evidence.status_code == 200, evidence.text
    assert (
        evidence.json()["latest_evidence"]["last_observed_at"]
        == evidence.json()["latest_evidence"]["received_at"]
    )
    assert evidence.json()["latest_evidence"]["observation_recorded"] is False

    response = client.patch(
        f"/permit-brand-matches/{match.id}",
        json={"review_status": "confirmed"},
    )
    assert response.status_code == 200, response.text

    db.expire_all()
    searches = db.query(NearbyParcelSearch).filter(
        NearbyParcelSearch.deal_id == deal.json()["id"]
    ).all()
    assert {search.persona for search in searches} == {
        "developer", "investor", "broker", "realtor"
    }
    assert all(search.anchor_brand_match_id == match.id for search in searches)

    repeated = client.post(f"/permit-brand-matches/{match.id}/opportunity", json={})
    assert repeated.status_code == 200, repeated.text
    repeated_body = repeated.json()
    assert repeated_body["created"] is False
    assert repeated_body["deal"]["id"] == deal.json()["id"]
    assert repeated_body["nearby_parcel_search"] is not None
    assert repeated_body["nearby_parcel_search"]["persona"] == "developer"
    assert len(repeated_body["nearby_parcel_searches"]) == 4
