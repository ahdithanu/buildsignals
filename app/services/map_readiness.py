"""Measured workspace inventory and parcel discovery readiness.

The counts intentionally distinguish stored parcel records, ranked nearby
candidates, and source-backed availability. A nearby candidate is a research
lead; it is not evidence that a parcel is for sale.
"""

from sqlalchemy import and_, case, exists, func
from sqlalchemy.orm import Session

from app.models.ingestion import PermitRecord
from app.models.parcel import NearbyParcelCandidate, NearbyParcelSearch, ParcelRecord
from app.models.planning import PlanningRecord
from app.services.parcel_availability import current_availability_conditions
from app.utils.org_scope import active_query


def _active_count_and_located(db: Session, model) -> tuple[int, int]:
    valid = model.latitude.between(-90, 90) & model.longitude.between(-180, 180)
    query = active_query(
        db.query(func.count(model.id), func.sum(case((valid, 1), else_=0))),
        model,
    )
    if hasattr(model, "is_active"):
        query = query.filter(model.is_active.is_(True))
    total, located = query.one()
    return int(total), int(located or 0)


def _verified_availability_exists(parcel_id_column, organization_id_column):
    return exists().where(*current_availability_conditions(
        parcel_id_column,
        organization_id_column,
    ))


def map_readiness(db: Session) -> dict:
    counts = {}
    for label, model in (("permits", PermitRecord), ("parcels", ParcelRecord)):
        counts[label], counts[f"geocoded_{label}"] = _active_count_and_located(db, model)
    planning_total, geocoded_planning = _active_count_and_located(db, PlanningRecord)
    counts["planning_records"] = planning_total
    counts["geocoded_planning_records"] = geocoded_planning
    counts["signals"] = counts["permits"] + planning_total
    counts["geocoded_signals"] = counts["geocoded_permits"] + geocoded_planning
    counts["saved_searches"] = active_query(
        db.query(func.count(NearbyParcelSearch.id)), NearbyParcelSearch,
    ).scalar() or 0
    candidate_rows = active_query(
        db.query(NearbyParcelCandidate.parcel_id), NearbyParcelCandidate,
    ).filter(NearbyParcelCandidate.review_status != "dismissed").distinct().all()
    candidate_parcel_ids = {row[0] for row in candidate_rows}
    counts["nearby_candidate_parcels"] = len(candidate_parcel_ids)

    counts["verified_available_parcels"] = int(active_query(
        db.query(func.count(func.distinct(ParcelRecord.id))), ParcelRecord,
    ).filter(
        ParcelRecord.is_active.is_(True),
        _verified_availability_exists(ParcelRecord.id, ParcelRecord.organization_id),
    ).scalar() or 0)
    counts["nearby_verified_available_parcels"] = int(active_query(
        db.query(func.count(func.distinct(NearbyParcelCandidate.parcel_id))),
        NearbyParcelCandidate,
    ).join(
        ParcelRecord,
        and_(
            NearbyParcelCandidate.parcel_id == ParcelRecord.id,
            NearbyParcelCandidate.organization_id == ParcelRecord.organization_id,
        ),
    ).filter(
        NearbyParcelCandidate.review_status != "dismissed",
        ParcelRecord.is_active.is_(True),
        _verified_availability_exists(
            NearbyParcelCandidate.parcel_id,
            NearbyParcelCandidate.organization_id,
        ),
    ).scalar() or 0)
    counts["has_geocoded_signals"] = counts["geocoded_signals"] > 0
    counts["has_geocoded_parcels"] = counts["geocoded_parcels"] > 0
    counts["has_saved_searches"] = counts["saved_searches"] > 0
    if not counts["has_geocoded_signals"]:
        counts["discovery_stage"] = "signals_not_geocoded"
        counts["discovery_next_action"] = "Ingest or geocode permit and planning signals."
    elif not counts["has_geocoded_parcels"]:
        counts["discovery_stage"] = "parcel_records_not_geocoded"
        counts["discovery_next_action"] = "Ingest geocoded parcel records for the target jurisdictions."
    elif not counts["has_saved_searches"]:
        counts["discovery_stage"] = "search_not_run"
        counts["discovery_next_action"] = "Run a bounded nearby-parcel search from a geocoded signal."
    elif not counts["nearby_candidate_parcels"]:
        counts["discovery_stage"] = "no_nearby_matches"
        counts["discovery_next_action"] = "Review radius and parcel-source coverage before treating this as a zero-market result."
    elif not counts["nearby_verified_available_parcels"]:
        counts["discovery_stage"] = "candidates_need_availability_evidence"
        counts["discovery_next_action"] = "Attach listing, broker, owner, or auction evidence before calling a candidate available."
    else:
        counts["discovery_stage"] = "verified_available_candidates"
        counts["discovery_next_action"] = "Review verified candidates and move qualified parcels into acquisition workflow."
    counts["ready_for_ranked_map"] = (
        counts["has_geocoded_signals"]
        and counts["has_geocoded_parcels"]
        and counts["has_saved_searches"]
    )
    return counts
