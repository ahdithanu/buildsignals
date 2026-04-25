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
