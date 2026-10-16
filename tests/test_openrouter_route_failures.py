from __future__ import annotations

import pytest
from fastapi import HTTPException, Response

from app.routes import deal_intelligence, memos


class ProviderError(Exception):
    def __init__(self, status_code: int, headers: dict[str, str] | None = None):
        super().__init__(f"provider failed with {status_code}")
        self.status_code = status_code
        self.headers = headers or {}


class DummyDB:
    def add(self, _value):
        pass

    def commit(self):
        pass

    def refresh(self, _value):
        pass


class DummyDeal:
    id = "deal_1"
    asking_price = 1_000_000
    units = 10
    sq_ft = None
    contacts = [{"email": "a@example.com"}]
    assumptions = {"rent": 1}
    outputs = None
    year_built = 2000


def test_score_route_falls_back_to_deterministic_on_openrouter_429(monkeypatch):
    monkeypatch.setattr(deal_intelligence, "get_org_id", lambda: "org_1")
    monkeypatch.setattr(deal_intelligence, "_get_deal", lambda _deal_id, _db: DummyDeal())
    monkeypatch.setattr(
        deal_intelligence.limiter,
        "check",
        lambda **_kwargs: type("Decision", (), {"allowed": True, "remaining": 29, "retry_after": 0, "reset_after": 60})(),
    )

    def fail_score(_db, _deal):
        raise ProviderError(429)

    monkeypatch.setattr(deal_intelligence, "score_deal", fail_score)
    monkeypatch.setattr(
        deal_intelligence,
        "score_deal_deterministic",
        lambda _db, deal: {
            "deal_id": deal.id,
            "score": 70,
            "risk_level": "low",
            "breakdown": {},
            "scoring_method": "deterministic",
        },
    )

    result = deal_intelligence.score("deal_1", Response(), db=DummyDB())

    assert result == {
        "deal_id": "deal_1",
        "score": 70,
        "risk_level": "low",
        "breakdown": {},
        "scoring_method": "deterministic_fallback",
        "fallback_reason": "OpenRouter returned HTTP 429",
    }


def test_score_route_returns_deterministic_method(monkeypatch):
    monkeypatch.setattr(deal_intelligence, "get_org_id", lambda: "org_1")
    monkeypatch.setattr(deal_intelligence, "_get_deal", lambda _deal_id, _db: DummyDeal())
    monkeypatch.setattr(
        deal_intelligence.limiter,
        "check",
        lambda **_kwargs: type("Decision", (), {"allowed": True, "remaining": 29, "retry_after": 0, "reset_after": 60})(),
    )
    monkeypatch.setattr(
        deal_intelligence,
        "score_deal",
        lambda _db, deal: {
            "deal_id": deal.id,
            "score": 70,
            "risk_level": "low",
            "breakdown": {},
            "scoring_method": "deterministic",
        },
    )

    result = deal_intelligence.score("deal_1", Response(), db=DummyDB())

    assert result["scoring_method"] == "deterministic"
    assert "fallback_reason" not in result


def test_score_route_returns_llm_method(monkeypatch):
    monkeypatch.setattr(deal_intelligence, "get_org_id", lambda: "org_1")
    monkeypatch.setattr(deal_intelligence, "_get_deal", lambda _deal_id, _db: DummyDeal())
    monkeypatch.setattr(
        deal_intelligence.limiter,
        "check",
        lambda **_kwargs: type("Decision", (), {"allowed": True, "remaining": 29, "retry_after": 0, "reset_after": 60})(),
    )
    monkeypatch.setattr(
        deal_intelligence,
        "score_deal",
        lambda _db, deal: {
            "deal_id": deal.id,
            "score": 80,
            "risk_level": "low",
            "breakdown": {},
            "scoring_method": "llm",
        },
    )

    result = deal_intelligence.score("deal_1", Response(), db=DummyDB())

    assert result["scoring_method"] == "llm"
    assert "fallback_reason" not in result


def test_score_route_reraises_non_provider_errors(monkeypatch):
    monkeypatch.setattr(deal_intelligence, "get_org_id", lambda: "org_1")
    monkeypatch.setattr(deal_intelligence, "_get_deal", lambda _deal_id, _db: DummyDeal())
    monkeypatch.setattr(
        deal_intelligence.limiter,
        "check",
        lambda **_kwargs: type("Decision", (), {"allowed": True, "remaining": 29, "retry_after": 0, "reset_after": 60})(),
    )

    def fail_score(_db, _deal):
        raise RuntimeError("database write failed")

    monkeypatch.setattr(deal_intelligence, "score_deal", fail_score)

    with pytest.raises(RuntimeError, match="database write failed"):
        deal_intelligence.score("deal_1", Response(), db=DummyDB())


def test_generate_memo_route_returns_clean_503_on_openrouter_5xx(monkeypatch):
    monkeypatch.setattr(memos, "get_org_id", lambda: "org_1")
    monkeypatch.setattr(memos, "_ensure_deal_exists", lambda _db, _deal_id: DummyDeal())
    monkeypatch.setattr(
        memos.limiter,
        "check",
        lambda **_kwargs: type("Decision", (), {"allowed": True, "remaining": 29, "retry_after": 0, "reset_after": 60})(),
    )

    def fail_memo(_db, _deal_id):
        raise ProviderError(500, headers={"Retry-After": "17"})

    monkeypatch.setattr(memos, "generate_memo", fail_memo)

    with pytest.raises(HTTPException) as exc_info:
        memos.generate_deal_memo("deal_1", Response(), db=DummyDB())

    exc = exc_info.value
    assert exc.status_code == 503
    assert exc.headers == {"Retry-After": "17"}
    assert exc.detail == {
        "error": "memo_generation_unavailable",
        "message": "Memo generation is temporarily unavailable. Try again shortly.",
    }
