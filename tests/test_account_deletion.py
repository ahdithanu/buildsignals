"""Self-service account deletion — POST /auth/delete-account (GDPR erasure)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.deal import Deal
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.services.rate_limiter import limiter
from app.services.security import hash_password

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


def _add_admin(db, org_id):
    """Add a second admin to an org so the first user isn't the sole admin."""
    u = User(id=str(uuid4()), email=f"co-{uuid4().hex[:6]}@x.com",
             password_hash=hash_password(STRONG_PW), full_name="Co Admin")
    db.add(u); db.flush()
    db.add(OrganizationMembership(id=str(uuid4()), organization_id=org_id,
           user_id=u.id, role=MemberRole.admin, is_default=False))
    db.commit()
    return u.id


def test_wrong_password_is_rejected(client):
    reg = _register(client, email="a@x.com", org_name="Acme")
    r = client.post("/auth/delete-account", json={"password": "nope"},
                    headers=_auth(reg["access_token"]))
    assert r.status_code == 403
    # Still there.
    assert client.get("/auth/me", headers=_auth(reg["access_token"])).status_code == 200


def test_sole_admin_cannot_self_delete(client):
    # A freshly registered user is the only admin of their new org.
    reg = _register(client, email="solo@x.com", org_name="Solo Org")
    r = client.post("/auth/delete-account", json={"password": STRONG_PW},
                    headers=_auth(reg["access_token"]))
    assert r.status_code == 409
    assert "only admin" in r.json()["detail"].lower()
    assert "Solo Org" in r.json()["detail"]


def test_self_delete_removes_user_but_keeps_org(client, db):
    reg = _register(client, email="leaver@x.com", org_name="Shared Org")
    org_id = reg["organization_id"]
    co_admin_id = _add_admin(db, org_id)  # so leaver isn't the sole admin

    r = client.post("/auth/delete-account", json={"password": STRONG_PW},
                    headers=_auth(reg["access_token"]))
    assert r.status_code == 204

    # User + their memberships are gone.
    assert db.get(User, reg["user_id"]) is None
    assert db.query(OrganizationMembership).filter(
        OrganizationMembership.user_id == reg["user_id"]).count() == 0
    # Org and the co-admin survive.
    assert db.get(User, co_admin_id) is not None
    assert db.query(OrganizationMembership).filter(
        OrganizationMembership.organization_id == org_id).count() == 1


def test_authored_org_data_survives_with_authorship_nulled(client, db):
    reg = _register(client, email="author@x.com", org_name="Authoring Org")
    org_id = reg["organization_id"]
    _add_admin(db, org_id)

    # A deal created by the user (created_by FK is SET NULL on user delete).
    deal = Deal(id=str(uuid4()), organization_id=org_id, name="Their deal",
                created_by=reg["user_id"])
    db.add(deal); db.commit()
    deal_id = deal.id

    r = client.post("/auth/delete-account", json={"password": STRONG_PW},
                    headers=_auth(reg["access_token"]))
    assert r.status_code == 204

    db.expire_all()
    survived = db.get(Deal, deal_id)
    assert survived is not None, "org's deal must survive user deletion"
    assert survived.created_by is None, "authorship link should be severed"
