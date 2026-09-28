from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import app.utils.api_key_deps as api_key_deps
from app.models.api_key import OrganizationApiKey
from app.models.api_usage import OrganizationApiKeyUsageEvent
from app.models.deal import Deal
from app.models.graph import (
    GraphEntity,
    GraphEntityLink,
    GraphEntityType,
    GraphRelationship,
    GraphRelationshipEvidence,
    GraphRelationshipType,
)
from app.models.signal import Signal
from app.services.api_key_service import create_api_key, revoke_api_key
from app.services.rate_limiter import limiter

STRONG_PW = "CorrectHorseBattery42"


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.clear()
    yield
    limiter.clear()


def _register(client, *, email: str, org_name: str) -> dict:
    response = client.post("/auth/register", json={
        "email": email,
        "password": STRONG_PW,
        "full_name": email.split("@")[0].title(),
        "organization_name": org_name,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _issue_key(db, *, org_id: str, user_id: str, scopes: list[str]) -> tuple[OrganizationApiKey, str]:
    api_key, secret = create_api_key(
        db,
        organization_id=org_id,
        name="Warehouse export",
        scopes=scopes,
        actor_id=user_id,
    )
    db.commit()
    db.refresh(api_key)
    return api_key, secret


def _seed_deal(db, *, org_id: str, name: str) -> Deal:
    deal = Deal(
        organization_id=org_id,
        name=name,
        address="100 Main St",
        city="Austin",
        state="TX",
        property_type="Industrial",
        source="fixture",
    )
    db.add(deal)
    db.flush()
    signal = Signal(
        organization_id=org_id,
        deal_id=deal.id,
        signal_type="permit",
        source="fixture",
        description=f"{name} permit movement",
        severity=8.2,
    )
    db.add(signal)
    db.commit()
    db.refresh(deal)
    return deal


def _seed_graph_context(db, *, org_id: str, deal: Deal, developer_name: str) -> None:
    opportunity = GraphEntity(
        organization_id=org_id,
        entity_type=GraphEntityType.property,
        display_name=deal.name,
        normalized_name=deal.name.lower(),
        normalized_address=(deal.address or "").lower(),
        address=deal.address,
        city=deal.city,
        state=deal.state,
        confidence=1.0,
    )
    developer = GraphEntity(
        organization_id=org_id,
        entity_type=GraphEntityType.developer,
        display_name=developer_name,
        normalized_name=developer_name.lower(),
        confidence=0.91,
    )
    db.add_all([opportunity, developer])
    db.flush()
    db.add(GraphEntityLink(
        organization_id=org_id,
        entity_id=opportunity.id,
        record_type="deal",
        record_id=deal.id,
        source_system="fixture",
    ))
    relationship = GraphRelationship(
        organization_id=org_id,
        source_entity_id=opportunity.id,
        target_entity_id=developer.id,
        relationship_type=GraphRelationshipType.developed_by,
        confidence=0.86,
        source_system="fixture",
        source_id=f"developer:{deal.id}",
    )
    db.add(relationship)
    db.flush()
    db.add(GraphRelationshipEvidence(
        organization_id=org_id,
        relationship_id=relationship.id,
        source_system="county_permits",
        source_id=f"permit:{deal.id}",
        evidence_type="permit_record",
        excerpt=f"{developer_name} listed on permit",
        confidence=0.88,
    ))
    db.commit()


def test_public_api_key_reads_only_own_organization(client, db):
    first = _register(client, email="public-first@example.com", org_name="Public First")
    second = _register(client, email="public-second@example.com", org_name="Public Second")
    first_deal = _seed_deal(db, org_id=first["organization_id"], name="First org warehouse")
    _seed_deal(db, org_id=second["organization_id"], name="Second org warehouse")
    api_key, secret = _issue_key(
        db,
        org_id=first["organization_id"],
        user_id=first["user_id"],
        scopes=["read"],
    )

    listed = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [first_deal.id]

    detail = client.get(f"/public/deals/{first_deal.id}", headers={"X-API-Key": secret})
    assert detail.status_code == 200, detail.text
    assert detail.json()["name"] == "First org warehouse"

    signals = client.get("/public/signals", headers={"Authorization": f"Bearer {secret}"})
    assert signals.status_code == 200, signals.text
    assert len(signals.json()) == 1
    assert signals.json()[0]["deal_id"] == first_deal.id

    db.refresh(api_key)
    assert api_key.last_used_at is not None
    usage_events = (
        db.query(OrganizationApiKeyUsageEvent)
        .filter_by(api_key_id=api_key.id)
        .order_by(OrganizationApiKeyUsageEvent.created_at.asc())
        .all()
    )
    assert [(event.method, event.path, event.response_items) for event in usage_events] == [
        ("GET", "/public/deals", 1),
        ("GET", "/public/deals/{deal_id}", 1),
        ("GET", "/public/signals", 1),
    ]


def test_public_api_list_routes_include_pagination_headers(client, db):
    identity = _register(client, email="public-page@example.com", org_name="Public Page")
    for index in range(3):
        _seed_deal(db, org_id=identity["organization_id"], name=f"Paged warehouse {index}")
    _, secret = _issue_key(
        db,
        org_id=identity["organization_id"],
        user_id=identity["user_id"],
        scopes=["read"],
    )

    deals = client.get(
        "/public/deals?skip=1&limit=1",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert deals.status_code == 200, deals.text
    assert len(deals.json()) == 1
    assert deals.headers["X-Total-Count"] == "3"
    assert deals.headers["X-Page-Skip"] == "1"
    assert deals.headers["X-Page-Limit"] == "1"
    assert deals.headers["X-Next-Skip"] == "2"

    signals = client.get(
        "/public/signals?skip=2&limit=1",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert signals.status_code == 200, signals.text
    assert len(signals.json()) == 1
    assert signals.headers["X-Total-Count"] == "3"
    assert signals.headers["X-Next-Skip"] == ""


def test_public_api_returns_tenant_scoped_graph_context(client, db):
    first = _register(client, email="public-graph-first@example.com", org_name="Public Graph First")
    second = _register(client, email="public-graph-second@example.com", org_name="Public Graph Second")
    first_deal = _seed_deal(db, org_id=first["organization_id"], name="First graph warehouse")
    second_deal = _seed_deal(db, org_id=second["organization_id"], name="Second graph warehouse")
    _seed_graph_context(
        db,
        org_id=first["organization_id"],
        deal=first_deal,
        developer_name="Riverstone Development",
    )
    _seed_graph_context(
        db,
        org_id=second["organization_id"],
        deal=second_deal,
        developer_name="Other Org Developer",
    )
    _api_key, secret = _issue_key(
        db,
        org_id=first["organization_id"],
        user_id=first["user_id"],
        scopes=["read"],
    )

    response = client.get(
        f"/public/deals/{first_deal.id}/graph-context",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["opportunity_id"] == first_deal.id
    assert body["root_entities"][0]["display_name"] == "First graph warehouse"
    assert body["developers"][0]["entity"]["display_name"] == "Riverstone Development"
    assert body["developers"][0]["relationship"]["evidence"][0]["source_system"] == "county_permits"

    cross_org = client.get(
        f"/public/deals/{second_deal.id}/graph-context",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert cross_org.status_code == 404


def test_public_api_rejects_missing_revoked_or_under_scoped_keys(client, db):
    identity = _register(client, email="public-scope@example.com", org_name="Public Scope")
    api_key, secret = _issue_key(
        db,
        org_id=identity["organization_id"],
        user_id=identity["user_id"],
        scopes=["write"],
    )

    missing = client.get("/public/deals")
    assert missing.status_code == 401

    write_can_read = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
    assert write_can_read.status_code == 200

    api_key.scopes = "[]"
    db.commit()
    under_scoped = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
    assert under_scoped.status_code == 403

    api_key.scopes = '["read"]'
    revoke_api_key(db, api_key=api_key, actor_id=identity["user_id"])
    db.commit()
    revoked = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
    assert revoked.status_code == 401


def test_public_api_rejects_expired_api_keys(client, db):
    identity = _register(client, email="public-expired@example.com", org_name="Public Expired")
    api_key, secret = _issue_key(
        db,
        org_id=identity["organization_id"],
        user_id=identity["user_id"],
        scopes=["read"],
    )
    api_key.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    response = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
    assert response.status_code == 401


def test_public_api_key_rate_limit_headers_and_enforcement(client, db, monkeypatch):
    identity = _register(client, email="public-rate@example.com", org_name="Public Rate")
    _seed_deal(db, org_id=identity["organization_id"], name="Rate-limited warehouse")
    _, secret = _issue_key(
        db,
        org_id=identity["organization_id"],
        user_id=identity["user_id"],
        scopes=["read"],
    )
    monkeypatch.setattr(api_key_deps, "PUBLIC_API_KEY_LIMIT", 1)
    monkeypatch.setattr(api_key_deps, "PUBLIC_API_KEY_WINDOW", 60)

    first = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
    assert first.status_code == 200, first.text
    assert first.headers["X-API-Key-RateLimit-Limit"] == "1"
    assert first.headers["X-API-Key-RateLimit-Remaining"] == "0"

    limited = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
    assert limited.status_code == 429
    assert limited.headers["Retry-After"]


def test_admin_can_view_api_key_usage_summary(client, db):
    identity = _register(client, email="public-usage@example.com", org_name="Public Usage")
    _seed_deal(db, org_id=identity["organization_id"], name="Usage warehouse")
    api_key, secret = _issue_key(
        db,
        org_id=identity["organization_id"],
        user_id=identity["user_id"],
        scopes=["read"],
    )
    for _ in range(2):
        response = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
        assert response.status_code == 200

    headers = {"Authorization": f"Bearer {identity['access_token']}"}
    listed = client.get(f"/organizations/{identity['organization_id']}/api-keys", headers=headers)
    assert listed.status_code == 200, listed.text
    [listed_key] = listed.json()
    assert listed_key["usage_total_calls"] == 2
    assert listed_key["usage_last_called_at"]
    assert listed_key["rate_limit_limit"] > 0

    usage = client.get(
        f"/organizations/{identity['organization_id']}/api-keys/{api_key.id}/usage",
        headers=headers,
    )
    assert usage.status_code == 200, usage.text
    body = usage.json()
    assert body["total_calls"] == 2
    assert body["total_items"] == 2
    assert body["daily"][0]["total_calls"] == 2
    assert body["daily"][0]["total_items"] == 2
    assert body["daily"][0]["average_latency_ms"] >= 0
    assert body["endpoints"][0]["path"] == "/public/deals"

    rebuild = client.post(
        f"/organizations/{identity['organization_id']}/api-keys/{api_key.id}/usage/rebuild-rollups",
        headers=headers,
    )
    assert rebuild.status_code == 200, rebuild.text
    assert rebuild.json()["rebuilt_events"] == 2
