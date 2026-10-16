"""Score a deal 0-100 based on weighted factors and set its risk level."""

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app import config
from app.models.deal import Deal, RiskLevel
from app.services.llm_client import get_default_llm_client, is_openrouter_configured

log = logging.getLogger(__name__)

PRICE_TIERS = {
    "unit": ((20, 30_000, 500_000), (10, 15_000, 750_000)),
    "sqft": ((20, 50, 600), (10, 25, 1_000)),
}


def _price_tier_text() -> str:
    tiers = []
    for unit_tier, sqft_tier in zip(PRICE_TIERS["unit"], PRICE_TIERS["sqft"]):
        points, unit_low, unit_high = unit_tier
        _, sqft_low, sqft_high = sqft_tier
        tiers.append(
            f"{points} points when price per unit is ${unit_low:,}-${unit_high:,} "
            f"or price per square foot is ${sqft_low:,}-${sqft_high:,}"
        )
    return "; ".join(tiers) + "; otherwise 0. Use per-unit tiers when units > 0, otherwise per-square-foot tiers"


SCORE_FACTORS: dict[str, dict[str, object]] = {
    "has_asking_price": {
        "max": 10,
        "description": "10 points when asking_price is present and greater than 0",
    },
    "price_per_unit_or_sqft": {
        "max": 20,
        "description": _price_tier_text(),
    },
    "has_contacts": {
        "max": 10,
        "description": "10 points when at least one contact is present",
    },
    "has_assumptions": {
        "max": 10,
        "description": "10 points when assumptions are present",
    },
    "noi_positive": {
        "max": 15,
        "description": "15 points when NOI is present and greater than 0",
    },
    "dscr_above_1_2": {
        "max": 15,
        "description": "15 points when DSCR is present and at least 1.2",
    },
    "cap_rate_reasonable": {
        "max": 10,
        "description": "10 points when cap rate is present and between 4% and 12%",
    },
    "year_built_after_1970": {
        "max": 10,
        "description": "10 points when year_built is present and at least 1970",
    },
}


def score_rubric_text() -> str:
    return "; ".join(
        f"{name} {factor['max']} points: {factor['description']}"
        for name, factor in SCORE_FACTORS.items()
    )


def _risk_for_score(total: float) -> RiskLevel:
    if total >= 70:
        return RiskLevel.low
    if total >= 40:
        return RiskLevel.medium
    return RiskLevel.high


def _score_values(values: dict[str, Any]) -> tuple[float, RiskLevel, dict[str, dict]]:
    breakdown: dict[str, dict] = {}

    asking_price = values.get("asking_price")
    has_price = asking_price is not None and asking_price > 0
    breakdown["has_asking_price"] = {"max": 10, "earned": 10 if has_price else 0}

    price_metric_pts = 0
    if has_price:
        units = values.get("units")
        sq_ft = values.get("sq_ft")
        if units and units > 0:
            ppu = asking_price / units
            price_metric_pts = next((points for points, low, high in PRICE_TIERS["unit"] if low <= ppu <= high), 0)
        elif sq_ft and sq_ft > 0:
            ppsf = asking_price / sq_ft
            price_metric_pts = next((points for points, low, high in PRICE_TIERS["sqft"] if low <= ppsf <= high), 0)
    breakdown["price_per_unit_or_sqft"] = {"max": 20, "earned": price_metric_pts}

    contacts_count = values.get("contacts_count")
    if contacts_count is None:
        contacts = values.get("contacts")
        contacts_count = len(contacts) if contacts else 0
    breakdown["has_contacts"] = {"max": 10, "earned": 10 if contacts_count > 0 else 0}

    has_assumptions = values.get("has_assumptions")
    if has_assumptions is None:
        has_assumptions = values.get("assumptions") is not None
    breakdown["has_assumptions"] = {"max": 10, "earned": 10 if has_assumptions else 0}

    noi = values.get("noi")
    breakdown["noi_positive"] = {"max": 15, "earned": 15 if noi is not None and noi > 0 else 0}

    dscr = values.get("dscr")
    breakdown["dscr_above_1_2"] = {
        "max": 15,
        "earned": 15 if dscr is not None and dscr >= 1.2 else 0,
    }

    cap_rate = values.get("cap_rate")
    breakdown["cap_rate_reasonable"] = {
        "max": 10,
        "earned": 10 if cap_rate is not None and 0.04 <= cap_rate <= 0.12 else 0,
    }

    year_built = values.get("year_built")
    breakdown["year_built_after_1970"] = {
        "max": 10,
        "earned": 10 if year_built is not None and year_built >= 1970 else 0,
    }

    total = float(sum(v["earned"] for v in breakdown.values()))
    return total, _risk_for_score(total), breakdown


def deterministic_score_payload(values: dict[str, Any]) -> dict[str, Any]:
    total, risk, breakdown = _score_values(values)
    return {"score": total, "risk_level": risk.value, "breakdown": breakdown}


class DealScoreLLMOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    score: float = Field(ge=0, le=100)
    risk_level: Literal["low", "medium", "high"]
    breakdown: dict[str, dict]


class ScorePayloadValidationError(ValueError):
    pass


def validate_score_payload(payload: dict[str, Any]) -> None:
    breakdown = payload.get("breakdown")
    if not isinstance(breakdown, dict):
        raise ScorePayloadValidationError("breakdown must be an object")

    earned_total = 0.0
    for factor, meta in SCORE_FACTORS.items():
        row = breakdown.get(factor)
        if not isinstance(row, dict):
            raise ScorePayloadValidationError(f"missing factor: {factor}")
        max_points = row.get("max")
        earned = row.get("earned")
        if max_points != meta["max"]:
            raise ScorePayloadValidationError(f"{factor}.max must be {meta['max']}")
        if not isinstance(earned, (int, float)):
            raise ScorePayloadValidationError(f"{factor}.earned must be numeric")
        if earned < 0 or earned > max_points:
            raise ScorePayloadValidationError(f"{factor}.earned out of range")
        earned_total += earned

    score = payload.get("score")
    if not isinstance(score, (int, float)):
        raise ScorePayloadValidationError("score must be numeric")
    if score != earned_total:
        raise ScorePayloadValidationError("score must equal sum of earned factor points")

    expected_risk = _risk_for_score(float(score)).value
    if payload.get("risk_level") != expected_risk:
        raise ScorePayloadValidationError(
            f"risk_level must be {expected_risk} for score {score}"
        )


def _deterministic_score(deal: Deal) -> tuple[float, RiskLevel, dict[str, dict]]:
    outputs = deal.outputs
    return _score_values(
        {
            "asking_price": deal.asking_price,
            "units": deal.units,
            "sq_ft": deal.sq_ft,
            "contacts": deal.contacts,
            "assumptions": deal.assumptions,
            "noi": outputs.noi if outputs else None,
            "dscr": outputs.dscr if outputs else None,
            "cap_rate": outputs.cap_rate if outputs else None,
            "year_built": deal.year_built,
        }
    )


def evaluate_deal_score(deal: Deal) -> dict:
    """Compute the production rubric without mutating the deal or calling an LLM."""
    total, risk, breakdown = _deterministic_score(deal)
    return {"deal_id": deal.id, "score": total, "risk_level": risk.value, "breakdown": breakdown}


def _deal_context(deal: Deal) -> str:
    outputs = deal.outputs
    return "\n".join(
        [
            f"name: {deal.name}",
            f"address: {deal.address or 'unknown'}",
            f"city: {deal.city or 'unknown'}",
            f"state: {deal.state or 'unknown'}",
            f"property_type: {deal.property_type or 'unknown'}",
            f"units: {deal.units if deal.units is not None else 'unknown'}",
            f"sq_ft: {deal.sq_ft if deal.sq_ft is not None else 'unknown'}",
            f"year_built: {deal.year_built if deal.year_built is not None else 'unknown'}",
            f"asking_price: {deal.asking_price if deal.asking_price is not None else 'unknown'}",
            f"contacts_count: {len(deal.contacts) if deal.contacts else 0}",
            f"has_assumptions: {deal.assumptions is not None}",
            f"noi: {outputs.noi if outputs and outputs.noi is not None else 'unknown'}",
            f"dscr: {outputs.dscr if outputs and outputs.dscr is not None else 'unknown'}",
            f"cap_rate: {outputs.cap_rate if outputs and outputs.cap_rate is not None else 'unknown'}",
        ]
    )


def _llm_score(
    deal: Deal,
) -> tuple[float, RiskLevel, dict[str, dict], str, str | None]:
    if config.SCORING_MODE == "deterministic" or not is_openrouter_configured():
        total, risk, breakdown = _deterministic_score(deal)
        return total, risk, breakdown, "deterministic", None

    result = get_default_llm_client().chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "You score commercial real-estate deals for BuildSignals. Return only JSON "
                    "with keys score, risk_level, and breakdown. Score must be 0-100. risk_level "
                    "must be low for score >= 70, medium for score >= 40 and < 70, otherwise high. "
                    f"Use this rubric exactly: {score_rubric_text()}. "
                    "For each breakdown item return max and earned."
                ),
            },
            {
                "role": "user",
                "content": f"Score this deal:\n{_deal_context(deal)}",
            },
        ],
        temperature=0,
        max_tokens=900,
        response_format={"type": "json_object"},
    )
    try:
        parsed = DealScoreLLMOutput.model_validate_json(result.content)
        payload = parsed.model_dump()
        validate_score_payload(payload)
    except (ScorePayloadValidationError, ValidationError) as exc:
        reason = str(exc)
        log.warning(
            "llm_score_validation_failed",
            extra={"reason": reason, "deal_id": getattr(deal, "id", None)},
        )
        total, risk, breakdown = _deterministic_score(deal)
        return total, risk, breakdown, "deterministic_fallback", reason
    return parsed.score, RiskLevel(parsed.risk_level), parsed.breakdown, "llm", None


def score_deal(db: Session, deal: Deal) -> dict:
    """Evaluate *deal* against scoring criteria and persist the result.

    Returns a dict with the total score, risk_level, and per-factor breakdown.
    """

    total, risk, breakdown, scoring_method, fallback_reason = _llm_score(deal)

    # Persist
    deal.score = total
    deal.risk_level = risk
    db.add(deal)
    db.commit()
    db.refresh(deal)

    payload = {
        "deal_id": deal.id,
        "score": total,
        "risk_level": risk.value,
        "breakdown": breakdown,
        "scoring_method": scoring_method,
    }
    if fallback_reason:
        payload["fallback_reason"] = fallback_reason
    return payload


def score_deal_deterministic(db: Session, deal: Deal) -> dict:
    """Persist and return the deterministic score, bypassing any LLM call."""
    total, risk, breakdown = _deterministic_score(deal)

    deal.score = total
    deal.risk_level = risk
    db.add(deal)
    db.commit()
    db.refresh(deal)

    return {
        "deal_id": deal.id,
        "score": total,
        "risk_level": risk.value,
        "breakdown": breakdown,
        "scoring_method": "deterministic",
    }
