from datetime import datetime, timezone

import jwt
import pytest

from app import config
from app.models.graph import GraphEntity, GraphRelationship
from app.models.ingestion import (
    IngestionRun,
    IngestionSource,
    PermitEvent,
    PermitRecord,
    RawSourceRecord,
)
from app.models.organization import Organization
from app.models.parcel import ParcelRecord
from app.models.permit_geocode import PermitGeocode
from app.models.user import User
from app.services.demo_access import DEMO_ORG_ID, DEMO_USER_ID, demo_read_only
from app.services.demo_geocoding import request_url, save_match, validated_match
from app.services.demo_seed import seed_demo
from app.services.rate_limiter import limiter
from app.services.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
)
from tests.demo_fixtures import CAPTURED, create_snapshot


@pytest.fixture
def demo(db, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DEMO_ENABLED", True)
    monkeypatch.setattr("app.middleware.auth_context.ALLOW_ANONYMOUS", False)
    limiter.reset("demo:testclient")
    path = tmp_path / "snapshot.db"
    create_snapshot(path)
    assert seed_demo(db, [path]) == 1
    return path


def headers(client):
    response = client.post("/auth/demo")
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_disabled(client, monkeypatch):
    monkeypatch.setattr(config, "DEMO_ENABLED", False)
    assert client.get("/auth/demo").json() == {"enabled": False}
    assert client.post("/auth/demo").status_code == 404
    assert client.post("/auth/demo", json={"user_id": "not-accepted"}).status_code == 404


def test_enabled_without_seed_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(config, "DEMO_ENABLED", True)
    limiter.reset("demo:testclient")
    assert client.post("/auth/demo").status_code == 503


def test_token_identity_ttl_and_no_refresh(client, db, demo):
    assert client.post("/auth/demo", json={"user_id": "victim", "org_id": "victim"}).status_code == 422
    response = client.post("/auth/demo")
    assert response.status_code == 200
    body = response.json()
    claims = decode_access_token(body["access_token"])
    assert claims["sub"] == DEMO_USER_ID and claims["org_id"] == DEMO_ORG_ID
    assert claims["demo"] is True and claims["read_only"] is True
    assert 3598 <= claims["exp"] - datetime.now(timezone.utc).timestamp() <= 3601
    assert body["role"] == "viewer" and body["is_demo"] is True
    assert "Max-Age=0" in response.headers["set-cookie"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["is_demo"] is True
    claims["exp"] = 1
    expired = jwt.encode(claims, config.SECRET_KEY, algorithm=config.ALGORITHM)
    assert decode_access_token(expired) is None
    assert client.get("/demo/summary", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/deals", "/auth/switch-org", "/auth/demo", "/future-write-route", "/ingestion/sources/anything/run"])
def test_all_writes_are_denied(client, demo, method, path):
    assert client.request(method, path, headers=headers(client), json={}).status_code == 403


@pytest.mark.parametrize("path", ["/settings", "/users", "/organizations/other/members", "/invites", "/billing", "/api-keys", "/auth/organizations", "/auth/2fa/status", "/ingestion/sources", "/deals/export", "/organizations/other/export", "/graph/entities", "/future-read-route"])
def test_sensitive_reads_default_denied(client, demo, path):
    assert client.get(path, headers=headers(client)).status_code == 403


def test_seed_idempotency_and_evidence(client, db, demo):
    models = (User, Organization, PermitRecord, RawSourceRecord, PermitEvent, GraphEntity, GraphRelationship)
    counts = {model: db.query(model).count() for model in models}
    db.rollback()
    assert seed_demo(db, [demo]) == 1
    assert {model: db.query(model).count() for model in models} == counts
    user = db.get(User, DEMO_USER_ID)
    assert user.password_hash == "!nologin" and not user.totp_enabled and not user.is_superuser
    assert not any(row.is_active for row in db.query(IngestionSource).all())
    auth = headers(client)
    permits = client.get("/ingestion/permits?limit=25", headers=auth).json()
    assert len(permits) == 1
    detail = client.get(f"/ingestion/permits/{permits[0]['id']}", headers=auth).json()
    assert detail["graph_entity"] and detail["events"] and detail["graph_related"]
    assert all(row["relationship"]["evidence"] for row in detail["graph_related"])
    assert detail["permit"]["first_seen_at"].startswith(CAPTURED.date().isoformat())
    assert client.get("/demo/summary", headers=auth).json()["permit_records"] == 1
    assert client.get("/ingestion/permits?limit=500", headers=auth).status_code == 403
    assert client.post("/auth/logout", headers=auth).status_code == 204


def test_demo_overview_parcel_references_and_map_readiness(client, demo):
    auth = headers(client)
    summary = client.get("/demo/summary", headers=auth).json()
    assert summary["permit_records"] == 1
    assert summary["parcel_references"] == 1
    assert summary["parcel_records"] == 0
    assert summary["mapped_permits"] == summary["mapped_parcels"] == 0
    references = client.get("/demo/parcel-references", headers=auth).json()
    assert len(references) == 1
    assert references[0]["reference"] == "010066782"
    assert references[0]["permit_count"] == 1
    assert references[0]["sample_address"] == "55 E STATE ST"
    assert client.get("/demo/parcel-references?limit=26", headers=auth).status_code == 422
    filings = client.get("/demo/parcel-filings?reference=010066782", headers=auth).json()
    assert filings["total_filings"] == 1
    assert filings["distinct_reported_addresses"] == 1
    assert filings["filings"][0]["address"] == "55 E STATE ST"
    assert client.get("/demo/parcel-filings?reference=missing", headers=auth).json()["filings"] == []
    assert client.get("/demo/parcel-filings?reference=", headers=auth).status_code == 422
    assert client.get("/demo/map", headers=auth).json() == {
        "permits": [], "parcels": [], "limit_per_layer": 100,
    }


def test_demo_graph_neighbors_and_activity_are_scoped(client, db, demo):
    auth = headers(client)
    activity = client.get("/demo/activity", headers=auth)
    assert activity.status_code == 200
    assert activity.json()["records_considered"] == 1
    assert sum(activity.json()["stages"].values()) == 1
    assert client.get("/demo/activity").status_code == 401

    company = db.query(GraphEntity).filter(GraphEntity.entity_type == "company").first()
    assert company is not None
    related = client.get(f"/demo/graph-neighbors?entity_id={company.id}", headers=auth)
    assert related.status_code == 200
    assert related.json()["entity"]["id"] == company.id
    assert all(item["permit_id"] for item in related.json()["neighbors"])
    assert client.get("/demo/graph-neighbors?entity_id=not-a-uuid", headers=auth).status_code == 422
    assert client.get("/demo/graph-neighbors?entity_id=00000000-0000-0000-0000-000000000000", headers=auth).status_code == 404
    hubs = client.get("/demo/graph-hubs", headers=auth)
    assert hubs.status_code == 200
    assert hubs.json() == []
    assert client.get("/demo/graph-hubs").status_code == 401
    parcel = db.query(GraphEntity).filter(GraphEntity.entity_type == "parcel").first()
    paths = client.get(f"/demo/parcel-paths?entity_id={parcel.id}", headers=auth)
    assert paths.status_code == 200
    assert len(paths.json()["paths"]) == 1
    assert paths.json()["paths"][0]["permit_to_property"]["evidence"]
    assert paths.json()["paths"][0]["property_to_parcel"]["evidence"]
    assert client.get("/demo/parcel-paths?entity_id=00000000-0000-0000-0000-000000000000", headers=auth).status_code == 404


def test_demo_map_only_shows_source_permitted_boundaries(client, db, demo):
    permit = db.query(PermitRecord).first()
    permit.latitude, permit.longitude = 39.9612, -82.9988
    source = IngestionSource(organization_id=DEMO_ORG_ID, key="test-parcel-source",
                             name="Test parcel source", adapter="test", record_type="parcel",
                             settings={"export_policy": "derived_parcel_context"}, is_active=False)
    db.add(source)
    db.flush()
    run = IngestionRun(organization_id=DEMO_ORG_ID, source_id=source.id, status="completed")
    db.add(run)
    db.flush()
    raw = RawSourceRecord(organization_id=DEMO_ORG_ID, source_id=source.id, run_id=run.id,
                          external_record_id="test-1", content_hash="a" * 64, payload={})
    db.add(raw)
    db.flush()
    geometry = {"type": "Polygon", "coordinates": [[
        [-83.001, 39.960], [-83.000, 39.960], [-83.000, 39.961], [-83.001, 39.960],
    ]]}
    parcel = ParcelRecord(organization_id=DEMO_ORG_ID, source_id=source.id,
                          latest_raw_record_id=raw.id, external_parcel_id="test-1",
                          latitude=39.9605, longitude=-83.0005,
                          attributes={"geometry": geometry})
    db.add(parcel)
    db.commit()
    auth = headers(client)
    mapped = client.get("/demo/map", headers=auth)
    assert mapped.status_code == 200
    assert len(mapped.json()["permits"]) == 1
    assert mapped.json()["parcels"][0]["boundary"] == geometry
    source.settings = {"export_policy": "parcel_id_only"}
    db.commit()
    hidden = client.get("/demo/map", headers=auth)
    assert hidden.status_code == 200
    assert hidden.json()["parcels"][0]["boundary"] is None


def test_derived_geocode_is_scoped_attributed_and_invalidated(client, db, demo):
    permit = db.query(PermitRecord).first()
    permit.postal_code = "43215"
    db.commit()
    response = {"result": {"addressMatches": [{
        "matchedAddress": "55 E STATE ST, COLUMBUS, OH, 43215",
        "addressComponents": {"city": "COLUMBUS", "state": "OH", "zip": "43215"},
        "coordinates": {"x": -82.9987, "y": 39.9603},
    }]}}
    assert validated_match(permit, response)
    assert save_match(db, permit, response, request_url(permit))
    db.commit()
    auth = headers(client)
    summary = client.get("/demo/summary", headers=auth).json()
    assert summary["mapped_permits"] == summary["derived_geocoded_permits"] == 1
    assert summary["mapped_filing_locations"] == 1
    point = client.get("/demo/map", headers=auth).json()["permits"][0]
    assert point["location_method"] == "census_address_range_estimate"
    assert point["source_url"].startswith("https://geocoding.geo.census.gov/")
    assert db.query(PermitGeocode).one().response_hash
    other = Organization(id="geocode-other-org", name="Other", slug="geocode-other-org")
    db.add(other)
    db.flush()
    geocode = db.query(PermitGeocode).one()
    geocode.organization_id = other.id
    db.commit()
    assert client.get("/demo/map", headers=auth).json()["permits"] == []
    geocode.organization_id = DEMO_ORG_ID
    db.commit()
    permit.address = "57 E STATE ST"
    db.commit()
    assert client.get("/demo/map", headers=auth).json()["permits"] == []
    assert client.get("/demo/summary", headers=auth).json()["mapped_permits"] == 0
    permit.address = "55 E STATE ST"
    response["result"]["addressMatches"].append(response["result"]["addressMatches"][0])
    assert not validated_match(permit, response)
    response["result"]["addressMatches"] = [response["result"]["addressMatches"][0]]
    response["result"]["addressMatches"][0]["matchedAddress"] = "57 E STATE ST, COLUMBUS, OH, 43215"
    assert not validated_match(permit, response)
    db.rollback()


def test_cross_tenant_reads_are_scoped(client, db, demo):
    auth = headers(client)
    row = db.query(GraphEntity).first()
    row.organization_id = "other-org"
    parcel = db.query(GraphEntity).filter(GraphEntity.entity_type == "parcel").first()
    parcel.organization_id = "other-org"
    permit = db.query(PermitRecord).first()
    permit.organization_id = "other-org"
    db.commit()
    assert client.get(f"/graph/entities/{row.id}", headers=auth).status_code == 404
    assert client.get(f"/demo/graph-neighbors?entity_id={row.id}", headers=auth).status_code == 404
    assert client.get(f"/demo/parcel-paths?entity_id={parcel.id}", headers=auth).status_code == 404
    assert client.get("/demo/parcel-references", headers=auth).json() == []
    assert client.get("/demo/parcel-filings?reference=010066782", headers=auth).json()["filings"] == []
    assert client.get("/demo/map", headers=auth).json()["permits"] == []
    assert client.get("/demo/summary", headers=auth).json()["parcel_references"] == 0
    other = create_access_token(user_id=DEMO_USER_ID, org_id="other-org", demo=True)
    assert client.get("/demo/summary", headers={"Authorization": f"Bearer {other}"}).status_code == 401


def test_no_password_refresh_or_ordinary_token_escape(client, db, demo):
    user = db.get(User, DEMO_USER_ID)
    user.password_hash = hash_password("ValidButForbidden2026!")
    user.email = "demo-test@example.com"
    db.commit()
    assert client.post("/auth/login", json={"email": user.email, "password": "ValidButForbidden2026!"}).status_code == 401
    token = create_access_token(user_id=DEMO_USER_ID, org_id=DEMO_ORG_ID)
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    refresh = create_refresh_token(user_id=DEMO_USER_ID, org_id=DEMO_ORG_ID)
    client.cookies.set(config.REFRESH_COOKIE_NAME, refresh)
    assert client.post("/auth/refresh").status_code == 401
    assert client.post("/auth/demo").status_code == 503


def test_rate_limit_and_kill_switch(client, demo, monkeypatch):
    auth = headers(client)
    for _ in range(9):
        assert client.post("/auth/demo").status_code == 200
    assert client.post("/auth/demo", headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 429
    monkeypatch.setattr(config, "DEMO_ENABLED", False)
    assert client.get("/demo/summary", headers=auth).status_code == 401


def test_demo_orm_guard(db, demo):
    token = demo_read_only.set(True)
    try:
        db.add(Organization(id="should-not-write", name="no", slug="no"))
        with pytest.raises(PermissionError):
            db.flush()
    finally:
        db.rollback()
        demo_read_only.reset(token)


def test_expired_demo_never_falls_back_to_anonymous(client, demo, monkeypatch):
    monkeypatch.setattr("app.middleware.auth_context.ALLOW_ANONYMOUS", True)
    token = create_access_token(user_id=DEMO_USER_ID, org_id=DEMO_ORG_ID, demo=True, expires_minutes=-1)
    assert client.get("/ingestion/permits", headers={"Authorization": f"Bearer {token}"}).status_code == 401


@pytest.mark.parametrize("semantics", ["person", "unknown", "legal_entity", "business_dba"])
def test_applicant_graph_requires_company_semantics(db, demo, semantics):
    from app.models.ingestion import SourceFieldMapping
    from app.services.ingestion.service import project_permit_to_graph
    from app.utils.org_scope import RequestContext, reset_current_context, set_current_context

    context = set_current_context(RequestContext(DEMO_ORG_ID, DEMO_USER_ID))
    try:
        permit = db.query(PermitRecord).first()
        mapping = db.query(SourceFieldMapping).filter_by(canonical_field="applicant_name").one()
        mapping.value_semantics = semantics
        permit.applicant_name = "Another Applicant"
        db.flush()
        project_permit_to_graph(db, permit)
        db.flush()
        found = db.query(GraphEntity).filter_by(display_name="Another Applicant").first()
        assert bool(found) == (semantics in {"legal_entity", "business_dba"})
    finally:
        db.rollback()
        reset_current_context(context)


def test_demo_password_reset_never_sends_email(client, db, demo, monkeypatch):
    from app.models.password_reset_token import PasswordResetToken
    user = db.get(User, DEMO_USER_ID)
    user.email = "demo-test@example.com"
    db.commit()
    def unexpected_email():
        pytest.fail("Demo password recovery must not send email")
    monkeypatch.setattr("app.routes.password_reset.get_email_service", unexpected_email)
    assert client.post("/auth/password/forgot", json={"email": user.email}).status_code == 204
    assert db.query(PasswordResetToken).count() == 0
