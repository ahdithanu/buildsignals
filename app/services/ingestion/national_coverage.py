"""Measured nationwide parcel coverage and connector-gap prioritization."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy import and_, distinct, exists, func, or_
from sqlalchemy.orm import Session

from app.models.parcel import NearbyParcelCandidate, ParcelFact, ParcelRecord
from app.services.ingestion.catalog import (
    US_STATE_CODES,
    extract_state_code,
    load_candidate_catalog,
    load_catalog,
)
from app.services.ingestion.measured_coverage import measured_coverage
from app.utils.org_scope import active_query

_AVAILABILITY_FACT_TYPES = {
    "availability",
    "listing",
    "broker_listing",
    "owner_availability",
    "sale_availability",
}
_VERIFIED_AVAILABILITY_STATUSES = {
    "available",
    "for_sale",
    "listed",
    "broker_listed",
    "owner_indicated_available",
}


def _availability_exists(parcel_id_column, organization_id_column):
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
    return exists().where(
        ParcelFact.parcel_id == parcel_id_column,
        ParcelFact.organization_id == organization_id_column,
        ParcelFact.is_current.is_(True),
        ParcelFact.fact_type.in_(_AVAILABILITY_FACT_TYPES),
        status.in_(_VERIFIED_AVAILABILITY_STATUSES),
        evidence_type.in_(("listing", "broker", "owner", "auction")),
        ParcelFact.confidence >= 0.7,
        or_(
            and_(ParcelFact.source_url.isnot(None), ParcelFact.source_url != ""),
            and_(ParcelFact.excerpt.isnot(None), ParcelFact.excerpt != ""),
        ),
    )


def _state_parcel_counts(db: Session) -> dict[str, dict[str, int]]:
    """Measure parcel inventory and availability without loading parcel rows."""
    state = func.upper(func.trim(ParcelRecord.state))
    counts = defaultdict(lambda: {
        "nearby_candidate_parcels": 0,
        "verified_available_parcels": 0,
        "nearby_verified_available_parcels": 0,
    })

    nearby_query = active_query(
        db.query(state.label("state"), func.count(distinct(ParcelRecord.id)).label("count")),
        ParcelRecord,
    ).join(
        NearbyParcelCandidate,
        and_(
            NearbyParcelCandidate.parcel_id == ParcelRecord.id,
            NearbyParcelCandidate.organization_id == ParcelRecord.organization_id,
        ),
    ).filter(
        ParcelRecord.is_active.is_(True),
        NearbyParcelCandidate.review_status != "dismissed",
        state.in_(US_STATE_CODES),
    ).group_by(state)
    for row in nearby_query.all():
        counts[row.state]["nearby_candidate_parcels"] = int(row.count or 0)

    available_query = active_query(
        db.query(state.label("state"), func.count(distinct(ParcelRecord.id)).label("count")),
        ParcelRecord,
    ).filter(
        ParcelRecord.is_active.is_(True),
        state.in_(US_STATE_CODES),
        _availability_exists(ParcelRecord.id, ParcelRecord.organization_id),
    ).group_by(state)
    for row in available_query.all():
        counts[row.state]["verified_available_parcels"] = int(row.count or 0)

    nearby_available_query = active_query(
        db.query(state.label("state"), func.count(distinct(ParcelRecord.id)).label("count")),
        ParcelRecord,
    ).join(
        NearbyParcelCandidate,
        and_(
            NearbyParcelCandidate.parcel_id == ParcelRecord.id,
            NearbyParcelCandidate.organization_id == ParcelRecord.organization_id,
        ),
    ).filter(
        ParcelRecord.is_active.is_(True),
        NearbyParcelCandidate.review_status != "dismissed",
        state.in_(US_STATE_CODES),
        _availability_exists(ParcelRecord.id, ParcelRecord.organization_id),
    ).group_by(state)
    for row in nearby_available_query.all():
        counts[row.state]["nearby_verified_available_parcels"] = int(row.count or 0)

    return counts


def _catalog_state_counts() -> tuple[dict[str, int], dict[str, int], dict[str, dict[str, int]]]:
    configured: Counter[str] = Counter()
    candidates: Counter[str] = Counter()
    candidate_statuses: dict[str, Counter[str]] = defaultdict(Counter)
    configured_keys: set[str] = set()

    for entry in load_catalog():
        if entry.record_type != "parcel" or not entry.is_active:
            continue
        configured_keys.add(entry.key)
        state = extract_state_code(entry.jurisdiction, entry.settings or {})
        if state:
            configured[state] += 1

    for entry in load_candidate_catalog(include_promoted=True):
        if entry.key in configured_keys or entry.record_type != "parcel":
            continue
        state = extract_state_code(entry.jurisdiction, entry.model_dump())
        if state:
            candidates[state] += 1
            candidate_statuses[state][entry.status] += 1

    return dict(configured), dict(candidates), {
        state: dict(statuses) for state, statuses in candidate_statuses.items()
    }


def _next_action(posture: str, counts: dict[str, int]) -> tuple[str, int, str]:
    if posture == "uncovered":
        return "research_official_parcel_source", 80, "No configured or candidate parcel source"
    if posture == "candidate_only":
        return "resolve_candidate_source_gate", 100, "Candidate source exists but is not admitted"
    if posture == "configured_only":
        return "run_configured_parcel_ingestion", 90, "Parcel source is configured but has no measured records"
    if counts["nearby_verified_available_parcels"]:
        return "review_verified_available_parcels", 10, "Nearby parcels have source-backed availability evidence"
    if counts["nearby_candidate_parcels"]:
        return "attach_availability_evidence", 55, "Nearby parcel candidates exist without verified availability"
    return "run_nearby_parcel_search", 70, "Measured parcel inventory exists but no nearby candidates are saved"


def national_parcel_coverage(db: Session, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    measured = measured_coverage(db, record_type="parcel", limit=100, now=now)
    measured_states = {
        row["state"]: row
        for row in measured["readiness_states"]
        if row.get("state") in US_STATE_CODES
    }
    configured, candidates, candidate_statuses = _catalog_state_counts()
    parcel_counts = _state_parcel_counts(db)
    states: list[dict] = []

    for state in US_STATE_CODES:
        measured_row = measured_states.get(state, {})
        measured_parcel_counts = parcel_counts.get(state, {})
        counts = {
            "nearby_candidate_parcels": measured_parcel_counts.get("nearby_candidate_parcels", 0),
            "verified_available_parcels": measured_parcel_counts.get("verified_available_parcels", 0),
            "nearby_verified_available_parcels": measured_parcel_counts.get("nearby_verified_available_parcels", 0),
        }
        if int(measured_row.get("stored_records") or 0) > 0:
            posture = "measured"
        elif configured.get(state, 0):
            posture = "configured_only"
        elif candidates.get(state, 0):
            posture = "candidate_only"
        else:
            posture = "uncovered"
        action, priority, reason = _next_action(posture, counts)
        states.append({
            "state": state,
            "posture": posture,
            "configured_source_count": configured.get(state, 0),
            "candidate_source_count": candidates.get(state, 0),
            "measured_source_count": int(measured_row.get("source_count") or 0),
            "stored_parcel_records": int(measured_row.get("stored_records") or 0),
            "geocoded_parcel_records": int(measured_row.get("geocoded_records") or 0),
            "recently_seen_parcel_records": int(measured_row.get("recently_seen_records") or 0),
            **counts,
            "candidate_status_counts": candidate_statuses.get(state, {}),
            "next_action": action,
            "priority_score": priority,
            "priority_reason": reason,
        })

    posture_counts = Counter(row["posture"] for row in states)
    summary = {
        "state_count": len(states),
        "measured_state_count": posture_counts["measured"],
        "configured_only_state_count": posture_counts["configured_only"],
        "candidate_only_state_count": posture_counts["candidate_only"],
        "uncovered_state_count": posture_counts["uncovered"],
        "states_with_nearby_candidates": sum(row["nearby_candidate_parcels"] > 0 for row in states),
        "states_with_verified_available_parcels": sum(row["verified_available_parcels"] > 0 for row in states),
        "stored_parcel_records": sum(row["stored_parcel_records"] for row in states),
        "geocoded_parcel_records": sum(row["geocoded_parcel_records"] for row in states),
        "nearby_candidate_parcels": sum(row["nearby_candidate_parcels"] for row in states),
        "verified_available_parcels": sum(row["verified_available_parcels"] for row in states),
        "nearby_verified_available_parcels": sum(row["nearby_verified_available_parcels"] for row in states),
    }
    queue = sorted(
        states,
        key=lambda row: (-row["priority_score"], -row["candidate_source_count"], row["state"]),
    )
    return {
        "measured_at": now,
        "record_type": "parcel",
        "scope": "Authenticated organization; active catalog parcel sources and stored canonical parcel records only",
        "coverage_claim": "A measured state has stored parcel records. Configured, candidate, and uncovered states are not represented as live parcel coverage.",
        "summary": summary,
        "states": states,
        "next_connector_targets": queue[:15],
        "warnings": [
            "Catalog configuration is not proof of imported records or statewide completeness.",
            "Nearby candidates are not for-sale evidence; availability requires source-backed listing, broker, owner, or auction evidence.",
            "No live source, canary, activation, or legal-hold state is changed by this report.",
        ],
    }
