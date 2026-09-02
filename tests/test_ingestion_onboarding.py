from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.audit_log import AuditLog
from app.models.ingestion import IngestionSource
from app.models.ingestion_onboarding import (
    OrganizationIngestionEnrollment,
    OrganizationIngestionEnrollmentSource,
)
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.services.ingestion.onboarding import build_ingestion_onboarding_plan
from app.services.rate_limiter import limiter
from app.services.security import create_access_token, hash_password

STRONG_PASSWORD = "CorrectHorseBattery42"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter.clear()
    yield
    limiter.clear()


def _register(client, *, email: str, organization_name: str) -> dict:
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": STRONG_PASSWORD,
            "full_name": email.split("@")[0].title(),
            "organization_name": organization_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _add_member(db, *, org_id: str, role: MemberRole) -> str:
    user = User(
        id=str(uuid4()),
        email=f"{role.value}-{uuid4().hex[:8]}@example.com",
        full_name=role.value.title(),
        password_hash=hash_password(STRONG_PASSWORD),
        is_active=True,
    )
    db.add(user)
    db.add(
        OrganizationMembership(
            id=str(uuid4()),
            organization_id=org_id,
            user_id=user.id,
            role=role,
            is_default=True,
        )
    )
    db.commit()
    return create_access_token(user_id=user.id, org_id=org_id)


def _selected_states_payload(*states: str) -> dict:
    return {
        "coverage_mode": "selected_states",
        "state_codes": list(states),
        "record_types": ["permit", "planning", "parcel"],
        "rollout_waves": [1, 2, 3, 4],
        "shard_count": 4,
        "enabled": True,
    }


def test_nationwide_plan_reports_reviewed_coverage_and_gaps():
    plan = build_ingestion_onboarding_plan()

    assert plan.source_count == 134
    assert len(plan.covered_regions) == 44
    assert "DC" in plan.covered_regions
    assert plan.missing_regions == ["IA", "MS", "MT", "NM", "OK", "WV", "WY"]
    assert plan.permit_source_count == 92
    assert plan.planning_source_count == 1
    assert plan.parcel_source_count == 41
    assert plan.automatic_source_count == 133
    assert plan.manual_source_count == 1


def test_plan_requires_authentication_and_allows_read_roles(client, db):
    registration = _register(
        client,
        email="onboarding-admin@example.com",
        organization_name="Onboarding Admin",
    )
    viewer_token = _add_member(
        db,
        org_id=registration["organization_id"],
        role=MemberRole.viewer,
    )
    payload = _selected_states_payload("TX", "GA")

    assert client.post("/ingestion/onboarding/plan", json=payload).status_code == 401
    response = client.post(
        "/ingestion/onboarding/plan",
        json=payload,
        headers=_headers(viewer_token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requested_regions"] == ["GA", "TX"]
    assert body["missing_regions"] == []
    assert {source["region"] for source in body["sources"]} == {"GA", "TX"}


def test_only_admin_can_activate_ingestion(client, db):
    registration = _register(
        client,
        email="activation-admin@example.com",
        organization_name="Activation Admin",
    )
    editor_token = _add_member(
        db,
        org_id=registration["organization_id"],
        role=MemberRole.editor,
    )
    viewer_token = _add_member(
        db,
        org_id=registration["organization_id"],
        role=MemberRole.viewer,
    )
    payload = _selected_states_payload("TX")

    assert (
        client.put(
            "/ingestion/onboarding/enrollment",
            json=payload,
            headers=_headers(editor_token),
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/ingestion/onboarding/enrollment",
            json=payload,
            headers=_headers(viewer_token),
        ).status_code
        == 403
    )

    response = client.put(
        "/ingestion/onboarding/enrollment",
        json=payload,
        headers=_headers(registration["access_token"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["enrollment_sources_created"] > 0


def test_activation_is_idempotent_audited_and_preserves_custom_source(client, db):
    registration = _register(
        client,
        email="idempotent-admin@example.com",
        organization_name="Idempotent Org",
    )
    org_id = registration["organization_id"]
    token = registration["access_token"]
    custom_source = IngestionSource(
        organization_id=org_id,
        key="customer_private_feed",
        name="Customer Private Feed",
        adapter="json_api",
        record_type="permit",
        jurisdiction="Private, TX",
        base_url="https://customer.example.test/permits",
        settings={"customer_managed": True},
        is_active=False,
    )
    db.add(custom_source)
    db.commit()

    first = client.put(
        "/ingestion/onboarding/enrollment",
        json=_selected_states_payload("TX", "GA"),
        headers=_headers(token),
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["enrollment_sources_created"] == first_body["plan"]["source_count"]

    second = client.put(
        "/ingestion/onboarding/enrollment",
        json=_selected_states_payload("TX", "GA"),
        headers=_headers(token),
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["enrollment_sources_created"] == 0
    assert second_body["enrollment_sources_updated"] == 0
    assert second_body["enrollment_sources_unchanged"] == second_body["plan"]["source_count"]

    db.expire_all()
    preserved = (
        db.query(IngestionSource)
        .filter_by(
            organization_id=org_id,
            key="customer_private_feed",
        )
        .one()
    )
    assert preserved.name == "Customer Private Feed"
    assert preserved.is_active is False
    assert preserved.settings == {"customer_managed": True}
    assert (
        db.query(AuditLog)
        .filter_by(
            organization_id=org_id,
            entity_type="ingestion_enrollment",
        )
        .count()
        == 2
    )


def test_scope_narrowing_removes_unselected_enrollment_sources(client, db):
    registration = _register(
        client,
        email="narrow-admin@example.com",
        organization_name="Narrow Scope Org",
    )
    headers = _headers(registration["access_token"])
    org_id = registration["organization_id"]

    initial = client.put(
        "/ingestion/onboarding/enrollment",
        json=_selected_states_payload("TX", "GA"),
        headers=headers,
    )
    assert initial.status_code == 200, initial.text
    narrowed = client.put(
        "/ingestion/onboarding/enrollment",
        json=_selected_states_payload("TX"),
        headers=headers,
    )
    assert narrowed.status_code == 200, narrowed.text
    assert narrowed.json()["enrollment_sources_removed"] > 0

    rows = db.query(OrganizationIngestionEnrollmentSource).filter_by(organization_id=org_id).all()
    assert all(row.status == "removed" for row in rows if row.state_code == "GA")
    assert all(
        row.status in {"active", "manual", "paused"} for row in rows if row.state_code == "TX"
    )


def test_enrollment_read_is_isolated_to_active_organization(client):
    org_a = _register(
        client,
        email="org-a-admin@example.com",
        organization_name="Onboarding Org A",
    )
    org_b = _register(
        client,
        email="org-b-admin@example.com",
        organization_name="Onboarding Org B",
    )
    activated = client.put(
        "/ingestion/onboarding/enrollment",
        json=_selected_states_payload("TX"),
        headers=_headers(org_a["access_token"]),
    )
    assert activated.status_code == 200, activated.text

    own = client.get(
        "/ingestion/onboarding/enrollment",
        headers=_headers(org_a["access_token"]),
    )
    other = client.get(
        "/ingestion/onboarding/enrollment",
        headers=_headers(org_b["access_token"]),
    )

    assert own.status_code == 200
    assert own.json()["organization_id"] == org_a["organization_id"]
    assert other.status_code == 404


def test_selected_states_validation_rejects_empty_scope(client):
    registration = _register(
        client,
        email="validation-admin@example.com",
        organization_name="Validation Org",
    )
    response = client.post(
        "/ingestion/onboarding/plan",
        json={"coverage_mode": "selected_states", "state_codes": []},
        headers=_headers(registration["access_token"]),
    )
    assert response.status_code == 422


def test_activation_persists_one_enrollment_per_organization(client, db):
    registration = _register(
        client,
        email="single-admin@example.com",
        organization_name="Single Enrollment Org",
    )
    response = client.put(
        "/ingestion/onboarding/enrollment",
        json=_selected_states_payload("GA"),
        headers=_headers(registration["access_token"]),
    )
    assert response.status_code == 200, response.text
    assert (
        db.query(OrganizationIngestionEnrollment)
        .filter_by(organization_id=registration["organization_id"])
        .count()
        == 1
    )
