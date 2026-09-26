"""Prompt registry authorization, isolation, versioning, preview, and audit tests."""

from uuid import uuid4

import pytest

from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.prompt_registry import PromptVersion
from app.services.rate_limiter import limiter

ROOT = "/v1/prompts"


@pytest.fixture(autouse=True)
def _auth(monkeypatch):
    monkeypatch.setattr("app.middleware.auth_context.ALLOW_ANONYMOUS", False)
    limiter.clear()
    yield
    limiter.clear()


def _register(client, label):
    response = client.post("/v1/auth/register", json={
        "email": f"prompt-{label}@example.com", "password": "CorrectHorseBattery42",
        "full_name": f"Prompt Admin {label}", "organization_name": f"Prompt Org {label}",
    })
    assert response.status_code == 201, response.text
    return response.json()


def _headers(user):
    return {"Authorization": f"Bearer {user['access_token']}"}


def _create(client, user, key="memo-summary"):
    response = client.post(ROOT, headers=_headers(user), json={
        "key": key, "name": "Memo summary", "workflow": "opportunity_memo",
        "description": "Candidate wording, not a live memo override",
        "body": "Summarize {{deal_name}} using cited evidence.", "variables": ["deal_name"],
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_strict_admin_even_in_demo_mode(client, db, monkeypatch):
    monkeypatch.setattr("app.middleware.auth_context.ALLOW_ANONYMOUS", True)
    assert client.get(ROOT).status_code == 401
    user = _register(client, "role")
    membership = db.query(OrganizationMembership).filter_by(user_id=user["user_id"]).one()
    membership.role = MemberRole.viewer
    db.commit()
    assert client.get(ROOT, headers=_headers(user)).status_code == 403
    assert client.post(ROOT, headers=_headers(user), json={}).status_code == 403


def test_versions_are_immutable_and_activation_is_audited(client, db):
    user = _register(client, "versions")
    created = _create(client, user)
    template_id = created["id"]
    assert created["active_version"] is None
    assert created["versions"][0]["version"] == 1
    assert created["history"][0]["action"] == "create"
    first_checksum = created["versions"][0]["checksum"]

    rendered = client.post(f"{ROOT}/{template_id}/preview", headers=_headers(user), json={
        "version": 1, "values": {"deal_name": "Acme site"},
    })
    assert rendered.status_code == 200, rendered.text
    assert rendered.json()["rendered"] == "Summarize Acme site using cited evidence."
    assert client.post(f"{ROOT}/{template_id}/preview", headers=_headers(user), json={
        "version": 1, "values": {},
    }).status_code == 422

    revision = client.post(f"{ROOT}/{template_id}/versions", headers=_headers(user), json={
        "body": "Assess {{deal_name}} against public records.", "variables": ["deal_name"],
    })
    assert revision.status_code == 201, revision.text
    assert [item["version"] for item in revision.json()["versions"]] == [2, 1]
    assert revision.json()["versions"][1]["checksum"] == first_checksum
    assert db.query(PromptVersion).filter_by(template_id=template_id, version=1).one().body == created["versions"][0]["body"]

    activated = client.post(f"{ROOT}/{template_id}/versions/2/activate", headers=_headers(user))
    assert activated.status_code == 200, activated.text
    assert activated.json()["active_version"] == 2
    rollback = client.post(f"{ROOT}/{template_id}/versions/1/activate", headers=_headers(user))
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["active_version"] == 1
    assert [item["action"] for item in rollback.json()["history"][:3]] == ["rollback", "activate", "version_create"]
    assert client.post(f"{ROOT}/{template_id}/versions/1/activate", headers=_headers(user)).json()["history"] == rollback.json()["history"]


@pytest.mark.parametrize("body,variables", [
    ("Hello {{name}}", []), ("Hello {{name}}", ["name", "name"]),
    ("Hello {{Name}}", ["Name"]), ("Hello {{name", ["name"]),
    ("Hello", ["name"]),
])
def test_invalid_placeholder_contract_rejected(client, body, variables):
    user = _register(client, f"invalid-{uuid4().hex[:8]}")
    response = client.post(ROOT, headers=_headers(user), json={
        "key": "invalid", "name": "Invalid", "workflow": "copilot_answer",
        "body": body, "variables": variables,
    })
    assert response.status_code == 422


def test_isolation_and_duplicate_key(client):
    first = _register(client, "tenant-a")
    second = _register(client, "tenant-b")
    a = _create(client, first)
    assert client.get(ROOT, headers=_headers(second)).json() == []
    assert client.get(f"{ROOT}/{a['id']}", headers=_headers(second)).status_code == 404
    assert client.post(f"{ROOT}/{a['id']}/versions", headers=_headers(second), json={
        "body": "Other org", "variables": [],
    }).status_code == 404
    assert client.post(f"{ROOT}/{a['id']}/versions/1/activate", headers=_headers(second)).status_code == 404
    assert client.post(f"{ROOT}/{a['id']}/preview", headers=_headers(second), json={
        "version": 1, "values": {"deal_name": "Other"},
    }).status_code == 404
    assert _create(client, second)["id"] != a["id"]
    duplicate = client.post(ROOT, headers=_headers(first), json={
        "key": "memo-summary", "name": "Duplicate", "workflow": "opportunity_memo",
        "body": "Plain text", "variables": [],
    })
    assert duplicate.status_code == 409
