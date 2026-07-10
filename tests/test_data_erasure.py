"""GDPR right-to-erasure — POST /organizations/{org_id}/delete.

The load-bearing guarantee is tenant isolation: erasing org A must not touch
org B. Plus the guard rails (admin + active-org, name confirmation, default
org protected) and orphaned-user cleanup.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.contact import Contact
from app.models.deal import Deal
from app.models.memo import Memo
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.services.rate_limiter import limiter

STRONG_PW = "CorrectHorseBattery42"


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.clear()
    yield
    limiter.clear()


def _register(client, *, email, org_name):
    r = client.post("/auth/register", json={
        "email": email, "password": STRONG_PW,
        "full_name": email.split("@")[0].title(), "organization_name": org_name,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed(db, *, org_id, label):
    deal = Deal(id=str(uuid4()), organization_id=org_id, name=f"Deal {label}",
                address=f"{label} St", city="Austin", state="TX")
    db.add(deal); db.flush()
    db.add_all([
        Contact(id=str(uuid4()), organization_id=org_id, deal_id=deal.id,
                name=f"Contact {label}", email=f"c-{label}@example.com"),
        Memo(id=str(uuid4()), organization_id=org_id, deal_id=deal.id,
             title=f"Memo {label}", content="body"),
    ])
    db.commit()
    return deal.id


def _org_name(db, org_id):
    return db.get(Organization, org_id).name


def test_wrong_confirmation_text_is_rejected(client):
    reg = _register(client, email="a@example.com", org_name="Acme Capital")
    r = client.post(f"/organizations/{reg['organization_id']}/delete",
                    json={"confirm": "wrong name"}, headers=_auth(reg["access_token"]))
    assert r.status_code == 400
    # Nothing deleted — org still resolvable.
    assert client.get("/organizations/me", headers=_auth(reg["access_token"])).status_code == 200


def test_default_org_cannot_be_deleted(client, db):
    from app.utils.org_scope import DEFAULT_ORG_ID
    # Ensure a default org row + an admin of it exist.
    if not db.get(Organization, DEFAULT_ORG_ID):
        db.add(Organization(id=DEFAULT_ORG_ID, name="Default", slug="default"))
        db.commit()
    user = User(id=str(uuid4()), email=f"d-{uuid4().hex[:6]}@example.com",
                password_hash="x", full_name="D")
    db.add(user); db.flush()
    db.add(OrganizationMembership(id=str(uuid4()), organization_id=DEFAULT_ORG_ID,
           user_id=user.id, role=MemberRole.admin, is_default=True))
    db.commit()
    from app.services.security import create_access_token
    token = create_access_token(user_id=user.id, org_id=DEFAULT_ORG_ID)
    r = client.post(f"/organizations/{DEFAULT_ORG_ID}/delete",
                    json={"confirm": "Default"}, headers=_auth(token))
    assert r.status_code == 403


def test_erasure_removes_all_org_data(client, db):
    reg = _register(client, email="owner@acme.com", org_name="Acme Capital")
    org_id = reg["organization_id"]
    _seed(db, org_id=org_id, label="acme")

    assert db.query(Deal).filter(Deal.organization_id == org_id).count() == 1

    r = client.post(f"/organizations/{org_id}/delete",
                    json={"confirm": "Acme Capital"}, headers=_auth(reg["access_token"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["organization_id"] == org_id
    assert body["rows_deleted"]["deals"] == 1
    assert body["rows_deleted"]["contacts"] == 1

    # Everything for the org is gone.
    assert db.get(Organization, org_id) is None
    assert db.query(Deal).filter(Deal.organization_id == org_id).count() == 0
    assert db.query(Contact).filter(Contact.organization_id == org_id).count() == 0
    assert db.query(Memo).filter(Memo.organization_id == org_id).count() == 0
    assert db.query(OrganizationMembership).filter(
        OrganizationMembership.organization_id == org_id).count() == 0
    # Sole-org member was orphaned → erased.
    assert db.get(User, reg["user_id"]) is None


def test_erasure_does_not_touch_other_orgs(client, db):
    a = _register(client, email="a@x.com", org_name="Org Alpha")
    b = _register(client, email="b@y.com", org_name="Org Beta")
    _seed(db, org_id=a["organization_id"], label="alpha")
    b_deal = _seed(db, org_id=b["organization_id"], label="beta")

    r = client.post(f"/organizations/{a['organization_id']}/delete",
                    json={"confirm": "Org Alpha"}, headers=_auth(a["access_token"]))
    assert r.status_code == 200

    # Beta is fully intact — the tenant-isolation guarantee.
    assert db.get(Organization, b["organization_id"]) is not None
    assert db.query(Deal).filter(Deal.organization_id == b["organization_id"]).count() == 1
    assert db.get(Deal, b_deal) is not None
    assert db.get(User, b["user_id"]) is not None
    # Beta's admin can still use the app.
    assert client.get("/organizations/me", headers=_auth(b["access_token"])).status_code == 200


def test_user_in_another_org_is_preserved(client, db):
    """A member of the deleted org who ALSO belongs to another org keeps their
    account — only their membership in the deleted org goes."""
    a = _register(client, email="multi@x.com", org_name="Org One")
    # Give that same user a membership in a second org.
    org2 = Organization(id=str(uuid4()), name="Org Two", slug=f"two-{uuid4().hex[:6]}")
    db.add(org2); db.flush()
    db.add(OrganizationMembership(id=str(uuid4()), organization_id=org2.id,
           user_id=a["user_id"], role=MemberRole.editor, is_default=False))
    db.commit()

    r = client.post(f"/organizations/{a['organization_id']}/delete",
                    json={"confirm": "Org One"}, headers=_auth(a["access_token"]))
    assert r.status_code == 200
    # User survives (still in Org Two); their Org One membership is gone.
    assert db.get(User, a["user_id"]) is not None
    assert db.query(OrganizationMembership).filter(
        OrganizationMembership.user_id == a["user_id"]).count() == 1
