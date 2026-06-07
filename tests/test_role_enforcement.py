"""RBAC route enforcement: viewers can't mutate; editors and admins can.

The audit (every write route carries a `require_role` dependency) is the
actual security win. These tests just prove the dep is wired: a viewer's
token hits 403 on a representative slice of write endpoints, while
editor and admin tokens never get 403/401 (they may get 404 if the deal
doesn't exist — what matters is they passed the role gate).
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


def _register(client, email="admin@acme.com", org_name="Acme"):
    r = client.post("/auth/register", json={
        "email": email, "password": STRONG_PW,
        "full_name": email.split("@")[0].title(),
        "organization_name": org_name,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _add_member(db, *, org_id: str, email: str, role: MemberRole) -> str:
    user = User(
        id=str(uuid4()),
        email=email,
        full_name=email.split("@")[0].title(),
        password_hash=hash_password(STRONG_PW),
        is_active=True,
    )
    db.add(user)
    db.add(OrganizationMembership(
        id=str(uuid4()),
        organization_id=org_id,
        user_id=user.id,
        role=role,
        is_default=True,
    ))
    db.commit()
    return create_access_token(user_id=user.id, org_id=org_id)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def roles(client, db):
    """Set up admin, editor, viewer in a single org. Also create one deal so
    deal-scoped routes have something to target."""
    admin_reg = _register(client, email="admin@acme.com")
    org_id = admin_reg["organization_id"]
    admin_token = admin_reg["access_token"]

    editor_token = _add_member(db, org_id=org_id, email="editor@acme.com", role=MemberRole.editor)
    viewer_token = _add_member(db, org_id=org_id, email="viewer@acme.com", role=MemberRole.viewer)

    # Create a deal as admin so we have something to mutate / target.
    r = client.post(
        "/deals",
        json={"name": "Test Deal", "address": "1 Main St", "property_type": "multifamily"},
        headers=_auth(admin_token),
    )
    assert r.status_code == 201, r.text
    deal_id = r.json()["id"]

    # Create a contact too so DELETE /contacts/{id} has a target.
    rc = client.post(
        f"/deals/{deal_id}/contacts",
        json={"name": "C1", "role": "broker", "status": "not_contacted"},
        headers=_auth(admin_token),
    )
    assert rc.status_code == 201, rc.text
    contact_id = rc.json()["id"]

    return {
        "org_id": org_id,
        "deal_id": deal_id,
        "contact_id": contact_id,
        "admin": admin_token,
        "editor": editor_token,
        "viewer": viewer_token,
    }


def _make_request(client, method: str, url: str, token: str, body=None):
    headers = _auth(token)
    if method == "POST":
        return client.post(url, json=body or {}, headers=headers)
    if method == "PATCH":
        return client.patch(url, json=body or {}, headers=headers)
    if method == "PUT":
        return client.put(url, json=body or {}, headers=headers)
    if method == "DELETE":
        return client.delete(url, headers=headers)
    raise ValueError(method)


# Representative slice of write routes — proves the dep is wired across
# multiple route modules. Each tuple is (method, url_template, body).
ROUTES = [
    ("POST", "/deals", {"name": "X", "address": "1 St", "property_type": "multifamily"}),
    ("PATCH", "/deals/{deal_id}", {"name": "Renamed"}),
    ("POST", "/deals/{deal_id}/contacts", {"name": "New", "role": "broker", "status": "not_contacted"}),
    ("POST", "/deals/{deal_id}/generate-memo", None),
    ("DELETE", "/contacts/{contact_id}", None),
]


@pytest.mark.parametrize("method,url_tmpl,body", ROUTES)
def test_viewer_is_forbidden(client, roles, method, url_tmpl, body):
    url = url_tmpl.format(deal_id=roles["deal_id"], contact_id=roles["contact_id"])
    r = _make_request(client, method, url, roles["viewer"], body)
    assert r.status_code == 403, (
        f"viewer should be 403 on {method} {url}, got {r.status_code}: {r.text}"
    )


@pytest.mark.parametrize("method,url_tmpl,body", ROUTES)
def test_editor_is_not_forbidden(client, roles, method, url_tmpl, body):
    url = url_tmpl.format(deal_id=roles["deal_id"], contact_id=roles["contact_id"])
    r = _make_request(client, method, url, roles["editor"], body)
    # Editor passed the gate — anything but 401/403 is acceptable. They may
    # get 200/201/204 on success, or 404 if a prior test in the parametrize
    # already deleted the resource. The contract under test is "no 403".
    assert r.status_code not in (401, 403), (
        f"editor should NOT be 401/403 on {method} {url}, got {r.status_code}: {r.text}"
    )


@pytest.mark.parametrize("method,url_tmpl,body", ROUTES)
def test_admin_is_not_forbidden(client, roles, method, url_tmpl, body):
    url = url_tmpl.format(deal_id=roles["deal_id"], contact_id=roles["contact_id"])
    r = _make_request(client, method, url, roles["admin"], body)
    assert r.status_code not in (401, 403), (
        f"admin should NOT be 401/403 on {method} {url}, got {r.status_code}: {r.text}"
    )
