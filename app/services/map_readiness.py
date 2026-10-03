"""Measured workspace inventory, not geographic coverage or acquisition availability."""

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.ingestion import PermitRecord
from app.models.parcel import NearbyParcelSearch, ParcelRecord
from app.models.planning import PlanningRecord
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
    counts["has_geocoded_signals"] = counts["geocoded_signals"] > 0
    counts["has_geocoded_parcels"] = counts["geocoded_parcels"] > 0
    counts["has_saved_searches"] = counts["saved_searches"] > 0
    counts["ready_for_ranked_map"] = (
        counts["has_geocoded_signals"]
        and counts["has_geocoded_parcels"]
        and counts["has_saved_searches"]
    )
    return counts
