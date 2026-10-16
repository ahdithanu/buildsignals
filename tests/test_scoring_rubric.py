from __future__ import annotations

import json

import pytest

from app.models.deal import RiskLevel
from app.services import scoring_service
from app.services.scoring_service import (
    SCORE_FACTORS,
    ScorePayloadValidationError,
    deterministic_score_payload,
    score_rubric_text,
    validate_score_payload,
)
from eval.bench import _prompt


def test_score_rubric_text_lists_every_factor_and_threshold():
    rubric = score_rubric_text()

    for name, factor in SCORE_FACTORS.items():
        assert name in rubric
        assert f"{factor['max']} points" in rubric

    for expected in (
        "$30,000-$500,000",
        "$15,000-$750,000",
        "$50-$600",
        "$25-$1,000",
        "at least 1.2",
        "between 4% and 12%",
        "at least 1970",
    ):
        assert expected in rubric


def test_score_benchmark_prompt_uses_shared_rubric_text():
    system, _ = _prompt({"task": "score", "input": {}})

    assert score_rubric_text() in system


def test_deterministic_score_payload_matches_mixed_use_tier():
    payload = deterministic_score_payload(
        {
            "asking_price": 95_000_000,
            "units": 150,
            "sq_ft": 185_000,
            "contacts_count": 1,
            "has_assumptions": True,
            "year_built": 2022,
        }
    )

    assert payload["score"] == 50
    assert payload["risk_level"] == "medium"
    assert payload["breakdown"]["price_per_unit_or_sqft"]["earned"] == 10


def test_scoring_mode_defaults_to_deterministic(monkeypatch):
    class DummyDeal:
        asking_price = 95_000_000
        units = 150
        sq_ft = 185_000
        contacts = [object()]
        assumptions = object()
        outputs = None
        year_built = 2022

    monkeypatch.setattr(scoring_service.config, "SCORING_MODE", "deterministic")
    monkeypatch.setattr(scoring_service, "is_openrouter_configured", lambda: True)

    score, risk, breakdown, method, reason = scoring_service._llm_score(DummyDeal())  # noqa: SLF001

    assert score == 50
    assert risk is RiskLevel.medium
    assert breakdown["price_per_unit_or_sqft"]["earned"] == 10
    assert method == "deterministic"
    assert reason is None


def _valid_payload():
    payload = deterministic_score_payload(
        {
            "asking_price": 42_000_000,
            "units": 240,
            "contacts_count": 2,
            "has_assumptions": True,
            "year_built": 2015,
        }
    )
    validate_score_payload(payload)
    return payload


def test_validate_score_payload_requires_every_factor():
    payload = _valid_payload()
    del payload["breakdown"]["noi_positive"]

    with pytest.raises(ScorePayloadValidationError, match="missing factor"):
        validate_score_payload(payload)


def test_validate_score_payload_rejects_earned_above_max():
    payload = _valid_payload()
    payload["breakdown"]["has_asking_price"]["earned"] = 11

    with pytest.raises(ScorePayloadValidationError, match="out of range"):
        validate_score_payload(payload)


def test_validate_score_payload_rejects_total_that_does_not_equal_earned_sum():
    payload = _valid_payload()
    payload["score"] = 99

    with pytest.raises(ScorePayloadValidationError, match="sum of earned"):
        validate_score_payload(payload)


def test_validate_score_payload_rejects_risk_level_mismatch():
    payload = _valid_payload()
    payload["risk_level"] = "low"

    with pytest.raises(ScorePayloadValidationError, match="risk_level"):
        validate_score_payload(payload)


@pytest.mark.parametrize("invalid_output", [None, "not JSON", '{"score": 900}'])
def test_llm_score_falls_back_to_deterministic_when_llama_style_total_is_wrong(monkeypatch, invalid_output):
    class DummyDeal:
        id = "deal-1"
        name = "Parkview"
        address = "1200 Parkview Blvd"
        city = "Austin"
        state = "TX"
        property_type = "multifamily"
        asking_price = 42_000_000
        units = 240
        sq_ft = 196_000
        contacts = [object()]
        assumptions = object()
        outputs = None
        year_built = 2015

    payload = _valid_payload()
    payload["score"] = 55

    class FakeClient:
        def chat_completion(self, **_kwargs):
            return type("Result", (), {"content": invalid_output or json.dumps(payload)})()

    monkeypatch.setattr(scoring_service.config, "SCORING_MODE", "llm")
    monkeypatch.setattr(scoring_service, "is_openrouter_configured", lambda: True)
    monkeypatch.setattr(scoring_service, "get_default_llm_client", lambda: FakeClient())

    score, risk, breakdown, method, reason = scoring_service._llm_score(DummyDeal())  # noqa: SLF001

    assert score == 60
    assert risk is RiskLevel.medium
    assert breakdown["price_per_unit_or_sqft"]["earned"] == 20
    assert method == "deterministic_fallback"
    assert reason
    if invalid_output is None:
        assert reason == "score must equal sum of earned factor points"


def test_pure_score_api_remains_available_to_current_evaluation_workflows(monkeypatch):
    from types import SimpleNamespace

    deal = SimpleNamespace(
        id="eval-deal", asking_price=1_000_000, units=10, sq_ft=None,
        contacts=[], assumptions=None, outputs=None, year_built=2000,
    )
    monkeypatch.setattr(scoring_service.config, "SCORING_MODE", "llm")
    monkeypatch.setattr(scoring_service, "get_default_llm_client", lambda: pytest.fail("must remain offline"))
    assert scoring_service.evaluate_deal_score(deal) == {
        "deal_id": "eval-deal", "score": 40, "risk_level": "medium",
        "breakdown": deterministic_score_payload(vars(deal))["breakdown"],
    }
    assert not hasattr(deal, "score")


def test_memo_context_keeps_property_fields_without_signals():
    from types import SimpleNamespace

    from app.services.memo_service import _deal_context

    deal = SimpleNamespace(
        name="Evidence property", address="123 Main", city="Columbus", state="OH",
        zip_code="43215", property_type="retail", units=None, sq_ft=10000,
        year_built=2000, asking_price=1_000_000, score=None, risk_level=None,
        outputs=None, signals=[],
    )
    context = _deal_context(deal)
    assert "name: Evidence property" in context
    assert "asking_price: 1000000" in context
    assert "signals: none recorded" in context
