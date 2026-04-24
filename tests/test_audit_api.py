"""End-to-end tests for the /audit read API.

Covers the security contract (admin-only, org-scoped) and the basic
happy-path shape the frontend depends on.
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.services.rate_limiter import limiter
from app.services.security import create_access_token, hash_password

STRONG_PW = "CorrectHorseBattery42"


@pytest.fixture(autouse=True)
def _reset_limiter():
    """The rate limiter is process-global; without this, a prior test's
    /auth/register hits bleed into ours and trip the 5-per-hour cap."""
    limiter.clear()
    yield
    limiter.clear()


def _register(client, email="alice@example.com", org_name="Acme"):
    r = client.post("/auth/register", json={
        "email": email, "password": STRONG_PW,
        "full_name": email.split("@")[0].title(),
        "organization_name": org_name,
    })
    assert r.status_code == 201, r.text
    return r.json()  # {access_token, user_id, organization_id, role}


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_log(db, *, org_id, entity_type="deal", action="create",
              actor_id=None, entity_id=None, request_id=None,
              new_values=None, old_values=None):
    entry = AuditLog(
        id=str(uuid4()),
        organization_id=org_id,
        entity_type=entity_type,
        entity_id=entity_id or str(uuid4()),
        action=action,
        actor_id=actor_id,
        new_values=json.dumps(new_values) if new_values else None,
        old_values=json.dumps(old_values) if old_values else None,
        request_id=request_id,
    )
    db.add(entry)
    db.commit()
    return entry


class TestAuditAPI:
    def test_unauthenticated_returns_401(self, client):
        r = client.get("/audit")
        assert r.status_code == 401

    def test_admin_can_list_logs_scoped_to_their_org(self, client, db):
        reg = _register(client)
        org_id = reg["organization_id"]
        _seed_log(db, org_id=org_id, action="create",
                  new_values={"name": "Deal A"})
        _seed_log(db, org_id=org_id, action="update", entity_type="memo",
                  new_values={"title": "Memo B"})

        # Filter to deals+memos so the `register` row auto-written by
        # /auth/register doesn't flap the assertion.
        r = client.get(
            "/audit?entity_type=deal",
            headers=_auth(reg["access_token"]),
        )
        assert r.status_code == 200
        assert r.json()["total"] == 1

        r = client.get(
            "/audit?entity_type=memo",
            headers=_auth(reg["access_token"]),
        )
        body = r.json()
        assert body["total"] == 1
        # JSON values decoded to objects for the client.
        assert body["items"][0]["new_values"] == {"title": "Memo B"}

        # Without a filter, we should see the two seeded rows + register row.
        r_all = client.get("/audit", headers=_auth(reg["access_token"]))
        assert r_all.json()["total"] == 3
        # Most-recent-first ordering: the two seeded writes happened after
        # register, and the "memo update" was seeded last.
        actions = [i["action"] for i in r_all.json()["items"]]
        assert actions[:2] == ["update", "create"]

    def test_cannot_see_other_orgs_logs(self, client, db):
        # Two separate orgs, each admin of their own.
        reg_a = _register(client, email="alice@acme.com", org_name="Acme")
        reg_b = _register(client, email="bob@globex.com", org_name="Globex")

        _seed_log(db, org_id=reg_a["organization_id"], entity_type="deal",
                  new_values={"secret": "acme-internal"})
        _seed_log(db, org_id=reg_b["organization_id"], entity_type="deal",
                  new_values={"secret": "globex-internal"})

        # Filter to deals so the register row from each signup doesn't
        # confuse the count; the cross-org scoping assertion is the point.
        r = client.get(
            "/audit?entity_type=deal",
            headers=_auth(reg_b["access_token"]),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["new_values"]["secret"] == "globex-internal"

    def test_non_admin_is_denied(self, client, db):
        # Admin creates the org; a second user is added as editor.
        admin = _register(client, email="admin@acme.com", org_name="Acme")
        org_id = admin["organization_id"]

        viewer = User(
            id=str(uuid4()),
            email="view@acme.com",
            full_name="Viewer",
            password_hash=hash_password(STRONG_PW),
            is_active=True,
        )
        db.add(viewer)
        db.add(OrganizationMembership(
            id=str(uuid4()),
            organization_id=org_id,
            user_id=viewer.id,
            role=MemberRole.editor,
            is_default=True,
        ))
        db.commit()

        viewer_token = create_access_token(user_id=viewer.id, org_id=org_id)
        r = client.get("/audit", headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_filters_by_entity_type(self, client, db):
        reg = _register(client)
        org = reg["organization_id"]
        _seed_log(db, org_id=org, entity_type="deal", action="create")
        _seed_log(db, org_id=org, entity_type="memo", action="create")
        _seed_log(db, org_id=org, entity_type="memo", action="update")

        r = client.get(
            "/audit?entity_type=memo",
            headers=_auth(reg["access_token"]),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 2
        assert all(i["entity_type"] == "memo" for i in body["items"])

    def test_pagination(self, client, db):
        reg = _register(client)
        org = reg["organization_id"]
        # Use entity_type="deal" so the register row (entity_type="user")
        # doesn't shift pagination boundaries.
        for i in range(7):
            _seed_log(db, org_id=org, entity_type="deal", action="create",
                      new_values={"i": i})

        r = client.get(
            "/audit?entity_type=deal&limit=3&offset=0",
            headers=_auth(reg["access_token"]),
        )
        body = r.json()
        assert body["total"] == 7
        assert len(body["items"]) == 3
        assert body["limit"] == 3 and body["offset"] == 0

        r2 = client.get(
            "/audit?entity_type=deal&limit=3&offset=6",
            headers=_auth(reg["access_token"]),
        )
        # Only the 7th row should land on the last page.
        assert len(r2.json()["items"]) == 1

    def test_actor_email_is_surfaced(self, client, db):
        reg = _register(client)
        org = reg["organization_id"]
        _seed_log(db, org_id=org, action="create",
                  actor_id=reg["user_id"], new_values={"n": 1})

        r = client.get("/audit", headers=_auth(reg["access_token"]))
        item = r.json()["items"][0]
        assert item["actor_email"] == "alice@example.com"
        assert item["actor_name"] == "Alice"
