"""End-to-end tests for /organizations/{id}/members.

The frontend Team page depends on these contracts:

- any member can list the roster
- only admins can invite / change role / remove
- the last admin cannot be demoted or removed (would leave the org unmanageable)
- inviting an email that hasn't registered returns a clear 404
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.services.rate_limiter import limiter
from app.services.security import create_access_token, hash_password

STRONG_PW = "CorrectHorseBattery42"


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.clear()
    yield
    limiter.clear()


def _register(client, *, email, org_name):
    r = client.post("/auth/register", json={
        "email": email, "password": STRONG_PW,
        "full_name": email.split("@")[0].title(),
        "organization_name": org_name,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_user(db, email, full_name="Seeded"):
    u = User(
        id=str(uuid4()),
        email=email,
        full_name=full_name,
        password_hash=hash_password(STRONG_PW),
        is_active=True,
    )
    db.add(u)
    db.commit()
    return u


class TestMemberRoster:
    def test_admin_invites_existing_user_and_lists_them(self, client, db):
        admin = _register(client, email="admin@acme.com", org_name="Acme")
        _seed_user(db, "teammate@acme.com", "Teammate")

        r = client.post(
            f"/organizations/{admin['organization_id']}/members",
            headers=_auth(admin["access_token"]),
            json={"email": "teammate@acme.com", "role": "editor"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["email"] == "teammate@acme.com"
        assert r.json()["role"] == "editor"

        r2 = client.get(
            f"/organizations/{admin['organization_id']}/members",
            headers=_auth(admin["access_token"]),
        )
        assert r2.status_code == 200
        emails = sorted(m["email"] for m in r2.json())
        assert emails == ["admin@acme.com", "teammate@acme.com"]

    def test_invite_unknown_email_is_404(self, client):
        admin = _register(client, email="admin@acme.com", org_name="Acme")
        r = client.post(
            f"/organizations/{admin['organization_id']}/members",
            headers=_auth(admin["access_token"]),
            json={"email": "ghost@nowhere.com", "role": "editor"},
        )
        assert r.status_code == 404

    def test_non_admin_cannot_invite(self, client, db):
        admin = _register(client, email="admin@acme.com", org_name="Acme")
        org_id = admin["organization_id"]

        viewer = _seed_user(db, "viewer@acme.com", "Viewer")
        db.add(OrganizationMembership(
            id=str(uuid4()),
            organization_id=org_id,
            user_id=viewer.id,
            role=MemberRole.viewer,
            is_default=True,
        ))
        db.commit()
        viewer_token = create_access_token(user_id=viewer.id, org_id=org_id)

        _seed_user(db, "newhire@acme.com")
        r = client.post(
            f"/organizations/{org_id}/members",
            headers=_auth(viewer_token),
            json={"email": "newhire@acme.com", "role": "editor"},
        )
        assert r.status_code == 403

    def test_last_admin_cannot_be_demoted(self, client):
        admin = _register(client, email="solo@acme.com", org_name="Acme")
        r = client.patch(
            f"/organizations/{admin['organization_id']}/members/{admin['user_id']}",
            headers=_auth(admin["access_token"]),
            json={"role": "editor"},
        )
        assert r.status_code == 400
        assert "last admin" in r.json()["detail"].lower()

    def test_last_admin_cannot_be_removed(self, client):
        admin = _register(client, email="solo@acme.com", org_name="Acme")
        r = client.delete(
            f"/organizations/{admin['organization_id']}/members/{admin['user_id']}",
            headers=_auth(admin["access_token"]),
        )
        assert r.status_code == 400

    def test_admin_can_change_role_and_remove(self, client, db):
        admin = _register(client, email="admin@acme.com", org_name="Acme")
        org_id = admin["organization_id"]
        teammate = _seed_user(db, "teammate@acme.com")

        # invite
        r = client.post(
            f"/organizations/{org_id}/members",
            headers=_auth(admin["access_token"]),
            json={"email": "teammate@acme.com", "role": "viewer"},
        )
        assert r.status_code == 201

        # promote to editor
        r = client.patch(
            f"/organizations/{org_id}/members/{teammate.id}",
            headers=_auth(admin["access_token"]),
            json={"role": "editor"},
        )
        assert r.status_code == 200
        assert r.json()["role"] == "editor"

        # remove
        r = client.delete(
            f"/organizations/{org_id}/members/{teammate.id}",
            headers=_auth(admin["access_token"]),
        )
        assert r.status_code == 204

        # confirm roster shrank
        r = client.get(
            f"/organizations/{org_id}/members",
            headers=_auth(admin["access_token"]),
        )
        assert [m["email"] for m in r.json()] == ["admin@acme.com"]


def test_concurrent_self_demotions_preserve_one_active_admin(client, db):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from fastapi import HTTPException, Response
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import NullPool

    from app.routes.organizations import update_member_role
    from app.schemas.organization import UpdateMemberRequest
    from app.utils.auth_deps import get_current_user

    admin = _register(client, email="first@acme.com", org_name="Acme")
    second = _seed_user(db, "second@acme.com")
    org_id = admin["organization_id"]
    db.add(OrganizationMembership(organization_id=org_id, user_id=second.id, role=MemberRole.admin))
    db.commit()
    actors = [(admin["user_id"], admin["access_token"]),
              (second.id, create_access_token(user_id=second.id, org_id=org_id))]
    # Independent connections, unlike the shared TestClient's StaticPool.
    engine = create_engine(db.get_bind().url, poolclass=NullPool,
                           connect_args={"check_same_thread": False, "timeout": 10})
    authorized = Barrier(2)

    def demote(actor):
        user_id, token = actor
        with Session(engine) as session:
            principal = get_current_user(authorization=f"Bearer {token}", db=session)
            authorized.wait(timeout=10)
            try:
                update_member_role(org_id=org_id, user_id=user_id,
                                   payload=UpdateMemberRequest(role=MemberRole.viewer),
                                   response=Response(), principal=principal, db=session)
            except HTTPException as exc:
                session.rollback()
                return exc.status_code
            return 200

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(demote, actors))
    finally:
        engine.dispose()
    assert sorted(results) == [200, 400]
    db.expire_all()
    assert db.query(OrganizationMembership).filter_by(organization_id=org_id, role=MemberRole.admin).count() == 1
    from app.models.audit_log import AuditLog

    assert db.query(AuditLog).filter_by(organization_id=org_id, action="role_change").count() == 1


@pytest.mark.parametrize("revoked", [False, True])
def test_membership_role_is_rechecked_after_authorization(client, db, revoked):
    from fastapi import HTTPException, Response
    from sqlalchemy.orm import Session

    from app.routes.organizations import invite_member
    from app.schemas.organization import InviteMemberRequest
    from app.utils.auth_deps import get_current_user

    admin = _register(client, email="admin@acme.com", org_name="Acme")
    _seed_user(db, "newhire@acme.com")
    principal = get_current_user(authorization=f"Bearer {admin['access_token']}", db=db)
    stale_membership = db.query(OrganizationMembership).filter_by(
        organization_id=admin["organization_id"], user_id=admin["user_id"],
    ).one()
    with Session(db.get_bind()) as other:
        membership = other.get(OrganizationMembership, stale_membership.id)
        if revoked:
            other.delete(membership)
        else:
            membership.role = MemberRole.viewer
        other.commit()
    # Keep the original session's admin object cached, as an in-flight request would.
    assert stale_membership.role == MemberRole.admin
    with pytest.raises(HTTPException) as error:
        invite_member(org_id=admin["organization_id"],
                      payload=InviteMemberRequest(email="newhire@acme.com", role=MemberRole.editor),
                      response=Response(), principal=principal, db=db)
    assert error.value.status_code in (403, 404)
    db.rollback()
    assert db.query(OrganizationMembership).filter_by(organization_id=admin["organization_id"]).count() == (0 if revoked else 1)


@pytest.mark.parametrize("method,suffix", [
    ("GET", "/members"),
    ("POST", "/members"),
    ("PATCH", "/members/{user_id}"),
    ("DELETE", "/members/{user_id}"),
    ("POST", "/switch-org"),
])
def test_inactive_target_org_rejects_cross_org_reads_mutations_and_switch(client, db, method, suffix):
    from app.models.audit_log import AuditLog
    from app.models.organization import Organization

    active = _register(client, email="active@acme.com", org_name="Active")
    target = _register(client, email="target@acme.com", org_name="Target")
    target_id = target["organization_id"]
    db.add(OrganizationMembership(organization_id=target_id, user_id=active["user_id"], role=MemberRole.admin))
    db.get(Organization, target_id).is_active = False
    db.commit()
    before_audit = db.query(AuditLog).count()
    path = "/auth/switch-org" if suffix == "/switch-org" else (
        f"/organizations/{target_id}" + suffix.format(user_id=target["user_id"])
    )
    response = client.request(
        method, path, headers=_auth(active["access_token"]),
        json={"organization_id": target_id, "email": "unregistered@example.com", "role": "viewer"}
        if method in ("POST", "PATCH") else None,
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "Organization is unavailable"
    assert "set-cookie" not in response.headers
    db.expire_all()
    assert db.query(OrganizationMembership).filter_by(organization_id=target_id, role=MemberRole.admin).count() == 2
    assert db.query(AuditLog).count() == before_audit
    available = client.get("/organizations/me", headers=_auth(active["access_token"]))
    assert available.status_code == 200
    assert [item["organization"]["id"] for item in available.json()] == [active["organization_id"]]


def test_role_update_with_missing_member_user_returns_404_without_audit(client, db):
    from app.models.audit_log import AuditLog

    admin = _register(client, email="admin@acme.com", org_name="Acme")
    missing_id = str(uuid4())
    membership = OrganizationMembership(organization_id=admin["organization_id"], user_id=missing_id,
                                        role=MemberRole.viewer)
    db.add(membership)
    db.commit()
    response = client.patch(
        f"/organizations/{admin['organization_id']}/members/{missing_id}",
        headers=_auth(admin["access_token"]), json={"role": "admin"},
    )
    assert response.status_code == 404
    db.expire_all()
    assert db.get(OrganizationMembership, membership.id).role == MemberRole.viewer
    assert db.query(AuditLog).filter_by(action="role_change").count() == 0


@pytest.mark.parametrize("target_active", [False, True])
def test_require_role_of_checks_target_availability_without_route_guard(client, db, target_active):
    from fastapi import HTTPException, Request

    from app.models.organization import Organization
    from app.utils.auth_deps import get_current_user, require_role_of

    admin = _register(client, email="shared-guard@acme.com", org_name="Active")
    target = Organization(id=str(uuid4()), name="Target", slug=str(uuid4()), is_active=target_active)
    db.add(target)
    db.flush()
    db.add(OrganizationMembership(organization_id=target.id, user_id=admin["user_id"], role=MemberRole.admin))
    db.commit()
    principal = get_current_user(authorization=f"Bearer {admin['access_token']}", db=db)
    request = Request({"type": "http", "path_params": {"org_id": target.id}})
    checker = require_role_of(MemberRole.admin)
    if target_active:
        assert checker(request=request, principal=principal, db=db) is principal
    else:
        with pytest.raises(HTTPException) as exc:
            checker(request=request, principal=principal, db=db)
        assert exc.value.status_code == 403
        assert exc.value.detail == "Organization is unavailable"
