import pytest

from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.user import User
from app.routes import auth
from app.services.rate_limiter import InMemoryRateLimiter


@pytest.fixture()
def session_identity(client, monkeypatch):
    monkeypatch.setattr(auth, "limiter", InMemoryRateLimiter())
    created = client.post("/v1/auth/register", json={
        "email": "revocation-check@example.com", "password": "SyntheticValidation42!", "full_name": "Synthetic Analyst",
    })
    assert created.status_code == 201, created.text
    identity = created.json()
    headers = {"Authorization": f"Bearer {identity['access_token']}"}
    deal = client.post("/v1/deals", json={"name": "LOCAL TEST private deal"}, headers=headers)
    assert deal.status_code == 201, deal.text
    return identity, headers, deal.json()["id"]


@pytest.mark.parametrize("change,expected", [
    ("inactive_user", 401), ("removed_membership", 403), ("inactive_org", 403), ("revoked_tokens", 401),
])
def test_every_business_read_rechecks_current_identity(client, db, session_identity, change, expected):
    identity, headers, deal_id = session_identity
    user = db.get(User, identity["user_id"])
    if change == "inactive_user":
        user.is_active = False
    elif change == "removed_membership":
        db.query(OrganizationMembership).filter_by(user_id=user.id, organization_id=identity["organization_id"]).delete()
    elif change == "inactive_org":
        db.get(Organization, identity["organization_id"]).is_active = False
    else:
        user.token_version += 1
    db.commit()
    for route in ("/deals", f"/deals/{deal_id}", "/signals", "/ingestion/sources", "/planning/events", "/parcels/unknown", "/auth/me"):
        response = client.get("/v1" + route, headers=headers)
        assert response.status_code == expected, (route, response.status_code, response.text)
        assert "LOCAL TEST private deal" not in response.text
        assert response.headers["cache-control"] == "no-store"
    assert client.get(f"/deals/{deal_id}", headers=headers).status_code == expected


def test_logout_all_immediately_revokes_access_but_new_login_works(client, session_identity):
    _, headers, deal_id = session_identity
    assert client.post("/v1/auth/logout-all", headers=headers).status_code == 204
    assert client.get(f"/v1/deals/{deal_id}", headers=headers).status_code == 401
    logged_in = client.post("/v1/auth/login", json={"email": "revocation-check@example.com", "password": "SyntheticValidation42!"})
    assert logged_in.status_code == 200
    fresh = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}
    assert client.get(f"/v1/deals/{deal_id}", headers=fresh).status_code == 200


def test_invalid_bearer_never_falls_back_to_anonymous_demo_reads(client, monkeypatch):
    from app.utils import auth_deps

    monkeypatch.setattr(auth_deps, "ALLOW_ANONYMOUS", True)
    for value in ("Bearer invalid", "Basic abc", "Bearer "):
        assert client.get("/v1/deals", headers={"Authorization": value}).status_code == 401
    assert client.get("/v1/deals").status_code == 200
    # Public endpoints do not treat unrelated stale Bearer state as their login protocol.
    assert client.get("/health", headers={"Authorization": "Bearer invalid"}).status_code == 200


def test_strict_dependency_denies_no_token_even_if_middleware_demo_mode(client, monkeypatch):
    from app.utils import auth_deps

    monkeypatch.setattr(auth_deps, "ALLOW_ANONYMOUS", False)
    assert client.get("/v1/deals").status_code == 401
    assert client.get("/health").status_code == 200


def test_role_revocation_applies_to_mutations_without_reissuing_token(client, db, session_identity):
    identity, headers, deal_id = session_identity
    from app.models.organization_membership import MemberRole

    member = db.query(OrganizationMembership).filter_by(user_id=identity["user_id"], organization_id=identity["organization_id"]).one()
    member.role = MemberRole.viewer
    db.commit()
    assert client.get(f"/v1/deals/{deal_id}", headers=headers).status_code == 200
    assert client.patch(f"/v1/deals/{deal_id}", json={"name": "Forbidden change"}, headers=headers).status_code == 403


def test_auth_and_authenticated_business_responses_are_not_http_cached(client, session_identity):
    _, headers, deal_id = session_identity
    response = client.get(f"/v1/deals/{deal_id}", headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "authorization" in response.headers["vary"].lower()
    login = client.post("/v1/auth/login", json={"email": "revocation-check@example.com", "password": "SyntheticValidation42!"})
    assert login.status_code == 200
    assert login.headers["cache-control"] == "no-store"
    invalid_login = client.post("/v1/auth/login", json={"email": "revocation-check@example.com", "password": "wrong"})
    assert invalid_login.status_code == 401
    assert invalid_login.headers["cache-control"] == "no-store"
