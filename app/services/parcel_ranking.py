from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from app.models.parcel import ParcelFact, ParcelRecord


RANKER_VERSION = "developer-v1"
RANKER_VERSIONS = {
    "developer": RANKER_VERSION,
    "broker": "broker-v2",
    "realtor": "realtor-v2",
}
FAVORABLE_ZONING_TERMS = (
    "commercial", "mixed", "industrial", "retail", "business", "downtown",
)


@dataclass(frozen=True)
class RankedParcel:
    score: float
    confidence: float
    explanation: dict[str, Any]


def rank_developer_candidate(
    parcel: ParcelRecord,
    facts: Iterable[ParcelFact],
    *,
    distance_miles: float,
    radius_miles: float,
) -> RankedParcel:
    current_facts = [fact for fact in facts if fact.is_current]
    fact_ids = [fact.id for fact in current_facts]
    raw_ids = sorted({fact.raw_source_record_id for fact in current_facts})
    features: list[dict[str, Any]] = []
    reasons: list[str] = []
    cautions: list[str] = []

    proximity = max(0.0, 1 - distance_miles / radius_miles) * 40
    features.append({"name": "proximity", "weight": 40, "score": round(proximity, 2)})
    reasons.append(f"{distance_miles:.2f} miles from the confirmed signal")

    available_weight = 40.0
    improvement_score = 0.0
    if parcel.land_value is not None and parcel.improvement_value is not None:
        denominator = max(float(parcel.land_value), 1.0)
        ratio = float(parcel.improvement_value) / denominator
        improvement_score = max(0.0, 1 - min(ratio, 2.0) / 2.0) * 25
        available_weight += 25
        if improvement_score >= 12.5:
            reasons.append("Low improvement value relative to land value")
    else:
        cautions.append("Improvement-to-land value ratio is unavailable")
    features.append({
        "name": "improvement_to_land", "weight": 25,
        "score": round(improvement_score, 2),
    })

    area_score = 0.0
    if parcel.land_area_sq_ft is not None:
        area_score = min(float(parcel.land_area_sq_ft) / 100_000, 1.0) * 20
        available_weight += 20
        if area_score >= 10:
            reasons.append(f"{parcel.land_area_sq_ft:,.0f} square feet of land")
    else:
        cautions.append("Parcel area is unavailable")
    features.append({"name": "land_area", "weight": 20, "score": round(area_score, 2)})

    zoning_text = " ".join(filter(None, (parcel.zoning_code, parcel.land_use))).casefold()
    zoning_score = 0.0
    if zoning_text:
        available_weight += 15
        if any(term in zoning_text for term in FAVORABLE_ZONING_TERMS):
            zoning_score = 15
            reasons.append("Published zoning or land use supports commercial development review")
        else:
            cautions.append("Published zoning needs use-specific entitlement review")
    else:
        cautions.append("Zoning and land use are unavailable")
    features.append({"name": "zoning_context", "weight": 15, "score": zoning_score})

    score = round(proximity + improvement_score + area_score + zoning_score, 2)
    confidence = round(available_weight / 100, 2)
    return RankedParcel(
        score=score,
        confidence=confidence,
        explanation={
            "ranker_version": RANKER_VERSION,
            "features": features,
            "reasons": reasons,
            "cautions": cautions,
            "parcel_fact_ids": fact_ids,
            "raw_source_record_ids": raw_ids,
        },
    )


def rank_parcel_candidate(
    parcel: ParcelRecord,
    facts: Iterable[ParcelFact],
    *,
    persona: str,
    distance_miles: float,
    radius_miles: float,
) -> RankedParcel:
    if persona == "developer":
        return rank_developer_candidate(
            parcel, facts, distance_miles=distance_miles, radius_miles=radius_miles
        )
    if persona not in {"broker", "realtor"}:
        raise ValueError(f"Unknown parcel ranking persona: {persona}")
    return _rank_market_candidate(
        parcel,
        facts,
        persona=persona,
        distance_miles=distance_miles,
        radius_miles=radius_miles,
    )


def ranker_version(persona: str) -> str:
    try:
        return RANKER_VERSIONS[persona]
    except KeyError as exc:
        raise ValueError(f"Unknown parcel ranking persona: {persona}") from exc


def _rank_market_candidate(
    parcel: ParcelRecord,
    facts: Iterable[ParcelFact],
    *,
    persona: str,
    distance_miles: float,
    radius_miles: float,
) -> RankedParcel:
    current_facts = [fact for fact in facts if fact.is_current]
    ownership = [fact for fact in current_facts if fact.fact_type == "ownership"]
    fact_ids = [fact.id for fact in current_facts]
    raw_ids = sorted({fact.raw_source_record_id for fact in current_facts})
    weights = (
        {
            "proximity": 30, "ownership": 20, "tenure": 15,
            "valuation": 15, "zoning": 10, "area": 10,
        }
        if persona == "broker"
        else {
            "proximity": 30, "ownership": 20, "tenure": 10,
            "valuation": 15, "zoning": 15, "area": 10,
        }
    )
    features: list[dict[str, Any]] = []
    reasons = [f"{distance_miles:.2f} miles from the confirmed signal"]
    cautions = ["No owner willingness to sell or listing intent is inferred"]
    available_weight = float(weights["proximity"])

    proximity = max(0.0, 1 - distance_miles / radius_miles) * weights["proximity"]
    features.append({"name": "proximity", "weight": weights["proximity"], "score": round(proximity, 2)})

    ownership_score = float(weights["ownership"] if ownership else 0)
    if ownership:
        available_weight += weights["ownership"]
        reasons.append("Current ownership evidence is available for outreach research")
    else:
        cautions.append("Current ownership evidence is unavailable")
    features.append({"name": "ownership_evidence", "weight": weights["ownership"], "score": ownership_score})

    sale_date = _latest_sale_date(current_facts)
    tenure_score = 0.0
    if sale_date is not None:
        available_weight += weights["tenure"]
        as_of = parcel.last_verified_at
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        years_held = max(0.0, (as_of - sale_date).days / 365.25)
        tenure_score = min(years_held / 10, 1.0) * weights["tenure"]
        if years_held >= 5:
            reasons.append(f"Published sale evidence indicates about {years_held:.0f} years of tenure")
        else:
            cautions.append("Published sale evidence indicates relatively recent ownership")
    else:
        cautions.append("Ownership tenure is unavailable")
    features.append({
        "name": "ownership_tenure", "weight": weights["tenure"],
        "score": round(tenure_score, 2),
    })

    value_fields = (parcel.land_value, parcel.improvement_value, parcel.total_assessed_value)
    value_completeness = sum(value is not None for value in value_fields) / len(value_fields)
    valuation_score = value_completeness * weights["valuation"]
    if value_completeness:
        available_weight += weights["valuation"]
        reasons.append("Published valuation context supports initial pricing research")
    else:
        cautions.append("Assessed valuation context is unavailable")
    features.append({"name": "valuation_context", "weight": weights["valuation"], "score": round(valuation_score, 2)})

    zoning_text = " ".join(filter(None, (parcel.zoning_code, parcel.land_use))).casefold()
    zoning_score = 0.0
    if zoning_text:
        available_weight += weights["zoning"]
        if any(term in zoning_text for term in FAVORABLE_ZONING_TERMS):
            zoning_score = float(weights["zoning"])
            reasons.append("Published zoning or land use supports commercial-use research")
        else:
            cautions.append("Published zoning needs use-specific review")
    else:
        cautions.append("Zoning and land use are unavailable")
    features.append({"name": "zoning_context", "weight": weights["zoning"], "score": zoning_score})

    area_score = 0.0
    if parcel.land_area_sq_ft is not None:
        available_weight += weights["area"]
        area_score = min(float(parcel.land_area_sq_ft) / 100_000, 1.0) * weights["area"]
        reasons.append("Published parcel area supports buyer-fit screening")
    else:
        cautions.append("Parcel area is unavailable")
    features.append({"name": "land_area", "weight": weights["area"], "score": round(area_score, 2)})

    return RankedParcel(
        score=round(
            proximity + ownership_score + tenure_score + valuation_score + zoning_score + area_score,
            2,
        ),
        confidence=round(available_weight / 100, 2),
        explanation={
            "ranker_version": RANKER_VERSIONS[persona],
            "features": features,
            "reasons": reasons,
            "cautions": cautions,
            "parcel_fact_ids": fact_ids,
            "raw_source_record_ids": raw_ids,
        },
    )


def _latest_sale_date(facts: Iterable[ParcelFact]) -> datetime | None:
    for fact in facts:
        if fact.fact_type != "last_sale" or not isinstance(fact.value, dict):
            continue
        value = fact.value.get("last_sale_date")
        if value is None:
            continue
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    return None
