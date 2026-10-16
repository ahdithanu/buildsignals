from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response

from app.routes import deal_intelligence, memos
from app.services.llm_client import is_openrouter_service_error
from app.services.memo_service import _deal_context
from app.services.rate_limiter import RateLimitDecision
from app.services.scoring_service import deterministic_score_payload
from eval import bench


@pytest.mark.parametrize("error_name", ["APITimeoutError", "APIConnectionError"])
def test_exhausted_transport_errors_have_safe_route_responses(monkeypatch, error_name):
    error = type(error_name, (Exception,), {})("private provider detail")
    assert is_openrouter_service_error(error)

    def fail(*args):
        raise error

    monkeypatch.setattr(deal_intelligence, "get_org_id", lambda: "org")
    monkeypatch.setattr(memos, "get_org_id", lambda: "org")
    monkeypatch.setattr(deal_intelligence.limiter, "check", lambda **kwargs: RateLimitDecision(True, 29, 0))
    monkeypatch.setattr(deal_intelligence, "_get_deal", lambda *args: object())
    monkeypatch.setattr(memos, "_ensure_deal_exists", lambda *args: None)
    monkeypatch.setattr(deal_intelligence, "score_deal", fail)
    monkeypatch.setattr(memos, "generate_memo", fail)
    monkeypatch.setattr(deal_intelligence, "score_deal_deterministic", lambda *args: {"score": 40})

    result = deal_intelligence.score("deal", Response(), db=None)
    assert result["scoring_method"] == "deterministic_fallback"
    assert result["fallback_reason"] == "OpenRouter request unavailable"
    with pytest.raises(HTTPException) as raised:
        memos.generate_deal_memo("deal", Response(), db=None)
    assert raised.value.status_code == 503
    assert raised.value.headers == {"Retry-After": "30"}
    assert "private provider detail" not in str(raised.value.detail)


@pytest.mark.parametrize("task", ["score", "enrich"])
@pytest.mark.parametrize("content", ["not JSON", "```json\nbroken\n```"])
def test_malformed_model_json_counts_as_check_failure(task, content):
    example = {"id": "bad-json", "task": task, "input": {}, "expected": {}}
    client = SimpleNamespace(chat_completion=lambda **kwargs: SimpleNamespace(
        content=content, served_model="fake", provider="fake", latency_ms=1, cost=0,
    ))
    row = bench._run_one(client, "fake", example, 1)
    assert row.status == "check_fail"
    assert not row.passed
    assert row.strict_parse is False
    assert bench._summary_row([row])[1:] == (1, 0, 0)


def test_benchmark_rejects_payload_that_production_validator_rejects():
    import json

    payload = deterministic_score_payload({})
    example = {"task": "score", "expected": {"score": 0, "risk_level": "high"}}
    assert bench._score(example, json.dumps(payload))
    del payload["breakdown"]["noi_positive"]
    assert not bench._score(example, json.dumps(payload))


def test_memo_context_includes_available_financial_and_relationship_data():
    deal = SimpleNamespace(
        name="Retail", address=None, city=None, state=None, zip_code=None,
        property_type="retail", units=None, sq_ft=None, year_built=None,
        asking_price=None, score=None, risk_level=None, signals=[],
        outputs=SimpleNamespace(noi=1, cap_rate=.05, dscr=1.2, irr=.15,
                                cash_on_cash=.09, equity_multiple=2.0),
        contacts=[SimpleNamespace(status=SimpleNamespace(value="new"))],
        activities=[SimpleNamespace(activity_type=SimpleNamespace(value="call"))],
    )
    context = _deal_context(deal)
    for expected in ("irr: 0.15", "cash_on_cash: 0.09", "equity_multiple: 2.0",
                     "contacts_count: 1", "'new': 1", "activities_count: 1", "'call': 1"):
        assert expected in context
