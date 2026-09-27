"""Evidence-backed parcel availability semantics."""
from __future__ import annotations

from typing import Any

from app.models.parcel import ParcelFact

AVAILABILITY_FACT_TYPES = {
    "availability",
    "listing",
    "broker_listing",
    "owner_availability",
    "sale_availability",
}

VERIFIED_AVAILABILITY_STATUSES = {
    "available",
    "for_sale",
    "listed",
    "broker_listed",
    "owner_indicated_available",
}


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


def verified_availability_fact(facts: list[ParcelFact]) -> ParcelFact | None:
    """Return the strongest current fact proving sale availability, if any."""
    for fact in facts:
        if not fact.is_current or fact.fact_type not in AVAILABILITY_FACT_TYPES:
            continue
        value = fact.value if isinstance(fact.value, dict) else {}
        status = _text(value.get("status") or value.get("availability_status"))
        evidence_type = _text(value.get("evidence_type") or value.get("source_type"))
        has_availability_status = status in VERIFIED_AVAILABILITY_STATUSES
        has_source = bool(fact.source_url or fact.excerpt)
        has_explicit_source_type = evidence_type in {"listing", "broker", "owner", "auction"}
        if has_availability_status and has_source and fact.confidence >= 0.7 and has_explicit_source_type:
            return fact
    return None


def availability_label(facts: list[ParcelFact]) -> str:
    return "verified_for_sale" if verified_availability_fact(facts) else "nearby_candidate_not_verified_for_sale"
