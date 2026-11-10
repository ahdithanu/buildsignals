from __future__ import annotations

from uuid import uuid4

import pytest

from app import config
from app.models.ingestion import IngestionSource
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.services.security import create_access_token, create_refresh_token, hash_password
from tests.test_demo import demo as demo

OPERATIONS_REQUESTS = [
    ("GET", "/observability/overview"),
    ("GET", "/ingestion/sources"),
    ("GET", "/ingestion/health"),
    ("GET", "/ingestion/reliability-summary"),
    ("GET", "/ingestion/runs"),
    ("GET", "/ingestion/candidates"),
    ("GET", "/ingestion/host-policy"),
    ("GET", "/ingestion/schedule-plan"),
    ("GET", "/ingestion/coverage"),
    ("GET", "/ingestion/coverage/measured"),
    ("GET", "/ingestion/sources/missing/health"),
    ("GET", "/ingestion/sources/missing/parcel-reference-audit?parcel_source_id=missing"),
    ("GET", "/ingestion/sources/missing/parcel-reconciliation?parcel_source_id=missing"),
    ("GET", "/ingestion/candidates/missing/canary-history"),
    ("POST", "/ingestion/sources"),
    ("PATCH", "/ingestion/sources/missing"),
    ("POST", "/ingestion/sources/missing/runs"),
    ("POST", "/ingestion/sources/missing/canary"),
    ("POST", "/ingestion/candidates/missing/canary"),
    ("POST", "/ingestion/candidates/missing/promote"),
    ("POST", "/ingestion/onboarding/plan"),
    ("GET", "/ingestion/onboarding/enrollment"),
    ("PUT", "/ingestion/onboarding/enrollment"),
]


def _identity(db, role=MemberRole.admin):
    org_id, user_id = str(uuid4()), str(uuid4())
    db.add(Organization(id=org_id, name="Test workspace", slug=org_id))
    db.add(User(id=user_id, email=f"{user_id}@example.com", full_name="Test user",
                password_hash=hash_password("CorrectHorseBattery42"), is_active=True))
    db.add(OrganizationMembership(organization_id=org_id, user_id=user_id,
                                  role=role, is_default=True))
    db.commit()
    return user_id, org_id, {"Authorization": f"Bearer {create_access_token(user_id=user_id, org_id=org_id)}"}


@pytest.mark.parametrize("role,allowlisted", [
    (MemberRole.admin, False), (MemberRole.editor, True), (MemberRole.viewer, True),
])
def test_operations_require_both_allowlist_and_admin(client, db, monkeypatch, role, allowlisted):
    user_id, _, headers = _identity(db, role)
    monkeypatch.setattr(config, "INTERNAL_OPERATIONS_USER_IDS",
                        frozenset({user_id}) if allowlisted else frozenset(), raising=False)
    for method, path in OPERATIONS_REQUESTS:
        response = client.request(method, f"/v1{path}", headers=headers, json={})
        assert response.status_code == 403, (method, path, response.text)


def test_operations_require_real_auth_even_in_anonymous_mode(client, monkeypatch):
    monkeypatch.setattr(config, "INTERNAL_OPERATIONS_USER_IDS", frozenset(), raising=False)
    for method, path in OPERATIONS_REQUESTS:
        response = client.request(method, path, json={})
        assert response.status_code == 401, (method, path, response.text)


def test_allowlisted_operator_reads_inventory_and_membership_revocation_takes_effect(client, db, monkeypatch):
    user_id, org_id, headers = _identity(db)
    monkeypatch.setattr(config, "INTERNAL_OPERATIONS_USER_IDS", frozenset({user_id}), raising=False)
    db.add(IngestionSource(organization_id=org_id, key="private_connector", name="Internal provider",
                           adapter="json_api", record_type="permit", base_url="https://example.gov/raw",
                           settings={"connector": {"endpoint": "https://example.gov/feed"}}))
    db.commit()
    response = client.get("/v1/ingestion/sources", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()[0]["base_url"] == "https://example.gov/raw"
    membership = db.query(OrganizationMembership).filter_by(user_id=user_id, organization_id=org_id).one()
    membership.role = MemberRole.viewer
    db.commit()
    assert client.get("/v1/ingestion/sources", headers=headers).status_code == 403
    db.delete(membership)
    db.commit()
    assert client.get("/v1/ingestion/sources", headers=headers).status_code == 403


@pytest.mark.parametrize("role", list(MemberRole))
def test_customer_source_options_are_narrow_active_and_tenant_scoped(client, db, monkeypatch, role):
    _, org_id, headers = _identity(db, role)
    _, other_org, _ = _identity(db)
    monkeypatch.setattr(config, "INTERNAL_OPERATIONS_USER_IDS", frozenset(), raising=False)
    source = IngestionSource(organization_id=org_id, key="secret_connector", name="Secret provider",
                             adapter="arcgis", record_type="parcel", jurisdiction="Internal notes",
                             base_url="https://example.gov/private", settings={"connector": {"field": "private"}})
    db.add_all([source,
                IngestionSource(organization_id=org_id, key="inactive", name="Inactive", adapter="csv", is_active=False),
                IngestionSource(organization_id=other_org, key="other", name="Other tenant", adapter="csv")])
    db.commit()
    response = client.get("/v1/ingestion/source-options", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == [{"id": source.id, "name": "Public records", "record_type": "parcel", "is_active": True}]
    assert client.get("/v1/ingestion/source-options").status_code == 401
    assert client.get("/v1/ingestion/permits", headers=headers).status_code == 200
    assert client.get("/v1/acquisition-map/signals", headers=headers).status_code == 200
    assert client.get("/v1/ingestion/coverage/national-parcels", headers=headers).status_code == 200


@pytest.mark.parametrize("role,allowlisted,expected", [
    (MemberRole.admin, True, True), (MemberRole.admin, False, False),
    (MemberRole.editor, True, False), (MemberRole.viewer, True, False),
])
def test_auth_operator_flag_is_computed_for_login_refresh_me(client, db, monkeypatch, role, allowlisted, expected):
    user_id, org_id, headers = _identity(db, role)
    monkeypatch.setattr(config, "INTERNAL_OPERATIONS_USER_IDS",
                        frozenset({user_id}) if allowlisted else frozenset(), raising=False)
    login = client.post("/v1/auth/login", json={"email": f"{user_id}@example.com", "password": "CorrectHorseBattery42",
                                               "is_internal_operator": True})
    assert login.status_code == 200, login.text
    assert login.json()["is_internal_operator"] is expected
    me = client.get("/v1/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["is_internal_operator"] is expected
    from app.config import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH

    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE_NAME, create_refresh_token(user_id=user_id, org_id=org_id), path=REFRESH_COOKIE_PATH)
    refreshed = client.post("/v1/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["is_internal_operator"] is expected
    monkeypatch.setattr(config, "INTERNAL_OPERATIONS_USER_IDS", frozenset())
    assert client.get("/v1/auth/me", headers=headers).json()["is_internal_operator"] is False
    assert client.post("/v1/auth/refresh").json()["is_internal_operator"] is False


def test_allowlisted_demo_remains_denied_and_customer_demo_reads_work(client, demo, monkeypatch):
    from app.services.demo_access import DEMO_USER_ID
    from app.utils.auth_deps import is_internal_operator

    monkeypatch.setattr(config, "INTERNAL_OPERATIONS_USER_IDS", frozenset({DEMO_USER_ID}))
    response = client.post("/v1/auth/demo")
    assert response.status_code == 200, response.text
    assert response.json()["is_internal_operator"] is False
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/v1/auth/me", headers=headers).json()["is_internal_operator"] is False
    for method, path in OPERATIONS_REQUESTS:
        assert client.request(method, f"/v1{path}", headers=headers, json={}).status_code == 403
    assert client.get("/v1/demo/summary", headers=headers).status_code == 200
    assert client.get("/v1/demo/map", headers=headers).status_code == 200
    assert client.get("/v1/ingestion/permits?limit=25", headers=headers).status_code == 200
    assert is_internal_operator(DEMO_USER_ID, "admin") is False


def test_customer_summary_counts_all_sources_without_raw_inventory(client, db, monkeypatch):
    from tests.test_measured_coverage import seed

    _, org_id, headers = _identity(db, MemberRole.viewer)
    monkeypatch.setattr(config, "INTERNAL_OPERATIONS_USER_IDS", frozenset())
    seed(db, org_id, "a_empty")
    populated = seed(db, org_id, "b_populated", count=2)
    populated.is_active = False
    db.commit()
    seed(db, "other-workspace", "hidden_provider", count=3)
    response = client.get("/v1/ingestion/coverage/summary?record_type=parcel", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"measured_at", "record_type", "stored_records", "geocoded_records"}
    assert response.json()["stored_records"] == 2
    assert response.json()["geocoded_records"] == 1
    assert client.get("/v1/ingestion/coverage/summary", headers=headers).json()["record_type"] == "parcel"
    assert client.get("/v1/ingestion/coverage/summary?record_type=permit", headers=headers).json()["stored_records"] == 0
    assert client.get("/v1/ingestion/coverage/summary?record_type=invalid", headers=headers).status_code == 422
    assert client.get("/v1/ingestion/coverage/summary").status_code == 401


def test_switch_org_operator_flag_uses_target_membership(client, db, monkeypatch):
    user_id, _, headers = _identity(db)
    target_org = str(uuid4())
    db.add(Organization(id=target_org, name="Target workspace", slug=target_org))
    membership = OrganizationMembership(organization_id=target_org, user_id=user_id,
                                        role=MemberRole.viewer)
    db.add(membership)
    db.commit()
    monkeypatch.setattr(config, "INTERNAL_OPERATIONS_USER_IDS", frozenset({user_id}))
    response = client.post("/v1/auth/switch-org", headers=headers, json={"organization_id": target_org})
    assert response.status_code == 200, response.text
    assert response.json()["is_internal_operator"] is False
    membership.role = MemberRole.admin
    db.commit()
    response = client.post("/v1/auth/switch-org", headers=headers, json={"organization_id": target_org})
    assert response.status_code == 200, response.text
    assert response.json()["is_internal_operator"] is True
    new_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/v1/auth/me", headers=new_headers).json()["is_internal_operator"] is True
    monkeypatch.setattr(config, "INTERNAL_OPERATIONS_USER_IDS", frozenset())
    response = client.post("/v1/auth/switch-org", headers=headers, json={"organization_id": target_org})
    assert response.json()["is_internal_operator"] is False


def test_registration_cannot_grant_internal_access(client, monkeypatch):
    monkeypatch.setattr(config, "INTERNAL_OPERATIONS_USER_IDS", frozenset())
    response = client.post("/v1/auth/register", json={
        "email": "ordinary-admin@example.com", "password": "CorrectHorseBattery42",
        "full_name": "Ordinary admin", "is_internal_operator": True,
    })
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "admin"
    assert response.json()["is_internal_operator"] is False
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/v1/ingestion/sources", headers=headers).status_code == 403


def test_mfa_login_preserves_computed_operator_flag(client, db, monkeypatch):
    import json

    import pyotp
    from cryptography.fernet import Fernet

    from app.services.mfa_secrets import store_secret

    user_id, _, _ = _identity(db)
    monkeypatch.setattr(config, "INTERNAL_OPERATIONS_USER_IDS", frozenset({user_id}))
    monkeypatch.setenv("MFA_ENCRYPTION_KEYS", json.dumps({"test": Fernet.generate_key().decode()}))
    monkeypatch.setenv("MFA_ACTIVE_KEY_ID", "test")
    user = db.get(User, user_id)
    secret = pyotp.random_base32()
    store_secret(user, secret)
    user.totp_enabled = True
    db.commit()
    credentials = {"email": user.email, "password": "CorrectHorseBattery42"}
    assert client.post("/v1/auth/login", json=credentials).status_code == 401
    response = client.post("/v1/auth/login", json={**credentials, "totp_code": pyotp.TOTP(secret).now()})
    assert response.status_code == 200, response.text
    assert response.json()["is_internal_operator"] is True


@pytest.mark.parametrize("role,allowlisted,operator", [
    (MemberRole.admin, False, False), (MemberRole.editor, True, False),
    (MemberRole.viewer, True, False), (MemberRole.admin, True, True),
])
def test_national_parcel_report_hides_nested_operations_except_for_operators(
    client, db, monkeypatch, role, allowlisted, operator,
):
    from datetime import datetime, timezone

    from app.services.ingestion.national_coverage import national_parcel_coverage
    from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
    from tests.test_measured_coverage import seed

    user_id, org_id, headers = _identity(db, role)
    monkeypatch.setattr(config, "INTERNAL_OPERATIONS_USER_IDS", frozenset({user_id}) if allowlisted else frozenset())
    seed(db, org_id, "customer_parcels", count=1)
    seed(db, "other-workspace", "not_customer_parcels", count=3)
    context = set_current_context(RequestContext(org_id, user_id))
    try:
        internal_report = national_parcel_coverage(db)
    finally:
        reset_current_context(context)
    florida = next(row for row in internal_report["states"] if row["state"] == "FL")
    florida["latest_verified_availability_at"] = datetime(2026, 11, 10, tzinfo=timezone.utc)
    for row in internal_report["states"] + internal_report["next_connector_targets"]:
        row["candidate_status_counts"] = {"PRIVATE_GATE_SENTINEL": 1}
        row["next_action"] = "PRIVATE_ACTION_SENTINEL"
        row["priority_reason"] = "PRIVATE_PRIORITY_SENTINEL"
    internal_report["scope"] = "PRIVATE_SCOPE_SENTINEL"
    internal_report["coverage_claim"] = "PRIVATE_CLAIM_SENTINEL"
    internal_report["warnings"] = ["PRIVATE_WARNING_SENTINEL"]
    monkeypatch.setattr("app.routes.ingestion.national_parcel_coverage", lambda db: internal_report)
    response = client.get("/v1/ingestion/coverage/national-parcels", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["summary"]["state_count"] == 50
    assert body["summary"]["stored_parcel_records"] == 1
    assert body["summary"]["geocoded_parcel_records"] == 1
    assert body["summary"]["measured_state_count"] == 1
    visible_florida = next(row for row in body["states"] if row["state"] == "FL")
    assert visible_florida["latest_verified_availability_at"].startswith("2026-11-10")
    if operator:
        assert body["next_connector_targets"]
        assert visible_florida["next_action"] == "PRIVATE_ACTION_SENTINEL"
        assert visible_florida["candidate_status_counts"] == {"PRIVATE_GATE_SENTINEL": 1}
        monkeypatch.setattr(config, "INTERNAL_OPERATIONS_USER_IDS", frozenset())
        revoked = client.get("/v1/ingestion/coverage/national-parcels", headers=headers)
        assert revoked.status_code == 200
        assert "next_connector_targets" not in revoked.json()
        assert "PRIVATE_" not in revoked.text
        return
    assert set(body) == {"measured_at", "record_type", "scope", "coverage_claim", "summary", "states", "warnings"}
    assert set(body["summary"]) == {
        "state_count", "measured_state_count", "unmeasured_state_count", "states_with_nearby_candidates",
        "states_with_verified_available_parcels", "stored_parcel_records", "geocoded_parcel_records",
        "nearby_candidate_parcels", "verified_available_parcels", "nearby_verified_available_parcels",
    }
    assert body["summary"]["unmeasured_state_count"] == 49
    for row in body["states"]:
        assert set(row) == {
            "state", "posture", "stored_parcel_records", "geocoded_parcel_records", "recently_seen_parcel_records",
            "nearby_candidate_parcels", "verified_available_parcels", "nearby_verified_available_parcels",
            "latest_verified_availability_at",
        }
        assert row["posture"] == ("measured" if row["stored_parcel_records"] else "unmeasured")
    assert "PRIVATE_" not in response.text
