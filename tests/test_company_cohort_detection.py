from __future__ import annotations

import csv

import pytest

from app.models.brand import BrandAlias, BrandProfile, PermitBrandMatch
from app.services.graph_service import normalize_name
from app.utils.org_scope import get_org_id


def _add_company(db, *, key: str, name: str, cohort: str | None) -> BrandProfile:
    brand = BrandProfile(
        organization_id=get_org_id(),
        key=key,
        name=name,
        normalized_name=normalize_name(name),
        category="homebuilder" if cohort == "major_builder" else "retail",
        priority=5,
        attributes={"signal_cohort": cohort} if cohort else None,
    )
    db.add(brand)
    db.flush()
    db.add(
        BrandAlias(
            organization_id=get_org_id(),
            brand_id=brand.id,
            alias=name,
            normalized_alias=normalize_name(name),
            confidence=1.0,
        )
    )
    db.commit()
    return brand


def _source_payload(csv_path: str, key: str) -> dict:
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
        "applicant": "applicant_name",
        "developer": "developer_name",
        "owner": "owner_name",
    }
    return {
        "key": key,
        "name": f"{key} test source",
        "adapter": "csv",
        "record_type": "permit",
        "jurisdiction": "Austin, TX",
        "base_url": csv_path,
        "settings": {"connector": {"page_size": 100}},
        "field_mappings": [
            {
                "source_field": source,
                "canonical_field": canonical,
                **({"value_semantics": "legal_entity"} if canonical == "applicant_name" else {}),
            }
            for source, canonical in fields.items()
        ],
    }


def _ingest(
    client,
    tmp_path,
    *,
    key: str,
    project: str,
    description: str,
    applicant: str = "",
    developer: str = "",
    owner: str = "",
    stage: str = "pre_approval",
) -> dict:
    csv_path = tmp_path / f"{key}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "application_no",
                "stage",
                "type",
                "status",
                "project",
                "description",
                "address",
                "city",
                "state",
                "parcel",
                "applicant",
                "developer",
                "owner",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "1",
                "application_no": "APP-1",
                "stage": stage,
                "type": "Development application",
                "status": "Under Review",
                "project": project,
                "description": description,
                "address": "100 Main St",
                "city": "Austin",
                "state": "TX",
                "parcel": "P-1",
                "applicant": applicant,
                "developer": developer,
                "owner": owner,
            }
        )
    source = client.post("/ingestion/sources", json=_source_payload(str(csv_path), key))
    assert source.status_code == 201, source.text
    source_id = source.json()["id"]
    run = client.post(f"/ingestion/sources/{source_id}/runs", json={"max_pages": 1})
    assert run.status_code == 201, run.text
    return {"source_id": source_id, "csv_path": csv_path}


def test_major_builder_matches_direct_developer_and_is_idempotent(client, db, tmp_path):
    _add_company(db, key="toll_brothers", name="Toll Brothers", cohort="major_builder")
    ingested = _ingest(
        client,
        tmp_path,
        key="builder_developer",
        project="Cedar Ridge",
        description="Site development and grading for 84 residential lots",
        developer="Toll Brothers",
    )

    match = db.query(PermitBrandMatch).one()
    match_id = match.id
    assert match.matched_field == "developer_name"
    assert match.confidence == 0.96
    assert "major_builder_development_context" in match.rule_ids
    assert "major_builder_exact_alias" in match.rule_ids

    rerun = client.post(f"/ingestion/sources/{ingested['source_id']}/runs", json={"max_pages": 1})
    assert rerun.status_code == 201, rerun.text
    assert db.query(PermitBrandMatch).one().id == match_id


def test_major_builder_matches_description_with_residential_context(client, db, tmp_path):
    _add_company(db, key="toll_brothers", name="Toll Brothers", cohort="major_builder")
    _ingest(
        client,
        tmp_path,
        key="builder_description",
        project="Cedar Ridge",
        description="Toll Brothers proposes a single-family subdivision with model homes",
    )

    match = db.query(PermitBrandMatch).one()
    assert match.matched_field == "description"
    assert match.confidence == 0.92


def test_major_builder_keeps_approved_development_signals(client, db, tmp_path):
    _add_company(db, key="toll_brothers", name="Toll Brothers", cohort="major_builder")
    _ingest(
        client,
        tmp_path,
        key="approved_builder",
        project="Toll Brothers at Cedar Ridge",
        description="Approved single-family residential subdivision",
        developer="Toll Brothers",
        stage="approved",
    )

    match = db.query(PermitBrandMatch).one()
    assert match.brand.key == "toll_brothers"
    assert match.permit.approval_stage == "approved"


def test_major_builder_rejects_generic_grading_context(client, db, tmp_path):
    _add_company(db, key="toll_brothers", name="Toll Brothers", cohort="major_builder")
    _ingest(
        client,
        tmp_path,
        key="builder_generic_grading",
        project="Commercial grading permit",
        description="Site development and grading for utility access",
        owner="Toll Brothers",
    )

    assert db.query(PermitBrandMatch).count() == 0


def test_major_builder_rejects_alias_without_development_context(client, db, tmp_path):
    _add_company(db, key="toll_brothers", name="Toll Brothers", cohort="major_builder")
    _ingest(
        client,
        tmp_path,
        key="builder_contextless",
        project="Corporate office electrical work",
        description="Electrical panel replacement for Toll Brothers",
    )

    assert db.query(PermitBrandMatch).count() == 0


@pytest.mark.parametrize(
    "description",
    [
        "Residential lots nearby Toll Brothers model homes",
        "Residential lots formerly Toll Brothers model homes",
        "Residential subdivision competitor to Toll Brothers",
    ],
)
def test_major_builder_rejects_negative_reference(client, db, tmp_path, description):
    _add_company(db, key="toll_brothers", name="Toll Brothers", cohort="major_builder")
    _ingest(
        client,
        tmp_path,
        key="builder_negative",
        project="Oak Creek subdivision",
        description=description,
    )

    assert db.query(PermitBrandMatch).count() == 0


def test_catalog_entry_without_cohort_retains_national_retail_detection(client, db, tmp_path):
    _add_company(db, key="starbucks", name="Starbucks", cohort=None)
    _ingest(
        client,
        tmp_path,
        key="default_retail",
        project="Coffee tenant improvement",
        description="Interior retail build out for Starbucks",
    )

    match = db.query(PermitBrandMatch).one()
    assert match.brand.key == "starbucks"
    assert match.matched_field == "description"
    assert "retail_context" in match.rule_ids
    assert "national_retail_cohort" in match.rule_ids
