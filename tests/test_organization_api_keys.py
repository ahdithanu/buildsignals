from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models.api_key import OrganizationApiKey
from app.models.audit_log import AuditLog
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.services.rate_limiter import limiter

STRONG_PW = "CorrectHorseBattery42"


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.clear()
    yield
    limiter.clear()


def _register(client, *, email, org_name):
    response = client.post("/auth/register", json={
        "email": email,
        "password": STRONG_PW,
        "full_name": email.split("@")[0].title(),
        "organization_name": org_name,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_admin_creates_lists_and_revokes_api_key_without_storing_secret(client, db):
    admin = _register(client, email="api-admin@example.com", org_name="API Co")
    org_id = admin["organization_id"]

    created = client.post(
        f"/organizations/{org_id}/api-keys",
        headers=_auth(admin["access_token"]),
        json={"name": "Warehouse ETL", "scopes": ["read", "write", "read"]},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["secret"].startswith("bs_live_")
    assert body["key_prefix"].startswith("bs_live_")
    assert body["scopes"] == ["read", "write"]
    assert body["revoked_at"] is None
    assert body["expires_at"] is not None
    assert body["rotation_due"] is False

    stored = db.query(OrganizationApiKey).filter_by(id=body["id"]).one()
    assert stored.key_hash != body["secret"]
    assert body["secret"] not in stored.key_hash
    assert json.loads(stored.scopes) == ["read", "write"]

    listed = client.get(f"/organizations/{org_id}/api-keys", headers=_auth(admin["access_token"]))
    assert listed.status_code == 200, listed.text
    listed_body = listed.json()
    assert len(listed_body) == 1
    assert "secret" not in listed_body[0]
    assert listed_body[0]["key_prefix"] == body["key_prefix"]
    assert listed_body[0]["expires_at"] == body["expires_at"]

    revoked = client.delete(
        f"/organizations/{org_id}/api-keys/{body['id']}",
        headers=_auth(admin["access_token"]),
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked_at"]
    assert revoked.json()["revoked_by"] == admin["user_id"]

    audit_actions = [
        row.action for row in db.query(AuditLog)
        .filter_by(organization_id=org_id, entity_type="organization_api_key")
        .order_by(AuditLog.created_at.asc()).all()
    ]
    assert audit_actions == ["create", "revoke"]
    assert body["secret"] not in "\n".join(row.new_values or "" for row in db.query(AuditLog).all())


def test_non_admin_cannot_manage_api_keys(client, db):
    admin = _register(client, email="admin-key@example.com", org_name="Key Co")
    org_id = admin["organization_id"]
    membership = db.query(OrganizationMembership).filter_by(user_id=admin["user_id"], organization_id=org_id).one()
    membership.role = MemberRole.viewer
    db.commit()

    response = client.post(
        f"/organizations/{org_id}/api-keys",
        headers=_auth(admin["access_token"]),
        json={"name": "Blocked", "scopes": ["read"]},
    )
    assert response.status_code == 403


def test_api_keys_are_tenant_scoped(client):
    first = _register(client, email="first-key@example.com", org_name="First Key Co")
    second = _register(client, email="second-key@example.com", org_name="Second Key Co")

    created = client.post(
        f"/organizations/{first['organization_id']}/api-keys",
        headers=_auth(first["access_token"]),
        json={"name": "First export", "scopes": ["read"]},
    )
    assert created.status_code == 201

    cross_list = client.get(
        f"/organizations/{first['organization_id']}/api-keys",
        headers=_auth(second["access_token"]),
    )
    assert cross_list.status_code == 403

    cross_revoke = client.delete(
        f"/organizations/{first['organization_id']}/api-keys/{created.json()['id']}",
        headers=_auth(second["access_token"]),
    )
    assert cross_revoke.status_code == 403


def test_invalid_api_key_scope_is_rejected(client):
    admin = _register(client, email="scope-key@example.com", org_name="Scope Key Co")
    response = client.post(
        f"/organizations/{admin['organization_id']}/api-keys",
        headers=_auth(admin["access_token"]),
        json={"name": "Bad scope", "scopes": ["root"]},
    )
    assert response.status_code == 422


def test_api_key_expiration_must_be_future_and_rotation_due_is_reported(client):
    admin = _register(client, email="expiry-key@example.com", org_name="Expiry Key Co")
    expired = client.post(
        f"/organizations/{admin['organization_id']}/api-keys",
        headers=_auth(admin["access_token"]),
        json={
            "name": "Already expired",
            "scopes": ["read"],
            "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
    )
    assert expired.status_code == 422

    soon = datetime.now(timezone.utc) + timedelta(days=7)
    created = client.post(
        f"/organizations/{admin['organization_id']}/api-keys",
        headers=_auth(admin["access_token"]),
        json={"name": "Rotate soon", "scopes": ["read"], "expires_at": soon.isoformat()},
    )
    assert created.status_code == 201, created.text
    assert created.json()["rotation_due"] is True
