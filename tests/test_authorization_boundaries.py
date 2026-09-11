"""Synthetic tenant-boundary regressions; no production services or credentials."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.routes import organizations
from app.services.audit_service import log_change
from app.services.security import (
    create_access_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
)
from app.utils.org_scope import (
    DEFAULT_ORG_ID,
    RequestContext,
    reset_current_context,
    set_current_context,
)


def _org(db, name):
    org = Organization(id=str(uuid4()), name=name, slug=str(uuid4()))
    db.add(org)
    db.flush()
    return org


def _member(db, org, name, role=MemberRole.admin, *, active=True):
    user = User(
        id=str(uuid4()), email=f"{name}@example.com", full_name=name,
        password_hash="unused-no-password-login", is_active=active,
    )
    db.add(user)
    db.flush()
    membership = OrganizationMembership(
        organization_id=org.id, user_id=user.id, role=role,
    )
    db.add(membership)
    db.commit()
    return user, membership


def _headers(user, org):
    token = create_access_token(user_id=user.id, org_id=org.id, token_version=user.token_version)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tenants(db):
    a, b = _org(db, "Tenant A"), _org(db, "Tenant B")
    admin_a, membership_a = _member(db, a, "admin-a")
    admin_b, membership_b = _member(db, b, "admin-b")
    return a, b, admin_a, admin_b, membership_a, membership_b


@pytest.mark.parametrize("method,suffix,payload,expected", [
    ("GET", "/members", None, 404),
    ("POST", "/members", {"email": "admin-a@example.com", "role": "admin"}, 403),
    ("PATCH", "/members/{target}", {"role": "viewer"}, 403),
    ("DELETE", "/members/{target}", None, 403),
    ("GET", "/export", None, 403),
])
def test_foreign_org_ids_cannot_read_or_mutate(client, db, tenants, method, suffix, payload, expected):
    a, b, admin_a, admin_b, _, membership_b = tenants
    response = client.request(
        method, f"/organizations/{b.id}" + suffix.format(target=admin_b.id),
        headers=_headers(admin_a, a), json=payload,
    )
    assert response.status_code == expected, response.text
    assert "admin-b@example.com" not in response.text
    db.expire_all()
    assert db.get(OrganizationMembership, membership_b.id).role == MemberRole.admin
    assert db.query(AuditLog).count() == 0


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_foreign_user_id_is_not_resolved_in_own_org(client, db, tenants, method):
    a, _, admin_a, admin_b, _, membership_b = tenants
    response = client.request(
        method, f"/organizations/{a.id}/members/{admin_b.id}",
        headers=_headers(admin_a, a), json={"role": "viewer"} if method == "PATCH" else None,
    )
    assert response.status_code == 404
    db.expire_all()
    assert db.get(OrganizationMembership, membership_b.id).role == MemberRole.admin


@pytest.mark.parametrize("role", [MemberRole.viewer, MemberRole.editor])
@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
def test_non_admin_cannot_escalate_or_manage_members(client, db, tenants, role, method):
    a, _, admin_a, _, _, _ = tenants
    user, membership = _member(db, a, "non-admin", role)
    target = "" if method == "POST" else f"/{user.id}"
    payload = {"email": admin_a.email, "role": "admin"} if method == "POST" else {"role": "admin"}
    response = client.request(
        method, f"/organizations/{a.id}/members{target}",
        headers=_headers(user, a), json=payload if method != "DELETE" else None,
    )
    assert response.status_code == 403
    db.expire_all()
    assert db.get(OrganizationMembership, membership.id).role == role
    assert db.query(AuditLog).count() == 0


def test_target_org_role_not_active_org_role_controls_membership_mutations(client, db, tenants):
    a, b, admin_a, admin_b, _, _ = tenants
    db.add(OrganizationMembership(organization_id=b.id, user_id=admin_a.id, role=MemberRole.viewer))
    db.commit()
    denied = client.patch(
        f"/organizations/{b.id}/members/{admin_a.id}",
        headers=_headers(admin_a, a), json={"role": "admin"},
    )
    assert denied.status_code == 403
    # An admin of the target organization can still manage it from another
    # active organization, per the existing membership API contract.
    allowed = client.post(
        f"/organizations/{a.id}/members", headers=_headers(admin_a, b),
        json={"email": admin_b.email, "role": "editor"},
    )
    assert allowed.status_code == 201, allowed.text
    event = db.query(AuditLog).one()
    assert event.organization_id == a.id
    assert event.actor_id == admin_a.id
    export = client.get(f"/organizations/{a.id}/export", headers=_headers(admin_a, b))
    assert export.status_code == 403  # Export requires an explicit org switch.


@pytest.mark.parametrize("state", ["inactive", "revoked"])
@pytest.mark.parametrize("method,path", [
    ("GET", "/organizations/me"),
    ("GET", "/organizations/{org}/members"),
    ("GET", "/organizations/{org}/export"),
    ("GET", "/audit"),
    ("POST", "/audit/export?format=json"),
    ("POST", "/audit/export?format=csv"),
    ("PATCH", "/organizations/{org}/members/{user}"),
    ("POST", "/auth/switch-org"),
])
def test_old_tokens_do_not_bypass_inactive_or_revoked_membership(client, db, tenants, state, method, path):
    a, _, admin_a, _, membership_a, _ = tenants
    headers = _headers(admin_a, a)
    if state == "inactive":
        admin_a.is_active = False
    else:
        db.delete(membership_a)
    db.commit()
    response = client.request(
        method, path.format(org=a.id, user=admin_a.id), headers=headers,
        json={"role": "admin", "organization_id": a.id} if method in ("POST", "PATCH") else None,
    )
    assert response.status_code == (401 if state == "inactive" else 403), response.text
    assert db.query(AuditLog).count() == 0


def test_role_change_and_revocation_take_effect_on_previously_issued_tokens(client, db, tenants):
    a, b, admin_a, admin_b, _, _ = tenants
    colleague, _ = _member(db, a, "colleague")
    db.add(OrganizationMembership(organization_id=b.id, user_id=colleague.id, role=MemberRole.viewer))
    db.commit()
    old_headers = _headers(colleague, a)
    response = client.patch(
        f"/organizations/{a.id}/members/{colleague.id}",
        headers=_headers(admin_a, a), json={"role": "viewer"},
    )
    assert response.status_code == 200
    for method, path in [("GET", "/audit"), ("POST", "/audit/export"),
                         ("GET", f"/organizations/{a.id}/export")]:
        assert client.request(method, path, headers=old_headers).status_code == 403
    escalation = client.patch(
        f"/organizations/{a.id}/members/{colleague.id}", headers=old_headers, json={"role": "admin"},
    )
    assert escalation.status_code == 403
    assert client.get(f"/organizations/{a.id}/members", headers=old_headers).status_code == 200
    assert client.delete(
        f"/organizations/{a.id}/members/{colleague.id}", headers=_headers(admin_a, a),
    ).status_code == 204
    assert client.get(f"/organizations/{a.id}/members", headers=old_headers).status_code == 403
    # Revocation in A must not remove the user's legitimate membership in B.
    own_orgs = client.get("/organizations/me", headers=_headers(colleague, b))
    assert own_orgs.status_code == 200
    assert [item["organization"]["id"] for item in own_orgs.json()] == [b.id]
    assert client.get(f"/organizations/{b.id}/members", headers=_headers(admin_b, b)).status_code == 200


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_inactive_admin_does_not_allow_last_active_admin_to_leave(client, db, tenants, method):
    a, _, admin_a, _, membership_a, _ = tenants
    _member(db, a, "inactive-admin", active=False)
    response = client.request(
        method, f"/organizations/{a.id}/members/{admin_a.id}", headers=_headers(admin_a, a),
        json={"role": "viewer"} if method == "PATCH" else None,
    )
    assert response.status_code == 400
    assert "last admin" in response.json()["detail"]
    db.expire_all()
    assert db.get(OrganizationMembership, membership_a.id).role == MemberRole.admin


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_inactive_users_cannot_be_invited_or_promoted(client, db, tenants, method):
    a, b, admin_a, _, _, _ = tenants
    inactive, _ = _member(db, b if method == "POST" else a, "inactive", MemberRole.viewer, active=False)
    path = f"/organizations/{a.id}/members" + (f"/{inactive.id}" if method == "PATCH" else "")
    response = client.request(
        method, path, headers=_headers(admin_a, a), json={"email": inactive.email, "role": "admin"},
    )
    assert response.status_code == 400
    assert db.query(AuditLog).count() == 0


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
def test_membership_write_rolls_back_if_audit_record_cannot_be_written(client, db, tenants, monkeypatch, method):
    a, b, admin_a, admin_b, _, _ = tenants
    colleague, membership = _member(db, a, "colleague", MemberRole.viewer)
    membership_id = membership.id

    def unavailable_audit(*args, **kwargs):
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr(organizations, "log_change", unavailable_audit)
    suffix = "" if method == "POST" else f"/{colleague.id}"
    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        client.request(
            method, f"/organizations/{a.id}/members{suffix}", headers=_headers(admin_a, a),
            json={"email": admin_b.email, "role": "editor"} if method != "DELETE" else None,
        )
    db.expire_all()
    assert db.get(OrganizationMembership, membership_id).role == MemberRole.viewer
    assert db.query(OrganizationMembership).filter_by(organization_id=a.id, user_id=admin_b.id).count() == 0
    assert db.query(AuditLog).count() == 0


def test_switch_org_preserves_current_token_version(client, db, tenants):
    a, b, admin_a, _, _, _ = tenants
    db.add(OrganizationMembership(organization_id=b.id, user_id=admin_a.id, role=MemberRole.viewer))
    admin_a.token_version = 7
    password = "SyntheticSwitchOrg42!"
    admin_a.password_hash = hash_password(password)
    db.commit()
    login = client.post("/auth/login", json={"email": admin_a.email, "password": password})
    assert login.status_code == 200
    assert login.json()["organization_id"] == a.id
    response = client.post(
        "/auth/switch-org", headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"organization_id": b.id},
    )
    assert response.status_code == 200
    claims = decode_access_token(response.json()["access_token"])
    assert claims["tv"] == 7
    assert claims["org_id"] == b.id
    from app.config import REFRESH_COOKIE_NAME

    cookie_claims = decode_refresh_token(response.cookies[REFRESH_COOKIE_NAME])
    assert cookie_claims["tv"] == 7
    assert cookie_claims["org_id"] == b.id
    assert response.headers["cache-control"] == "no-store"


def test_switch_org_cannot_resurrect_session_after_logout_all(client, db, tenants):
    a, b, admin_a, _, _, _ = tenants
    db.add(OrganizationMembership(organization_id=b.id, user_id=admin_a.id, role=MemberRole.viewer))
    db.commit()
    old_headers = _headers(admin_a, a)
    assert client.post("/auth/logout-all", headers=old_headers).status_code == 204
    response = client.post("/auth/switch-org", headers=old_headers, json={"organization_id": b.id})
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


def test_audit_service_default_uses_request_tenant_but_explicit_scope_wins(db, tenants):
    a, b, admin_a, _, _, _ = tenants
    context = set_current_context(RequestContext(org_id=a.id, user_id=admin_a.id))
    try:
        entry = log_change(db, "deal", "example", "update", new_values={"name": "private-a"})
        explicit = log_change(db, "membership", "example", "invite", organization_id=b.id)
        assert entry.organization_id == a.id
        assert explicit.organization_id == b.id
        with pytest.raises(ValueError, match="organization_id"):
            log_change(db, "deal", "example", "update", organization_id=" ")
    finally:
        reset_current_context(context)


def test_authenticated_deal_audit_is_not_written_into_default_tenant(client, db, tenants):
    a, _, admin_a, _, _, _ = tenants
    response = client.post("/deals", headers=_headers(admin_a, a), json={"name": "Private investment"})
    assert response.status_code == 201, response.text
    deal_id = response.json()["id"]
    assert client.patch(
        f"/deals/{deal_id}", headers=_headers(admin_a, a), json={"name": "Confidential revision"},
    ).status_code == 200
    entries = db.query(AuditLog).filter(AuditLog.entity_id == deal_id).all()
    assert len(entries) == 2
    assert all(entry.organization_id == a.id for entry in entries)
    assert db.query(AuditLog).filter_by(organization_id=DEFAULT_ORG_ID).count() == 0
    logs = client.get(f"/audit?entity_id={deal_id}", headers=_headers(admin_a, a))
    assert logs.status_code == 200
    assert logs.json()["total"] == 2


def test_org_export_isolates_members_and_audit_entries(client, db, tenants):
    a, b, admin_a, admin_b, _, _ = tenants
    for org, actor, secret in [(a, admin_a, "private-a"), (b, admin_b, "private-b")]:
        log_change(db, "deal", str(uuid4()), "create", organization_id=org.id,
                   actor_id=actor.id, new_values={"secret": secret})
    db.commit()
    response = client.get(f"/organizations/{a.id}/export", headers=_headers(admin_a, a))
    assert response.status_code == 200
    assert [member["user"]["id"] for member in response.json()["members"]] == [admin_a.id]
    assert all(entry["organization_id"] == a.id for entry in response.json()["audit_logs"])
    assert "private-b" not in response.text
    assert admin_b.email not in response.text
    assert "password_hash" not in response.text
    assert "totp_secret" not in response.text


def test_member_rosters_and_organization_lists_are_not_cacheable(client, tenants):
    a, _, admin_a, _, _, _ = tenants
    for path in ["/organizations/me", f"/organizations/{a.id}/members"]:
        response = client.get(path, headers=_headers(admin_a, a))
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
