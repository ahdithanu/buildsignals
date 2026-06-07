"""Per-org rate limits on LLM-backed endpoints.

The three expensive routes (/generate-memo, /enrich, /score) each call
out to a paid LLM provider in production. A misbehaving client could
burn through the budget in minutes, so we cap each org at AI_LIMIT calls
per AI_WINDOW seconds. These tests pin that contract.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.deal import Deal
from app.services import enrichment_service, memo_service, scoring_service
from app.services.rate_limiter import AI_LIMIT, limiter
import app.routes.deal_intelligence as deal_intel_routes
import app.routes.memos as memo_routes

STRONG_PW = "CorrectHorseBattery42"


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Per-org buckets are process-global; reset around every test so
    /auth/register hits from a previous test don't bleed in."""
    limiter.clear()
    yield
    limiter.clear()


@pytest.fixture(autouse=True)
def _stub_llm_services(monkeypatch):
    """The routes call into paid LLM providers in prod. Stub the three
    service entry points so the rate-limit check is the only interesting
    behavior under test."""

    def _fake_enrich(db, deal):
        return deal

    def _fake_score(db, deal):
        return {
            "deal_id": deal.id,
            "score": 0.0,
            "risk_level": "low",
            "breakdown": {},
        }

    def _fake_generate_memo(db, deal_id):
        from app.models.memo import Memo
        from datetime import datetime, timezone

        # Reuse an existing memo if the route is called again for the
        # same deal — the route is idempotent by design.
        existing = db.query(Memo).filter(Memo.deal_id == deal_id).first()
        if existing is not None:
            return existing
        deal = db.query(Deal).filter(Deal.id == deal_id).first()
        now = datetime.now(timezone.utc)
        memo = Memo(
            id=str(uuid4()),
            deal_id=deal_id,
            organization_id=deal.organization_id,
            title="stub",
            content="stub",
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(memo)
        db.commit()
        db.refresh(memo)
        return memo

    # Patch at the import sites the routes use.
    monkeypatch.setattr(deal_intel_routes, "enrich_deal", _fake_enrich)
    monkeypatch.setattr(deal_intel_routes, "score_deal", _fake_score)
    monkeypatch.setattr(memo_routes, "generate_memo", _fake_generate_memo)
    # Also patch the originals in case anything else imports them.
    monkeypatch.setattr(enrichment_service, "enrich_deal", _fake_enrich)
    monkeypatch.setattr(scoring_service, "score_deal", _fake_score)
    monkeypatch.setattr(memo_service, "generate_memo", _fake_generate_memo)


def _register(client, email="alice@example.com", org_name="Acme"):
    r = client.post("/auth/register", json={
        "email": email, "password": STRONG_PW,
        "full_name": email.split("@")[0].title(),
        "organization_name": org_name,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_deal(db, org_id, name="Deal A") -> Deal:
    d = Deal(id=str(uuid4()), name=name, organization_id=org_id)
    db.add(d); db.commit(); db.refresh(d)
    return d


class TestAIRateLimits:
    def test_score_allows_up_to_the_limit_then_429s(self, client, db):
        reg = _register(client)
        deal = _seed_deal(db, reg["organization_id"])
        headers = _auth(reg["access_token"])

        for i in range(AI_LIMIT):
            r = client.post(f"/deals/{deal.id}/score", headers=headers)
            assert r.status_code == 200, f"hit {i} unexpectedly failed: {r.status_code} {r.text}"

        r = client.post(f"/deals/{deal.id}/score", headers=headers)
        assert r.status_code == 429
        assert "Retry-After" in r.headers
        # Header value should be a positive int (seconds).
        assert int(r.headers["Retry-After"]) >= 1

    def test_enrich_429s_after_limit(self, client, db):
        reg = _register(client)
        deal = _seed_deal(db, reg["organization_id"])
        headers = _auth(reg["access_token"])

        for _ in range(AI_LIMIT):
            r = client.post(f"/deals/{deal.id}/enrich", headers=headers)
            assert r.status_code == 200, r.text

        r = client.post(f"/deals/{deal.id}/enrich", headers=headers)
        assert r.status_code == 429
        assert "Retry-After" in r.headers

    def test_generate_memo_429s_after_limit(self, client, db):
        reg = _register(client)
        deal = _seed_deal(db, reg["organization_id"])
        headers = _auth(reg["access_token"])

        for _ in range(AI_LIMIT):
            r = client.post(f"/deals/{deal.id}/generate-memo", headers=headers)
            assert r.status_code == 201, r.text

        r = client.post(f"/deals/{deal.id}/generate-memo", headers=headers)
        assert r.status_code == 429
        assert "Retry-After" in r.headers

    def test_bucket_is_per_org_not_global(self, client, db):
        """An org that's burned its budget must not block a separate org."""
        org_a = _register(client, email="a@example.com", org_name="OrgA")
        deal_a = _seed_deal(db, org_a["organization_id"], name="A")
        headers_a = _auth(org_a["access_token"])

        # Burn org A's budget completely.
        for _ in range(AI_LIMIT):
            r = client.post(f"/deals/{deal_a.id}/score", headers=headers_a)
            assert r.status_code == 200
        r = client.post(f"/deals/{deal_a.id}/score", headers=headers_a)
        assert r.status_code == 429

        # Org B's first call should still succeed — separate bucket.
        org_b = _register(client, email="b@example.com", org_name="OrgB")
        deal_b = _seed_deal(db, org_b["organization_id"], name="B")
        headers_b = _auth(org_b["access_token"])
        r = client.post(f"/deals/{deal_b.id}/score", headers=headers_b)
        assert r.status_code == 200, r.text
