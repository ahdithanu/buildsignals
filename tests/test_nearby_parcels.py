from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from uuid import uuid4

import app.services.ingestion.service as ingestion_service
from app.models.audit_log import AuditLog
from app.models.brand import PermitBrandMatch
from app.models.graph import GraphEntity, GraphRelationship, GraphRelationshipEvidence
from app.models.ingestion import (
    IngestionSource,
    RawSourceRecord,
    RawSourceRecordObservation,
)
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.parcel import NearbyParcelCandidate, NearbyParcelSearch, ParcelFact, ParcelRecord
from app.models.user import User
from app.services.brand_intelligence import load_brand_catalog, sync_brand_catalog
from app.services.ingestion.catalog import load_catalog
from app.services.ingestion.connectors import FetchEnvelope
from app.services.parcel_export import derived_export_fields
from app.services.parcel_ingestion import ParcelFactInput, upsert_parcel_snapshot
from app.services.parcel_proximity import find_nearby_parcels, haversine_miles
from app.services.parcel_ranking import rank_developer_candidate, rank_parcel_candidate
from app.services.security import create_access_token, hash_password


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


def _catalog_source_payload(key: str) -> dict:
    entry = next(entry for entry in load_catalog() if entry.key == key)
    return entry.model_dump(mode="json")


def _setup_confirmed_signal(
    client,
    db,
    tmp_path,
    *,
    approval_stage: str = "pre_approval",
    confirm: bool = True,
    headers: dict[str, str] | None = None,
):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    deal = client.post("/deals", headers=headers, json={
        "name": "Main Street signal",
        "address": "100 Main Street",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
        "property_type": "retail",
    }).json()
    csv_path = tmp_path / "geocoded-retail.csv"
    csv_path.write_text(
        "id,application,stage,status,type,description,address,city,state,lat,lon\n"
        f"1,APP-1,{approval_stage},Under Review,Commercial Retail,"
        '"Interior retail build-out for Starbucks Coffee",100 Main St,Austin,TX,30.2672,-97.7431\n'
    )
    payload = {
        "key": "geocoded_retail",
        "name": "Geocoded retail filings",
        "adapter": "csv",
        "record_type": "permit",
        "jurisdiction": "Austin",
        "base_url": str(csv_path),
        "settings": {"connector": {"page_size": 100}},
        "field_mappings": [
            {"source_field": source, "canonical_field": canonical}
            for source, canonical in {
                "id": "source_record_id",
                "application": "application_number",
                "stage": "approval_stage",
                "status": "status",
                "type": "permit_type",
                "description": "description",
                "address": "address",
                "city": "city",
                "state": "state",
                "lat": "latitude",
                "lon": "longitude",
            }.items()
        ],
    }
    source = client.post("/ingestion/sources", headers=headers, json=payload).json()
    run = client.post(
        f"/ingestion/sources/{source['id']}/runs", headers=headers, json={"max_pages": 1}
    )
    assert run.status_code == 201, run.text
    match = db.query(PermitBrandMatch).one()
    if confirm:
        confirmed = client.patch(
            f"/permit-brand-matches/{match.id}", headers=headers, json={"review_status": "confirmed"}
        )
        assert confirmed.status_code == 200, confirmed.text
    return deal, source, match


def _setup_unlinked_geocoded_signal(client, db, tmp_path, *, headers: dict[str, str] | None = None):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    csv_path = tmp_path / "unlinked-geocoded-retail.csv"
    csv_path.write_text(
        "id,application,stage,status,type,description,address,city,state,lat,lon\n"
        "1,APP-2,pre_approval,Under Review,Commercial Retail,"
        '"Interior retail build-out for Starbucks Coffee",100 Main St,Austin,TX,30.2672,-97.7431\n'
    )
    payload = {
        "key": "unlinked_geocoded_retail",
        "name": "Unlinked geocoded retail filings",
        "adapter": "csv",
        "record_type": "permit",
        "jurisdiction": "Austin",
        "base_url": str(csv_path),
        "settings": {"connector": {"page_size": 100}},
        "field_mappings": [
            {"source_field": source, "canonical_field": canonical}
            for source, canonical in {
                "id": "source_record_id",
                "application": "application_number",
                "stage": "approval_stage",
                "status": "status",
                "type": "permit_type",
                "description": "description",
                "address": "address",
                "city": "city",
                "state": "state",
                "lat": "latitude",
                "lon": "longitude",
            }.items()
        ],
    }
    source = client.post("/ingestion/sources", headers=headers, json=payload).json()
    run = client.post(
        f"/ingestion/sources/{source['id']}/runs", headers=headers, json={"max_pages": 1}
    )
    assert run.status_code == 201, run.text
    match = db.query(PermitBrandMatch).one()
    return source, match


def _add_parcel(
    db,
    source_id: str,
    raw_id: str,
    parcel_id: str,
    longitude: float,
    *,
    organization_id: str = "default-org",
    **values,
):
    now = datetime.now(timezone.utc)
    parcel = ParcelRecord(
        organization_id=organization_id,
        source_id=source_id,
        latest_raw_record_id=raw_id,
        external_parcel_id=parcel_id,
        jurisdiction="Travis County",
        county="Travis",
        state="TX",
        address=f"{parcel_id} Congress Ave",
        city="Austin",
        postal_code="78701",
        normalized_address=f"{parcel_id} congress ave austin tx",
        latitude=30.2672,
        longitude=longitude,
        last_verified_at=now,
        **values,
    )
    db.add(parcel)
    db.flush()
    fact = ParcelFact(
        organization_id=organization_id,
        parcel_id=parcel.id,
        raw_source_record_id=raw_id,
        fact_type="zoning",
        value={"code": parcel.zoning_code},
        source_system="test_assessor",
        source_url="https://example.gov/parcels",
        field_path="zoning_code",
        excerpt=parcel.zoning_code,
        confidence=1.0,
        observed_at=now,
        last_verified_at=now,
        valid_from=now,
        is_current=True,
    )
    db.add(fact)
    return parcel


def _role_headers(db, role: MemberRole = MemberRole.admin) -> dict[str, str]:
    org = db.get(Organization, "default-org") or Organization(
        id="default-org", name="Default Org", slug="default-org", is_active=True
    )
    user = User(
        id=str(uuid4()),
        email=f"parcel-export-{uuid4()}@acme.com",
        full_name="Parcel Export Admin",
        password_hash=hash_password("CorrectHorseBattery42"),
        is_active=True,
    )
    db.add_all([org, user])
    db.add(OrganizationMembership(
        id=str(uuid4()),
        organization_id=org.id,
        user_id=user.id,
        role=role,
        is_default=True,
    ))
    db.commit()
    return {
        "Authorization": (
            "Bearer " + create_access_token(user_id=user.id, org_id=org.id)
        )
    }


def _admin_headers(db) -> dict[str, str]:
    return _role_headers(db, MemberRole.admin)


def test_confirmed_signal_creates_ranked_reviewable_parcel_search(client, db, tmp_path):
    deal, source_data, match = _setup_confirmed_signal(client, db, tmp_path)
    source = db.get(IngestionSource, source_data["id"])
    raw = db.query(RawSourceRecord).one()
    _add_parcel(
        db, source.id, raw.id, "P-NEAR", -97.735,
        land_area_sq_ft=80_000,
        land_value=1_000_000,
        improvement_value=100_000,
        zoning_code="Commercial Retail",
        land_use="Retail",
    )
    _add_parcel(
        db, source.id, raw.id, "P-MID", -97.72,
        land_area_sq_ft=80_000,
        land_value=1_000_000,
        improvement_value=100_000,
        zoning_code="Commercial Retail",
        land_use="Retail",
    )
    _add_parcel(
        db, source.id, raw.id, "P-FAR", -97.62,
        land_area_sq_ft=80_000,
        land_value=1_000_000,
        improvement_value=100_000,
        zoning_code="Commercial Retail",
        land_use="Retail",
    )
    db.commit()

    response = client.post(
        f"/deals/{deal['id']}/nearby-parcel-searches",
        json={
            "anchor_brand_match_id": match.id,
            "radius_miles": 2,
            "persona": "developer",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["anchor_latitude"] == 30.2672
    assert [row["parcel"]["external_parcel_id"] for row in body["candidates"]] == [
        "P-NEAR", "P-MID"
    ]
    assert body["candidates"][0]["distance_miles"] < body["candidates"][1]["distance_miles"]
    assert body["candidates"][0]["facts"][0]["source_url"].startswith("https://")
    candidate_id = body["candidates"][0]["id"]

    reviewed = client.patch(
        f"/parcel-candidates/{candidate_id}", json={"review_status": "shortlisted"}
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["review_status"] == "shortlisted"
    assert db.query(AuditLog).filter(
        AuditLog.entity_type == "nearby_parcel_candidate",
        AuditLog.entity_id == candidate_id,
    ).count() == 1
    history = client.get(f"/deals/{deal['id']}/nearby-parcel-searches")
    assert history.status_code == 200
    assert history.json()[0]["id"] == body["id"]

    for persona in ("broker", "realtor"):
        persona_search = client.post(
            f"/deals/{deal['id']}/nearby-parcel-searches",
            json={
                "anchor_brand_match_id": match.id,
                "radius_miles": 2,
                "persona": persona,
            },
        )
        assert persona_search.status_code == 201, persona_search.text
        persona_body = persona_search.json()
        assert persona_body["ranker_version"] == f"{persona}-v2"
        assert persona_body["candidates"][0]["explanation"]["ranker_version"] == f"{persona}-v2"
        assert "No owner willingness to sell" in persona_body["candidates"][0]["explanation"]["cautions"][0]


def test_nearby_parcel_export_is_policy_gated_safe_and_audited(
    client, db, tmp_path
):
    headers = _admin_headers(db)
    deal, source_data, match = _setup_confirmed_signal(
        client, db, tmp_path, headers=headers
    )
    source = db.get(IngestionSource, source_data["id"])
    source.settings = {
        **(source.settings or {}),
        "export_policy": "derived_nearby_parcel_context_only_no_raw_delaware_firstmap_resale",
    }
    raw = db.query(RawSourceRecord).one()
    parcel = _add_parcel(
        db,
        source.id,
        raw.id,
        "P-EXPORT",
        -97.735,
        land_area_sq_ft=80_000,
        zoning_code="Commercial Retail",
        land_use="Retail",
    )
    parcel.address = '=HYPERLINK("https://bad.example","click")'
    db.commit()
    created = client.post(
        f"/deals/{deal['id']}/nearby-parcel-searches",
        headers=headers,
        json={
            "anchor_brand_match_id": match.id,
            "radius_miles": 2,
            "persona": "developer",
        },
    )
    assert created.status_code == 201, created.text
    search_id = created.json()["id"]

    response = client.post(
        f"/nearby-parcel-searches/{search_id}/export", headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["x-exported-count"] == "1"
    assert response.headers["x-omitted-count"] == "0"
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 1
    assert rows[0]["external_parcel_id"] == "P-EXPORT"
    assert rows[0]["address"].startswith("'=")
    assert "owner" not in rows[0]
    assert "geometry" not in rows[0]
    audit = db.query(AuditLog).filter_by(
        entity_type="nearby_parcel_search",
        entity_id=search_id,
        action="export",
    ).one()
    values = json.loads(audit.new_values)
    assert values["exported_count"] == 1
    assert values["omitted_count"] == 0
    assert values["ownership_included"] is False
    assert values["raw_geometry_included"] is False
    assert values["candidate_ids"] == [created.json()["candidates"][0]["id"]]
    assert len(values["content_sha256"]) == 64
    assert values["policy_decisions"][source.key]["approved"] is True
    assert audit.request_id


def test_nearby_parcel_export_fails_closed_without_reviewed_policy(
    client, db, tmp_path
):
    headers = _admin_headers(db)
    deal, source_data, match = _setup_confirmed_signal(
        client, db, tmp_path, headers=headers
    )
    source = db.get(IngestionSource, source_data["id"])
    raw = db.query(RawSourceRecord).one()
    _add_parcel(
        db,
        source.id,
        raw.id,
        "P-BLOCKED",
        -97.735,
        zoning_code="Commercial Retail",
    )
    db.commit()
    created = client.post(
        f"/deals/{deal['id']}/nearby-parcel-searches",
        headers=headers,
        json={
            "anchor_brand_match_id": match.id,
            "radius_miles": 2,
            "persona": "developer",
        },
    )
    assert created.status_code == 201, created.text

    response = client.post(
        f"/nearby-parcel-searches/{created.json()['id']}/export",
        headers=headers,
    )

    assert response.status_code == 422
    assert "No candidates are exportable" in response.json()["detail"]
    denied = db.query(AuditLog).filter_by(action="export_denied").one()
    assert json.loads(denied.new_values)["reason"] == "no_reviewed_active_source_policy"


def test_nearby_parcel_export_rejects_malformed_policy_and_inactive_source(
    client, db, tmp_path
):
    headers = _admin_headers(db)
    deal, source_data, match = _setup_confirmed_signal(
        client, db, tmp_path, headers=headers
    )
    source = db.get(IngestionSource, source_data["id"])
    source.settings = {
        **(source.settings or {}),
        "export_policy": "derived_nearby_parcel_context_raw_export_allowed",
    }
    raw = db.query(RawSourceRecord).one()
    _add_parcel(db, source.id, raw.id, "P-MALFORMED", -97.735)
    db.commit()
    created = client.post(
        f"/deals/{deal['id']}/nearby-parcel-searches",
        headers=headers,
        json={
            "anchor_brand_match_id": match.id,
            "radius_miles": 2,
            "persona": "developer",
        },
    )
    assert created.status_code == 201, created.text
    search_id = created.json()["id"]

    assert derived_export_fields(source.settings) == frozenset()
    malformed = client.post(
        f"/nearby-parcel-searches/{search_id}/export", headers=headers
    )
    assert malformed.status_code == 422

    source.settings = {
        **(source.settings or {}),
        "export_policy": "derived_nearby_parcel_context_only_no_raw_delaware_firstmap_resale",
    }
    source.is_active = False
    db.commit()
    inactive = client.post(
        f"/nearby-parcel-searches/{search_id}/export", headers=headers
    )
    assert inactive.status_code == 422
    decisions = json.loads(
        db.query(AuditLog)
        .filter_by(action="export_denied")
        .order_by(AuditLog.created_at.desc())
        .first()
        .new_values
    )["policy_decisions"]
    assert decisions[source.key]["active"] is False


def test_nearby_parcel_export_requires_editor_or_admin(client, db):
    response = client.post(
        "/nearby-parcel-searches/does-not-matter/export",
        headers=_role_headers(db, MemberRole.viewer),
    )

    assert response.status_code == 403


def test_acquisition_radar_deduplicates_and_prioritizes_cross_opportunity_parcels(
    client, db, tmp_path
):
    deal, source_data, match = _setup_confirmed_signal(client, db, tmp_path)
    source = db.get(IngestionSource, source_data["id"])
    raw = db.query(RawSourceRecord).one()
    parcel = _add_parcel(
        db,
        source.id,
        raw.id,
        "P-RADAR",
        -97.735,
        land_area_sq_ft=80_000,
        land_value=1_000_000,
        improvement_value=100_000,
        zoning_code="Commercial Retail",
        land_use="Retail",
    )
    db.commit()
    first_response = client.post(
        f"/deals/{deal['id']}/nearby-parcel-searches",
        json={
            "anchor_brand_match_id": match.id,
            "radius_miles": 2,
            "persona": "developer",
        },
    )
    assert first_response.status_code == 201, first_response.text
    first = db.get(NearbyParcelSearch, first_response.json()["id"])
    first_candidate = db.query(NearbyParcelCandidate).filter_by(
        search_id=first.id,
        parcel_id=parcel.id,
    ).one()

    second_deal = client.post("/deals", json={
        "name": "Second Main Street signal",
        "address": "200 Main Street",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
        "property_type": "retail",
    }).json()
    second_search = NearbyParcelSearch(
        organization_id="default-org",
        deal_id=second_deal["id"],
        anchor_brand_match_id=first.anchor_brand_match_id,
        anchor_permit_id=first.anchor_permit_id,
        anchor_latitude=first.anchor_latitude,
        anchor_longitude=first.anchor_longitude,
        radius_miles=first.radius_miles,
        persona="broker",
        filters={},
        result_limit=25,
        as_of=datetime.now(timezone.utc),
        ranker_version="broker-v2",
    )
    db.add(second_search)
    db.flush()
    db.add(NearbyParcelCandidate(
        organization_id="default-org",
        search_id=second_search.id,
        parcel_id=parcel.id,
        rank=1,
        distance_miles=0.4,
        score=88,
        score_confidence=0.92,
        explanation={"reasons": ["Repeated market signal"], "cautions": []},
        review_status="shortlisted",
        ranker_version="broker-v2",
    ))
    db.commit()

    response = client.get("/acquisition-radar?state=TX")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["summary"] == {
        "total_parcels": 1,
        "shortlisted_parcels": 1,
        "multi_opportunity_parcels": 1,
        "assigned_parcels": 0,
        "state_count": 1,
    }
    item = body["items"][0]
    assert item["parcel"]["external_parcel_id"] == "P-RADAR"
    assert item["opportunity_count"] == 2
    assert item["appearance_count"] == 2
    assert item["personas"] == ["broker", "developer"]
    assert item["review_status"] == "shortlisted"
    assert item["radar_score"] > first_candidate.score * 0.45
    assert {signal["deal_name"] for signal in item["signals"]} == {
        "Main Street signal",
        "Second Main Street signal",
    }
    assert "Appears near 2 opportunities" in item["reasons"]

    filtered = client.get("/acquisition-radar?persona=developer&review_status=candidate")
    assert filtered.status_code == 200
    assert filtered.json()["items"][0]["opportunity_count"] == 1


def test_shortlisted_candidate_can_be_assigned_to_a_member(client, db, tmp_path):
    org = Organization(id="default-org", name="Default Org", slug="default-org", is_active=True)
    db.add(org)
    admin_user = User(
        id=str(uuid4()),
        email="admin@acme.com",
        full_name="Admin",
        password_hash=hash_password("CorrectHorseBattery42"),
        is_active=True,
    )
    teammate_user = User(
        id=str(uuid4()),
        email="teammate@acme.com",
        full_name="Teammate",
        password_hash=hash_password("CorrectHorseBattery42"),
        is_active=True,
    )
    db.add(admin_user)
    db.add(teammate_user)
    db.add(OrganizationMembership(
        id=str(uuid4()),
        organization_id=org.id,
        user_id=admin_user.id,
        role=MemberRole.admin,
        is_default=True,
    ))
    db.add(OrganizationMembership(
        id=str(uuid4()),
        organization_id=org.id,
        user_id=teammate_user.id,
        role=MemberRole.editor,
        is_default=False,
    ))
    db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user_id=admin_user.id, org_id=org.id)}"}

    deal, source_data, match = _setup_confirmed_signal(client, db, tmp_path, headers=headers)
    source = db.get(IngestionSource, source_data["id"])
    raw = db.query(RawSourceRecord).one()
    _add_parcel(
        db,
        source.id,
        raw.id,
        "P-ASSIGN",
        -97.735,
        organization_id=org.id,
        land_area_sq_ft=80_000,
        land_value=1_000_000,
        improvement_value=100_000,
        zoning_code="Commercial Retail",
        land_use="Retail",
    )
    db.commit()

    response = client.post(
        f"/deals/{deal['id']}/nearby-parcel-searches",
        headers=headers,
        json={
            "anchor_brand_match_id": match.id,
            "radius_miles": 2,
            "persona": "developer",
            "limit": 5,
        },
    )
    assert response.status_code == 201, response.text
    candidate_id = response.json()["candidates"][0]["id"]

    reviewed = client.patch(
        f"/parcel-candidates/{candidate_id}",
        headers=headers,
        json={"review_status": "shortlisted"},
    )
    assert reviewed.status_code == 200, reviewed.text

    assigned = client.patch(
        f"/parcel-candidates/{candidate_id}/assignment",
        headers=headers,
        json={"assigned_to_user_id": teammate_user.id},
    )
    assert assigned.status_code == 200, assigned.text
    body = assigned.json()
    assert body["assigned_to_user_id"] == teammate_user.id
    assert body["assigned_to_name"] == "Teammate"
    assert body["assigned_by_user_id"] == admin_user.id
    assert body["assigned_at"]


def test_shortlisted_candidate_promotes_into_a_live_opportunity(client, db, tmp_path):
    org = Organization(id="default-org", name="Default Org", slug="default-org", is_active=True)
    db.add(org)
    admin_user = User(
        id=str(uuid4()),
        email="admin@acme.com",
        full_name="Admin",
        password_hash=hash_password("CorrectHorseBattery42"),
        is_active=True,
    )
    db.add(admin_user)
    db.add(OrganizationMembership(
        id=str(uuid4()),
        organization_id=org.id,
        user_id=admin_user.id,
        role=MemberRole.admin,
        is_default=True,
    ))
    db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user_id=admin_user.id, org_id=org.id)}"}

    deal, source_data, match = _setup_confirmed_signal(client, db, tmp_path, headers=headers)
    source = db.get(IngestionSource, source_data["id"])
    raw = db.query(RawSourceRecord).one()
    _add_parcel(
        db,
        source.id,
        raw.id,
        "P-PROMOTE",
        -97.735,
        organization_id=org.id,
        land_area_sq_ft=80_000,
        land_value=1_000_000,
        improvement_value=100_000,
        zoning_code="Commercial Retail",
        land_use="Retail",
    )
    db.commit()

    response = client.post(
        f"/deals/{deal['id']}/nearby-parcel-searches",
        headers=headers,
        json={
            "anchor_brand_match_id": match.id,
            "radius_miles": 2,
            "persona": "developer",
            "limit": 5,
        },
    )
    assert response.status_code == 201, response.text
    candidate_id = response.json()["candidates"][0]["id"]

    reviewed = client.patch(
        f"/parcel-candidates/{candidate_id}",
        headers=headers,
        json={"review_status": "shortlisted"},
    )
    assert reviewed.status_code == 200, reviewed.text

    promoted = client.post(
        f"/parcel-candidates/{candidate_id}/opportunity",
        headers=headers,
        json={"name": "125 Main St Opportunity"},
    )
    assert promoted.status_code == 200, promoted.text
    body = promoted.json()
    assert body["created"] is True
    assert body["candidate_id"] == candidate_id
    assert body["deal"]["name"] == "125 Main St Opportunity"
    assert body["deal"]["address"] == "P-PROMOTE Congress Ave"

    graph = client.get(f"/deals/{body['deal']['id']}/graph-context", headers=headers)
    assert graph.status_code == 200, graph.text
    payload = graph.json()
    assert payload["parcels"]
    assert payload["parcels"][0]["entity"]["display_name"] == "P-PROMOTE"


def test_search_requires_confirmation_and_enforces_radius(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    deal, _source, match = _setup_confirmed_signal(client, db, tmp_path, confirm=False)
    match.permit.approval_stage = "approved"
    db.commit()
    client.patch(
        f"/permit-brand-matches/{match.id}", json={"review_status": "candidate"}
    )
    unconfirmed = client.post(
        f"/deals/{deal['id']}/nearby-parcel-searches",
        json={"anchor_brand_match_id": match.id, "radius_miles": 2},
    )
    assert unconfirmed.status_code == 422
    too_wide = client.post(
        f"/deals/{deal['id']}/nearby-parcel-searches",
        json={"anchor_brand_match_id": match.id, "radius_miles": 5.1},
    )
    assert too_wide.status_code == 422
    match.review_status = "confirmed"
    db.commit()
    widest_valid = client.post(
        f"/deals/{deal['id']}/nearby-parcel-searches",
        json={"anchor_brand_match_id": match.id, "radius_miles": 5.0},
    )
    assert widest_valid.status_code == 201, widest_valid.text


def test_preapproval_signal_can_seed_nearby_parcel_context(client, db, tmp_path):
    deal, source_data, match = _setup_confirmed_signal(
        client,
        db,
        tmp_path,
        confirm=False,
    )
    source = db.get(IngestionSource, source_data["id"])
    raw = db.query(RawSourceRecord).one()
    _add_parcel(
        db, source.id, raw.id, "P-PREAPPROVAL-NEAR", -97.735,
        land_area_sq_ft=80_000,
        land_value=1_000_000,
        improvement_value=100_000,
        zoning_code="Commercial Retail",
        land_use="Retail",
    )
    db.commit()

    response = client.post(
        f"/deals/{deal['id']}/nearby-parcel-searches",
        json={
            "anchor_brand_match_id": match.id,
            "radius_miles": 2,
            "persona": "developer",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["anchor_brand_match_id"] == match.id
    assert [row["parcel"]["external_parcel_id"] for row in body["candidates"]] == ["P-PREAPPROVAL-NEAR"]


def test_nearby_parcel_search_applies_filters(client, db, tmp_path):
    deal, source_data, match = _setup_confirmed_signal(client, db, tmp_path)
    source = db.get(IngestionSource, source_data["id"])
    raw = db.query(RawSourceRecord).one()
    _add_parcel(
        db, source.id, raw.id, "P-FILTER-LOW", -97.735,
        land_area_sq_ft=40_000,
        land_value=800_000,
        improvement_value=90_000,
        zoning_code="Commercial Retail",
        land_use="Retail",
    )
    _add_parcel(
        db, source.id, raw.id, "P-FILTER-ZONE", -97.734,
        land_area_sq_ft=90_000,
        land_value=950_000,
        improvement_value=100_000,
        zoning_code="Industrial",
        land_use="Retail",
    )
    _add_parcel(
        db, source.id, raw.id, "P-FILTER-KEEP", -97.733,
        land_area_sq_ft=95_000,
        land_value=1_000_000,
        improvement_value=120_000,
        zoning_code="Commercial Retail",
        land_use="Retail",
    )
    db.commit()

    response = client.post(
        f"/deals/{deal['id']}/nearby-parcel-searches",
        json={
            "anchor_brand_match_id": match.id,
            "radius_miles": 2,
            "persona": "developer",
            "minimum_land_area_sq_ft": 80_000,
            "zoning_codes": ["Commercial Retail"],
            "land_uses": ["Retail"],
            "limit": 10,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert [row["parcel"]["external_parcel_id"] for row in body["candidates"]] == [
        "P-FILTER-KEEP"
    ]


def test_creating_opportunity_from_geocoded_signal_auto_seeds_parcel_context(client, db, tmp_path):
    source_data, match = _setup_unlinked_geocoded_signal(client, db, tmp_path)
    source = db.get(IngestionSource, source_data["id"])
    raw = db.query(RawSourceRecord).one()
    _add_parcel(
        db, source.id, raw.id, "P-AUTO-NEAR", -97.735,
        land_area_sq_ft=70_000,
        land_value=900_000,
        improvement_value=120_000,
        zoning_code="Commercial Retail",
        land_use="Retail",
    )
    _add_parcel(
        db, source.id, raw.id, "P-AUTO-MID", -97.722,
        land_area_sq_ft=90_000,
        land_value=1_100_000,
        improvement_value=150_000,
        zoning_code="Commercial Retail",
        land_use="Retail",
    )
    db.commit()

    created = client.post(f"/permit-brand-matches/{match.id}/opportunity", json={})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["created"] is True
    assert body["nearby_parcel_search"] is not None
    assert body["nearby_parcel_search"]["persona"] == "developer"
    assert body["nearby_parcel_search"]["radius_miles"] == 2.0
    assert [row["persona"] for row in body["nearby_parcel_searches"]] == [
        "developer", "broker", "realtor"
    ]

    deal_id = body["deal"]["id"]
    history = client.get(f"/deals/{deal_id}/nearby-parcel-searches")
    assert history.status_code == 200, history.text
    assert {row["persona"] for row in history.json()[:3]} == {"developer", "broker", "realtor"}
    assert any(row["id"] == body["nearby_parcel_search"]["id"] for row in history.json())

    search = client.get(f"/nearby-parcel-searches/{body['nearby_parcel_search']['id']}")
    assert search.status_code == 200, search.text
    assert [row["parcel"]["external_parcel_id"] for row in search.json()["candidates"]] == [
        "P-AUTO-NEAR", "P-AUTO-MID"
    ]
    broker_search_id = next(
        row["id"] for row in body["nearby_parcel_searches"] if row["persona"] == "broker"
    )
    broker_search = client.get(f"/nearby-parcel-searches/{broker_search_id}")
    assert broker_search.status_code == 200, broker_search.text
    assert broker_search.json()["ranker_version"] == "broker-v2"


def test_approved_signals_also_seed_nearby_parcel_context(client, db, tmp_path):
    source_data, match = _setup_unlinked_geocoded_signal(client, db, tmp_path)
    source = db.get(IngestionSource, source_data["id"])
    raw = db.query(RawSourceRecord).one()
    client.patch(
        f"/permit-brand-matches/{match.id}", json={"review_status": "confirmed"}
    )
    match.permit.approval_stage = "approved"
    _add_parcel(
        db, source.id, raw.id, "P-APPROVED-NEAR", -97.735,
        land_area_sq_ft=85_000,
        land_value=1_050_000,
        improvement_value=125_000,
        zoning_code="Commercial Retail",
        land_use="Retail",
    )
    db.commit()

    created = client.post(f"/permit-brand-matches/{match.id}/opportunity", json={})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["nearby_parcel_search"] is not None
    assert body["nearby_parcel_search"]["persona"] == "developer"
    search = client.get(f"/nearby-parcel-searches/{body['nearby_parcel_search']['id']}")
    assert search.status_code == 200, search.text
    assert [row["parcel"]["external_parcel_id"] for row in search.json()["candidates"]] == [
        "P-APPROVED-NEAR"
    ]


def test_haversine_and_missing_data_ranking_are_deterministic():
    assert round(haversine_miles(30.2672, -97.7431, 30.2672, -97.7431), 8) == 0
    parcel = ParcelRecord(
        organization_id="default-org",
        source_id="source",
        latest_raw_record_id="raw",
        external_parcel_id="P-MISSING",
        latitude=30.2672,
        longitude=-97.7431,
        last_verified_at=datetime.now(timezone.utc),
    )
    ranked = rank_developer_candidate(
        parcel, [], distance_miles=1, radius_miles=2
    )
    assert ranked.score == 20
    assert ranked.confidence == 0.4
    assert len(ranked.explanation["cautions"]) == 3
    assert not any("favorable" in reason for reason in ranked.explanation["reasons"])


def test_physical_parcel_grouping_collapses_condo_tax_accounts(client, db, tmp_path):
    _deal, source_data, _match = _setup_confirmed_signal(client, db, tmp_path)
    source = db.get(IngestionSource, source_data["id"])
    raw = db.query(RawSourceRecord).one()
    parent = _add_parcel(
        db, source.id, raw.id, "PHYSICAL-1", -97.735,
        parcel_group_id="PHYSICAL-1", land_area_sq_ft=100_000,
    )
    _add_parcel(
        db, source.id, raw.id, "UNIT-101", -97.735,
        parcel_group_id="PHYSICAL-1", land_area_sq_ft=100_000,
    )
    _add_parcel(
        db, source.id, raw.id, "UNIT-102", -97.735,
        parcel_group_id="PHYSICAL-1", land_area_sq_ft=100_000,
    )
    second_source = IngestionSource(
        organization_id="default-org", key="second_assessor",
        name="Second assessor", adapter="csv", record_type="parcel",
    )
    db.add(second_source)
    db.flush()
    other = _add_parcel(
        db, second_source.id, raw.id, "OTHER-SOURCE-PARCEL", -97.736,
        parcel_group_id="PHYSICAL-1", land_area_sq_ft=100_000,
    )
    db.commit()

    nearby = find_nearby_parcels(
        db, latitude=30.2672, longitude=-97.7431, radius_miles=2
    )

    assert len(nearby) == 2
    assert {row[0].id for row in nearby} == {parent.id, other.id}


def test_market_ranker_uses_sale_tenure_without_inferring_intent():
    as_of = datetime(2026, 7, 17, tzinfo=timezone.utc)
    parcel = ParcelRecord(
        organization_id="default-org",
        source_id="source",
        latest_raw_record_id="raw",
        external_parcel_id="P-TENURE",
        latitude=30.2672,
        longitude=-97.7431,
        last_verified_at=as_of,
    )
    sale = ParcelFact(
        id="sale-fact", organization_id="default-org", parcel_id="parcel",
        raw_source_record_id="raw", fact_type="last_sale",
        value={"last_sale_date": "2011-07-17T00:00:00+00:00"},
        source_system="assessor", confidence=1.0, observed_at=as_of,
        last_verified_at=as_of, valid_from=as_of, is_current=True,
    )

    ranked = rank_parcel_candidate(
        parcel, [sale], persona="broker", distance_miles=1, radius_miles=2
    )

    tenure = next(
        feature for feature in ranked.explanation["features"]
        if feature["name"] == "ownership_tenure"
    )
    assert tenure["score"] == 15
    assert any("15 years of tenure" in reason for reason in ranked.explanation["reasons"])
    assert ranked.explanation["cautions"][0] == (
        "No owner willingness to sell or listing intent is inferred"
    )


def test_parcel_ingestion_versions_fact_evidence(client, db, tmp_path):
    _deal, source_data, _match = _setup_confirmed_signal(client, db, tmp_path)
    source = db.get(IngestionSource, source_data["id"])
    first_raw = db.query(RawSourceRecord).one()
    now = datetime.now(timezone.utc)
    parcel, action = upsert_parcel_snapshot(
        db,
        source=source,
        raw_record=first_raw,
        external_parcel_id="ASSESSOR-1",
        values={
            "address": "300 Main St", "city": "Austin", "state": "TX",
            "latitude": 30.27, "longitude": -97.74, "zoning_code": "CS",
        },
        facts=[ParcelFactInput(
            fact_type="ownership",
            value={"owner": "Original Owner LLC"},
            field_path="owner_name",
            observed_at=now,
        )],
        verified_at=now,
    )
    assert action == "created"
    second_raw = RawSourceRecord(
        organization_id="default-org",
        source_id=source.id,
        run_id=first_raw.run_id,
        external_record_id="parcel-ASSESSOR-1",
        record_type="parcel",
        content_hash="f" * 64,
        payload={"owner_name": "New Owner LLC"},
        received_at=now,
    )
    db.add(second_raw)
    db.flush()
    updated, action = upsert_parcel_snapshot(
        db,
        source=source,
        raw_record=second_raw,
        external_parcel_id="ASSESSOR-1",
        values={
            "address": "300 Main St", "city": "Austin", "state": "TX",
            "latitude": 30.27, "longitude": -97.74, "zoning_code": "CS",
        },
        facts=[ParcelFactInput(
            fact_type="ownership",
            value={"owner": "New Owner LLC"},
            field_path="owner_name",
            observed_at=now,
        )],
        verified_at=now,
    )
    db.flush()
    assert updated.id == parcel.id
    assert action == "updated"
    versions = db.query(ParcelFact).filter(
        ParcelFact.parcel_id == parcel.id,
        ParcelFact.fact_type == "ownership",
    ).order_by(ParcelFact.created_at).all()
    assert len(versions) == 2
    assert versions[0].is_current is False
    assert versions[0].valid_to is not None
    assert versions[1].is_current is True
    assert versions[1].raw_source_record_id == second_raw.id


def test_parcel_snapshot_geometry_surfaces_as_boundary_geometry(db):
    from app.models.ingestion import IngestionRun, IngestionSource, RawSourceRecord
    from app.services.parcel_ingestion import upsert_parcel_snapshot

    now = datetime.now(timezone.utc)
    source = IngestionSource(
        organization_id="default-org",
        key="geometry-parcels",
        name="Geometry Parcels",
        adapter="arcgis",
        record_type="parcel",
        settings={
            "export_policy": "derived_nearby_parcel_context_only_no_raw_test_resale",
        },
    )
    db.add(source)
    db.flush()
    run = IngestionRun(organization_id="default-org", source_id=source.id, status="completed")
    db.add(run)
    db.flush()
    raw = RawSourceRecord(
        organization_id="default-org",
        source_id=source.id,
        run_id=run.id,
        external_record_id="parcel-geometry-1",
        record_type="parcel",
        content_hash="g" * 64,
        payload={"pin": "0600500019"},
        received_at=now,
    )
    db.add(raw)
    db.flush()

    parcel, action = upsert_parcel_snapshot(
        db,
        source=source,
        raw_record=raw,
        external_parcel_id="0600500019",
        values={
            "address": "125 Main St",
            "city": "Wilmington",
            "state": "DE",
            "latitude": 39.8350529,
            "longitude": -75.5210446,
        },
        facts=[],
        verified_at=now,
        attributes={
            "geometry": {
                "rings": [[
                    [-75.52092528443355, 39.83522338557626],
                    [-75.52081899307417, 39.834910673876756],
                    [-75.52127695600264, 39.83496886694226],
                    [-75.52116505466434, 39.83526917634252],
                    [-75.52092528443355, 39.83522338557626],
                ]],
            },
        },
    )

    assert action == "created"
    assert parcel.boundary_geometry is not None
    assert parcel.boundary_geometry["type"] == "Polygon"
    assert len(parcel.boundary_geometry["coordinates"][0]) == 5


def test_parcel_source_runs_through_snapshot_ingestion(client, db, tmp_path):
    csv_path = tmp_path / "assessor.csv"
    csv_path.write_text(
        "parcel,address,city,state,lat,lon,acres,land_value,improvement_value,owner\n"
        "P-100,300 Main St,Austin,TX,30.2700,-97.7400,2,900000,100000,Original Owner LLC\n"
    )
    payload = {
        "key": "travis_assessor_test",
        "name": "Travis assessor test",
        "adapter": "csv",
        "record_type": "parcel",
        "jurisdiction": "Travis County",
        "base_url": str(csv_path),
        "settings": {
            "connector": {"page_size": 100},
            "reconciliation_mode": "daily_full_snapshot",
            "allow_empty_snapshot": True,
            "max_snapshot_retirement_fraction": 1.0,
        },
        "field_mappings": [
            {"source_field": source, "canonical_field": canonical, **options}
            for source, canonical, options in (
                ("parcel", "source_record_id", {"is_required": True}),
                ("address", "address", {}),
                ("city", "city", {}),
                ("state", "state", {}),
                ("lat", "latitude", {"is_required": True}),
                ("lon", "longitude", {"is_required": True}),
                (
                    "acres",
                    "land_area_sq_ft",
                    {"transform": "multiply", "transform_options": {"factor": 43560}},
                ),
                ("land_value", "land_value", {}),
                ("improvement_value", "improvement_value", {}),
                ("owner", "owner_name", {}),
            )
        ],
    }
    source = client.post("/ingestion/sources", json=payload)
    assert source.status_code == 201, source.text
    source_id = source.json()["id"]
    canary = client.post(
        f"/ingestion/sources/{source_id}/canary", json={"sample_size": 1}
    )
    assert canary.status_code == 200, canary.text
    assert canary.json()["approval_stages"] == {"parcel_snapshot": 1}

    first = client.post(f"/ingestion/sources/{source_id}/runs", json={"max_pages": 1})
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "completed", first.text
    parcel = db.query(ParcelRecord).one()
    assert parcel.external_parcel_id == "P-100"
    assert float(parcel.land_area_sq_ft) == 87120
    assert parcel.is_active is True
    ownership = db.query(ParcelFact).filter(ParcelFact.fact_type == "ownership").one()
    assert ownership.value["owner_name"] == "Original Owner LLC"
    assert ownership.source_url == str(csv_path)
    graph_types = {entity.entity_type.value for entity in db.query(GraphEntity).all()}
    assert {"parcel", "owner"}.issubset(graph_types)
    owner_relationship = db.query(GraphRelationship).filter(
        GraphRelationship.relationship_type == "owned_by"
    ).one()
    assert owner_relationship.is_current is True
    assert db.query(GraphRelationshipEvidence).filter(
        GraphRelationshipEvidence.relationship_id == owner_relationship.id
    ).count() == 1
    first_observed_at = db.query(RawSourceRecordObservation).one().last_observed_at
    first_raw_id = db.query(RawSourceRecord).one().id

    unchanged = client.post(f"/ingestion/sources/{source_id}/runs", json={"max_pages": 1})
    assert unchanged.status_code == 201, unchanged.text
    db.expire_all()
    relationships = db.query(GraphRelationship).filter(
        GraphRelationship.relationship_type == "owned_by"
    ).all()
    assert len(relationships) == 1
    assert relationships[0].id == owner_relationship.id
    assert relationships[0].is_current is True
    assert db.query(RawSourceRecord).count() == 1
    assert db.query(RawSourceRecordObservation).count() == 1
    assert (
        db.query(RawSourceRecordObservation).one().last_observed_at
        > first_observed_at
    )

    csv_path.write_text(
        "parcel,address,city,state,lat,lon,acres,land_value,improvement_value,owner\n"
        "P-100,300 Main St,Austin,TX,30.2700,-97.7400,2,900000,100000,Replacement Owner LLC\n"
    )
    changed = client.post(f"/ingestion/sources/{source_id}/runs", json={"max_pages": 1})
    assert changed.status_code == 201, changed.text
    assert changed.json()["records_updated"] == 1
    assert db.query(RawSourceRecord).count() == 2
    assert db.query(RawSourceRecordObservation).count() == 2
    assert db.query(ParcelFact).filter(
        ParcelFact.fact_type == "ownership",
        ParcelFact.is_current.is_(True),
    ).one().value["owner_name"] == "Replacement Owner LLC"

    csv_path.write_text(
        "parcel,address,city,state,lat,lon,acres,land_value,improvement_value,owner\n"
        "P-100,300 Main St,Austin,TX,30.2700,-97.7400,2,900000,100000,Original Owner LLC\n"
    )
    reverted = client.post(f"/ingestion/sources/{source_id}/runs", json={"max_pages": 1})
    assert reverted.status_code == 201, reverted.text
    assert reverted.json()["records_updated"] == 1
    db.expire_all()
    parcel = db.query(ParcelRecord).one()
    assert parcel.latest_raw_record_id == first_raw_id
    current_ownership = db.query(ParcelFact).filter(
        ParcelFact.fact_type == "ownership",
        ParcelFact.is_current.is_(True),
    ).one()
    assert current_ownership.raw_source_record_id == first_raw_id
    assert current_ownership.value["owner_name"] == "Original Owner LLC"
    ownership_versions = db.query(ParcelFact).filter(
        ParcelFact.fact_type == "ownership"
    ).order_by(ParcelFact.valid_from.asc()).all()
    assert len(ownership_versions) == 3
    assert ownership_versions[0].raw_source_record_id == first_raw_id
    assert ownership_versions[0].valid_to is not None
    assert ownership_versions[1].valid_to is not None
    assert ownership_versions[2].raw_source_record_id == first_raw_id
    assert ownership_versions[2].valid_to is None
    assert ownership_versions[2].is_current is True
    assert db.query(RawSourceRecord).count() == 2
    assert db.query(RawSourceRecordObservation).count() == 2

    csv_path.write_text(
        "parcel,address,city,state,lat,lon,acres,land_value,improvement_value,owner\n"
    )
    retired = client.post(f"/ingestion/sources/{source_id}/runs", json={"max_pages": 1})
    assert retired.status_code == 201, retired.text
    db.expire_all()
    assert db.query(ParcelRecord).one().is_active is False
    assert db.get(GraphRelationship, owner_relationship.id).is_current is False

    csv_path.write_text(
        "parcel,address,city,state,lat,lon,acres,land_value,improvement_value,owner\n"
        "P-100,300 Main St,Austin,TX,30.2700,-97.7400,2,900000,100000,Original Owner LLC\n"
    )
    restored = client.post(f"/ingestion/sources/{source_id}/runs", json={"max_pages": 1})
    assert restored.status_code == 201, restored.text
    db.expire_all()
    assert db.query(ParcelRecord).one().is_active is True
    assert db.get(GraphRelationship, owner_relationship.id).is_current is True


def test_parcel_snapshot_rejects_unsafe_mass_retirement(client, db, tmp_path):
    csv_path = tmp_path / "guarded-assessor.csv"
    header = "parcel,address,lat,lon\n"
    csv_path.write_text(
        header
        + "P-1,100 Main St,30.2700,-97.7400\n"
        + "P-2,200 Main St,30.2710,-97.7410\n"
    )
    payload = {
        "key": "guarded_assessor_test",
        "name": "Guarded assessor test",
        "adapter": "csv",
        "record_type": "parcel",
        "jurisdiction": "Travis County",
        "base_url": str(csv_path),
        "settings": {
            "connector": {"page_size": 100},
            "reconciliation_mode": "daily_full_snapshot",
            "max_snapshot_retirement_fraction": 0.25,
        },
        "field_mappings": [
            {"source_field": "parcel", "canonical_field": "source_record_id", "is_required": True},
            {"source_field": "address", "canonical_field": "address"},
            {"source_field": "lat", "canonical_field": "latitude", "is_required": True},
            {"source_field": "lon", "canonical_field": "longitude", "is_required": True},
        ],
    }
    source = client.post("/ingestion/sources", json=payload)
    assert source.status_code == 201, source.text
    source_id = source.json()["id"]
    initial = client.post(f"/ingestion/sources/{source_id}/runs", json={"max_pages": 1})
    assert initial.json()["status"] == "completed", initial.text

    csv_path.write_text(header + "P-1,100 Main St,30.2700,-97.7400\n")
    guarded = client.post(f"/ingestion/sources/{source_id}/runs", json={"max_pages": 1})
    assert guarded.status_code == 201, guarded.text
    assert guarded.json()["status"] == "failed"
    assert "50.0%" in guarded.json()["error_message"]
    db.expire_all()
    assert db.query(ParcelRecord).filter(ParcelRecord.is_active.is_(True)).count() == 2


def test_cook_county_catalog_run_persists_geometry_context_without_owner_relationship(
    client, db, monkeypatch
):
    monkeypatch.setattr(
        ingestion_service,
        "build_connector",
        lambda *_args, **_kwargs: _StaticConnector([
            {
                "pin": "17032270241105",
                "pin10": "1703227024",
                "row_id": "170322702411052026",
                "year": "2026.0",
                "class": "299",
                "triad_name": "City",
                "township_name": "North Chicago",
                "nbhd_code": "74022",
                "tax_code": "74002",
                "zip_code": "60611",
                "lon": "-87.6206525272",
                "lat": "41.897883532",
                "cook_municipality_name": "CITY OF CHICAGO",
                "ward_num": "42",
                "chicago_community_area_name": "NEAR NORTH SIDE",
                "chicago_industrial_corridor_name": "",
                "econ_enterprise_zone_num": "",
                "econ_industrial_growth_zone_num": "",
                "econ_qualified_opportunity_zone_num": "17031081403",
                "econ_central_business_district_num": "1",
                "env_flood_fema_sfha": False,
                "env_flood_fs_factor": "1",
                "env_flood_fs_risk_direction": "0",
                "env_ohare_noise_contour_no_buffer_bool": False,
                "env_ohare_noise_contour_half_mile_buffer_bool": False,
                "env_airport_noise_dnl": "",
                "tax_tif_district_num": "",
                "tax_tif_district_name": "",
                "access_cmap_walk_total_score": "134.5",
                "misc_subdivision_id": "1703A_A",
            }
        ]),
    )
    source = client.post(
        "/ingestion/sources",
        json=_catalog_source_payload("cook_county_il_assessor_parcels_current_year_nearby"),
    )
    assert source.status_code == 201, source.text

    run = client.post(f"/ingestion/sources/{source.json()['id']}/runs", json={"max_pages": 1})

    assert run.status_code == 201, run.text
    assert run.json()["records_inserted"] == 1
    parcel = db.query(ParcelRecord).one()
    assert parcel.external_parcel_id == "170322702411052026"
    assert parcel.parcel_group_id == "1703227024"
    assert parcel.state == "IL"
    assert parcel.postal_code == "60611"
    assert parcel.land_use == (
        "299 | North Chicago | CITY OF CHICAGO | NEAR NORTH SIDE | 17031081403"
    )
    assert float(parcel.latitude) == 41.897883532
    assert float(parcel.longitude) == -87.6206525272
    parcel_entity = db.query(GraphEntity).filter(GraphEntity.entity_type == "parcel").one()
    assert parcel_entity.display_name == "170322702411052026"
    assert parcel_entity.attributes["parcel_group_id"] == "1703227024"
    assert db.query(RawSourceRecord).count() == 1
    assert db.query(GraphRelationship).filter(
        GraphRelationship.relationship_type == "owned_by"
    ).count() == 0
