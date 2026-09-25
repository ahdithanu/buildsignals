"""Public self-registration must never enroll users into an existing tenant."""
from __future__ import annotations

import re
from uuid import uuid4

import pytest

from app.models.deal import Deal
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.services.account_lockout import lockout
from app.services.rate_limiter import limiter
from app.utils.org_scope import DEFAULT_ORG_ID

STRONG_PW = "CorrectHorseBattery42"
UNNAMED_ORG_PAYLOADS = [
    pytest.param({}, id="omitted"),
    pytest.param({"organization_name": None}, id="null"),
    pytest.param({"organization_name": ""}, id="empty"),
    pytest.param({"organization_name": " \t\n "}, id="whitespace"),
]


@pytest.fixture(autouse=True)
def _strict_auth_and_clean_limits(monkeypatch):
    monkeypatch.setattr("app.middleware.auth_context.ALLOW_ANONYMOUS", False)
    limiter.clear()
    lockout.clear()
    yield
    limiter.clear()
    lockout.clear()


def _register(client, email, **fields):
    response = client.post("/v1/auth/register", json={
        "email": email,
        "password": STRONG_PW,
        "full_name": "New User",
        **fields,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _auth(identity):
    return {"Authorization": f"Bearer {identity['access_token']}"}


def _seed_default_tenant(db):
    org = Organization(
        id=DEFAULT_ORG_ID,
        name="Confidential Default Workspace",
        slug="default",
    )
    db.add(org)
    db.flush()
    deal = Deal(
        id=str(uuid4()),
        organization_id=org.id,
        name="Confidential acquisition",
        notes="Private default-tenant diligence",
    )
    db.add(deal)
    db.commit()
    return org, deal


def _assert_new_admin(client, db, identity):
    assert identity["organization_id"] != DEFAULT_ORG_ID
    assert identity["role"] == "admin"
    memberships = db.query(OrganizationMembership).filter(
        OrganizationMembership.user_id == identity["user_id"],
    ).all()
    assert len(memberships) == 1
    assert memberships[0].organization_id == identity["organization_id"]
    assert memberships[0].role == MemberRole.admin
    assert memberships[0].is_default is True

    org = db.get(Organization, identity["organization_id"])
    assert org is not None and org.is_active
    assert org.name.strip() == org.name
    assert 0 < len(org.name) <= Organization.__table__.c.name.type.length
    assert 0 < len(org.slug) <= Organization.__table__.c.slug.type.length
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", org.slug)

    me = client.get("/v1/auth/me", headers=_auth(identity))
    assert me.status_code == 200, me.text
    assert me.json()["user"]["id"] == identity["user_id"]
    assert me.json()["organization_id"] == org.id
    assert me.json()["role"] == "admin"
    organizations = client.get("/v1/organizations/me", headers=_auth(identity))
    assert organizations.status_code == 200, organizations.text
    assert [item["organization"]["id"] for item in organizations.json()] == [org.id]
    return org


@pytest.mark.parametrize("fields", UNNAMED_ORG_PAYLOADS)
def test_unnamed_registrations_cannot_join_or_read_default_tenant(client, db, fields):
    default_org, confidential_deal = _seed_default_tenant(db)
    identities = [
        _register(client, "first@example.com", **fields),
        _register(client, "second@example.com", **fields),
    ]
    assert identities[0]["organization_id"] != identities[1]["organization_id"]
    assert db.query(Organization).count() == 3

    for identity in identities:
        _assert_new_admin(client, db, identity)
        deals = client.get("/v1/deals", headers=_auth(identity))
        assert deals.status_code == 200, deals.text
        assert deals.json() == []
        hidden = client.get(f"/v1/deals/{confidential_deal.id}", headers=_auth(identity))
        assert hidden.status_code == 404
        assert confidential_deal.notes not in hidden.text
        switch = client.post("/v1/auth/switch-org", headers=_auth(identity), json={
            "organization_id": default_org.id,
        })
        assert switch.status_code == 403

    assert db.query(OrganizationMembership).filter(
        OrganizationMembership.organization_id == DEFAULT_ORG_ID,
    ).count() == 0
    assert db.get(Deal, confidential_deal.id).organization_id == DEFAULT_ORG_ID


@pytest.mark.parametrize("fields", UNNAMED_ORG_PAYLOADS)
def test_registration_needs_no_default_org_or_seed_script(client, db, fields):
    assert db.query(Organization).count() == 0
    identity = _register(client, "unseeded@example.com", **fields)
    _assert_new_admin(client, db, identity)
    assert db.query(Organization).count() == 1
    assert db.get(Organization, DEFAULT_ORG_ID) is None

    refreshed = client.post("/v1/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["organization_id"] == identity["organization_id"]
    assert refreshed.json()["role"] == "admin"
    logged_in = client.post("/v1/auth/login", json={
        "email": "unseeded@example.com", "password": STRONG_PW,
    })
    assert logged_in.status_code == 200, logged_in.text
    assert logged_in.json()["organization_id"] == identity["organization_id"]
    assert logged_in.json()["role"] == "admin"


@pytest.mark.parametrize("name", ["Confidential Default Workspace", "Acme Capital", "A" * 255])
def test_identical_explicit_display_names_still_create_separate_tenants(client, db, name):
    default_org, _ = _seed_default_tenant(db)
    first = _register(client, "first@example.com", organization_name=name)
    second = _register(client, "second@example.com", organization_name=name)
    first_org = _assert_new_admin(client, db, first)
    second_org = _assert_new_admin(client, db, second)

    assert len({first_org.id, second_org.id, default_org.id}) == 3
    assert first_org.name == second_org.name == name
    assert first_org.slug != second_org.slug
    assert db.query(Organization).count() == 3
    denied = client.post("/v1/auth/switch-org", headers=_auth(second), json={
        "organization_id": first_org.id,
    })
    assert denied.status_code == 403


@pytest.mark.parametrize("full_name,expected_fragment", [
    ("A" * 255, "A" * 200),
    ("  Alex \n Smith\t ", "Alex Smith"),
    (" \t ", "Personal"),
    ("\u674e \u96f7", "\u674e \u96f7"),
])
def test_derived_names_are_nonempty_bounded_and_have_safe_slugs(client, db, full_name, expected_fragment):
    identity = _register(client, "name-check@example.com", full_name=full_name)
    org = _assert_new_admin(client, db, identity)
    assert expected_fragment in org.name
    assert "\n" not in org.name and "\t" not in org.name


def test_oversized_explicit_org_name_is_still_rejected(client, db):
    response = client.post("/v1/auth/register", json={
        "email": "oversized@example.com", "password": STRONG_PW,
        "full_name": "New User", "organization_name": "A" * 256,
    })
    assert response.status_code == 422
    assert db.query(Organization).count() == 0
    assert db.query(OrganizationMembership).count() == 0


def test_joining_an_existing_team_requires_an_explicit_admin_grant(client, db):
    owner = _register(client, "owner@example.com")
    newcomer = _register(client, "newcomer@example.com")
    _assert_new_admin(client, db, owner)
    _assert_new_admin(client, db, newcomer)
    deal = Deal(id=str(uuid4()), organization_id=owner["organization_id"], name="Team-only deal")
    db.add(deal)
    db.commit()
    assert client.get(f"/v1/deals/{deal.id}", headers=_auth(newcomer)).status_code == 404

    member_path = f"/v1/organizations/{owner['organization_id']}/members"
    invitation = {"email": "newcomer@example.com", "role": "editor"}
    assert client.post(member_path, headers=_auth(newcomer), json=invitation).status_code == 403
    granted = client.post(member_path, headers=_auth(owner), json=invitation)
    assert granted.status_code == 201, granted.text
    switched = client.post("/v1/auth/switch-org", headers=_auth(newcomer), json={
        "organization_id": owner["organization_id"],
    })
    assert switched.status_code == 200, switched.text
    assert switched.json()["role"] == "editor"
    visible = client.get(f"/v1/deals/{deal.id}", headers=_auth(switched.json()))
    assert visible.status_code == 200, visible.text
    assert visible.json()["id"] == deal.id
