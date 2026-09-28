from __future__ import annotations

import pytest

import app.utils.api_key_deps as api_key_deps
from app.models.api_key import OrganizationApiKey
from app.models.api_usage import OrganizationApiKeyUsageEvent
from app.models.deal import Deal
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
    assert body["endpoints"][0]["path"] == "/public/deals"
