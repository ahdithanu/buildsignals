"""Evidence-backed parcel availability semantics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import and_, func, or_

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
AVAILABILITY_MAX_AGE = timedelta(days=30)
OBSERVED_AT_SOURCE_KEY = "observed_at_source"
AvailabilityState = Literal[
    "nearby_candidate",
    "verified_current",
    "verified_stale",
    "verified_unaged",
]


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_qualifying_fact(fact: ParcelFact) -> bool:
    if not fact.is_current or fact.fact_type not in AVAILABILITY_FACT_TYPES:
        return False
    value = fact.value if isinstance(fact.value, dict) else {}
    status = _text(value.get("status") or value.get("availability_status"))
    evidence_type = _text(value.get("evidence_type") or value.get("source_type"))
    return (
        status in VERIFIED_AVAILABILITY_STATUSES
        and bool(fact.source_url or fact.excerpt)
        and fact.confidence >= 0.7
        and evidence_type in {"listing", "broker", "owner", "auction"}
    )


def availability_state(
    fact: ParcelFact,
    *,
    now: datetime | None = None,
    max_age: timedelta = AVAILABILITY_MAX_AGE,
) -> AvailabilityState | None:
    """Classify qualifying evidence without treating capture time as source time."""
    if not _is_qualifying_fact(fact):
        return None
    value = fact.value if isinstance(fact.value, dict) else {}
    if _text(value.get(OBSERVED_AT_SOURCE_KEY)) != "source":
        return "verified_unaged"
    current_time = _as_utc(now or datetime.now(timezone.utc))
    observed_at = _as_utc(fact.observed_at)
    if observed_at > current_time or current_time - observed_at > max_age:
        return "verified_stale"
    return "verified_current"


def resolve_availability(
    facts: list[ParcelFact],
    *,
    now: datetime | None = None,
) -> tuple[ParcelFact | None, AvailabilityState]:
    """Return the best current availability fact and its freshness state."""
    candidates = [fact for fact in facts if _is_qualifying_fact(fact)]
    if not candidates:
        return None, "nearby_candidate"
    candidates.sort(key=lambda fact: _as_utc(fact.observed_at), reverse=True)
    fact = candidates[0]
    return fact, availability_state(fact, now=now) or "nearby_candidate"


def verified_availability_fact(
    facts: list[ParcelFact],
    *,
    now: datetime | None = None,
) -> ParcelFact | None:
    """Return only source-observed availability evidence that is current."""
    fact, state = resolve_availability(facts, now=now)
    return fact if state == "verified_current" else None


def availability_recheck_at(
    fact: ParcelFact | None,
    *,
    state: AvailabilityState,
    max_age: timedelta = AVAILABILITY_MAX_AGE,
) -> datetime | None:
    if fact is None or state not in {"verified_current", "verified_stale"}:
        return None
    value = fact.value if isinstance(fact.value, dict) else {}
    if _text(value.get(OBSERVED_AT_SOURCE_KEY)) != "source":
        return None
    return _as_utc(fact.observed_at) + max_age


def current_availability_conditions(
    parcel_id_column,
    organization_id_column,
    *,
    now: datetime | None = None,
):
    """SQL predicate matching the same freshness policy as ``resolve_availability``."""
    current_time = _as_utc(now or datetime.now(timezone.utc))
    status = func.lower(func.coalesce(
        ParcelFact.value["status"].as_string(),
        ParcelFact.value["availability_status"].as_string(),
        "",
    ))
    evidence_type = func.lower(func.coalesce(
        ParcelFact.value["evidence_type"].as_string(),
        ParcelFact.value["source_type"].as_string(),
        "",
    ))
    observed_source = func.lower(func.coalesce(
        ParcelFact.value[OBSERVED_AT_SOURCE_KEY].as_string(),
        "",
    ))
    return [
        ParcelFact.parcel_id == parcel_id_column,
        ParcelFact.organization_id == organization_id_column,
        ParcelFact.is_current.is_(True),
        ParcelFact.fact_type.in_(AVAILABILITY_FACT_TYPES),
        status.in_(VERIFIED_AVAILABILITY_STATUSES),
        evidence_type.in_(("listing", "broker", "owner", "auction")),
        observed_source == "source",
        ParcelFact.observed_at >= current_time - AVAILABILITY_MAX_AGE,
        ParcelFact.confidence >= 0.7,
        or_(
            and_(ParcelFact.source_url.isnot(None), ParcelFact.source_url != ""),
            and_(ParcelFact.excerpt.isnot(None), ParcelFact.excerpt != ""),
        ),
    ]


def availability_label(facts: list[ParcelFact]) -> str:
    _fact, state = resolve_availability(facts)
    return {
        "verified_current": "verified_for_sale",
        "verified_stale": "verified_for_sale_stale",
        "verified_unaged": "verified_for_sale_unaged",
        "nearby_candidate": "nearby_candidate_not_verified_for_sale",
    }[state]
