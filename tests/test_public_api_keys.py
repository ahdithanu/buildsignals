from __future__ import annotations

import pytest

from app.models.api_key import OrganizationApiKey
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
