"""Tests for the GDPR data export endpoint.

Covers the security contract (admin-only, single-org), the shape of the
dump, and the hard guarantee that `password_hash` never leaks.
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.models.contact import Contact
from app.models.deal import Deal
from app.models.memo import Memo
from app.services.rate_limiter import limiter

STRONG_PW = "CorrectHorseBattery42"


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Per-process /auth/register rate limit would otherwise trip on the
    second org registration in a single test."""
    limiter.clear()
    yield
    limiter.clear()


def _register(client, *, email, org_name):
    r = client.post("/auth/register", json={
        "email": email,
        "password": STRONG_PW,
        "full_name": email.split("@")[0].title(),
        "organization_name": org_name,
    })
    assert r.status_code == 201, r.text
    return r.json()  # {access_token, user_id, organization_id, role}


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_org_data(db, *, org_id, label):
    """Drop a deal + contact + memo into the given org so we have something
    to assert appears in (or is excluded from) the export."""
    deal = Deal(
        id=str(uuid4()),
        organization_id=org_id,
        name=f"Deal {label}",
        address=f"{label} Main St",
        city="Austin",
        state="TX",
    )
    db.add(deal)
    db.flush()
    contact = Contact(
        id=str(uuid4()),
        organization_id=org_id,
        deal_id=deal.id,
        name=f"Contact {label}",
        email=f"c-{label}@example.com",
    )
    memo = Memo(
        id=str(uuid4()),
        organization_id=org_id,
        deal_id=deal.id,
        title=f"Memo {label}",
        content=f"Body for {label}",
    )
    db.add_all([contact, memo])
    db.commit()
    return {"deal_id": deal.id, "contact_id": contact.id, "memo_id": memo.id}


def _no_password_hash_anywhere(blob) -> bool:
    """Walk the payload and assert no `password_hash` key appears at any
    depth. Belt and suspenders: also forbid the literal hash bytes string
    `password_hash` showing up as a value."""
    serialized = json.dumps(blob)
    if '"password_hash"' in serialized:
        return False
    return True


class TestDataExport:
    def test_admin_export_includes_own_org_and_excludes_others(self, client, db):
        reg_a = _register(client, email="alice@acme.com", org_name="Acme")
        reg_b = _register(client, email="bob@beta.com", org_name="Beta")

        seeds_a = _seed_org_data(db, org_id=reg_a["organization_id"], label="A")
        seeds_b = _seed_org_data(db, org_id=reg_b["organization_id"], label="B")

        r = client.get(
            f"/organizations/{reg_a['organization_id']}/export",
            headers=_auth(reg_a["access_token"]),
        )
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["organization_id"] == reg_a["organization_id"]
        assert body["organization"]["name"] == "Acme"
        assert "exported_at" in body

        deal_ids = {d["id"] for d in body["deals"]}
        contact_ids = {c["id"] for c in body["contacts"]}
        memo_ids = {m["id"] for m in body["memos"]}

        assert seeds_a["deal_id"] in deal_ids
        assert seeds_a["contact_id"] in contact_ids
        assert seeds_a["memo_id"] in memo_ids

        # Cross-tenant negative: org B's rows must not appear.
        assert seeds_b["deal_id"] not in deal_ids
        assert seeds_b["contact_id"] not in contact_ids
        assert seeds_b["memo_id"] not in memo_ids

    def test_non_admin_gets_403(self, client, db):
        from app.models.organization_membership import MemberRole, OrganizationMembership

        reg = _register(client, email="alice@acme.com", org_name="Acme")
        # Demote the registering user from admin → editor. The fresh JWT was
        # issued as admin, but our guard re-reads the membership row, so
        # demotion takes effect immediately.
        membership = (
            db.query(OrganizationMembership)
            .filter(OrganizationMembership.user_id == reg["user_id"])
            .first()
        )
        membership.role = MemberRole.editor
        db.commit()

        r = client.get(
            f"/organizations/{reg['organization_id']}/export",
            headers=_auth(reg["access_token"]),
        )
        # The JWT still claims admin, but the membership row is the source
        # of truth for `principal['role']` — so this is a 403.
        # Note: get_current_user returns role from the membership lookup.
        # We expect 403 from the explicit admin check in the route.
        assert r.status_code == 403, r.text

    def test_admin_cannot_export_other_org(self, client, db):
        reg_a = _register(client, email="alice@acme.com", org_name="Acme")
        reg_b = _register(client, email="bob@beta.com", org_name="Beta")

        r = client.get(
            f"/organizations/{reg_b['organization_id']}/export",
            headers=_auth(reg_a["access_token"]),
        )
        assert r.status_code == 403, r.text

    def test_unauthenticated_returns_401(self, client):
        r = client.get(f"/organizations/{uuid4()}/export")
        assert r.status_code == 401

    def test_password_hash_never_leaks(self, client, db):
        reg = _register(client, email="alice@acme.com", org_name="Acme")
        _seed_org_data(db, org_id=reg["organization_id"], label="A")

        r = client.get(
            f"/organizations/{reg['organization_id']}/export",
            headers=_auth(reg["access_token"]),
        )
        assert r.status_code == 200
        body = r.json()
        assert _no_password_hash_anywhere(body), (
            "password_hash key found in export payload"
        )

    def test_members_section_includes_email_not_hash(self, client, db):
        reg = _register(client, email="alice@acme.com", org_name="Acme")

        r = client.get(
            f"/organizations/{reg['organization_id']}/export",
            headers=_auth(reg["access_token"]),
        )
        assert r.status_code == 200
        body = r.json()
        assert "members" in body
        assert len(body["members"]) >= 1
        member = body["members"][0]
        assert "user" in member
        assert member["user"]["email"] == "alice@acme.com"
        assert member["user"]["full_name"] == "Alice"
        assert "password_hash" not in member["user"]
        assert member["role"] == "admin"

    def test_export_writes_audit_log(self, client, db):
        from app.models.audit_log import AuditLog

        reg = _register(client, email="alice@acme.com", org_name="Acme")
        r = client.get(
            f"/organizations/{reg['organization_id']}/export",
            headers=_auth(reg["access_token"]),
        )
        assert r.status_code == 200

        # Refresh in case the test session is caching.
        db.expire_all()
        logs = (
            db.query(AuditLog)
            .filter(
                AuditLog.organization_id == reg["organization_id"],
                AuditLog.action == "data_export",
            )
            .all()
        )
        assert len(logs) == 1
        assert logs[0].entity_type == "organization"
        assert logs[0].entity_id == reg["organization_id"]
        assert logs[0].actor_id == reg["user_id"]
