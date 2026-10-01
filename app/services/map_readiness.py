"""Measured workspace inventory, not geographic coverage or acquisition availability."""

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.ingestion import PermitRecord
from app.models.parcel import NearbyParcelSearch, ParcelRecord
from app.utils.org_scope import active_query


def map_readiness(db: Session) -> dict:
    counts = {}
    for label, model in (("permits", PermitRecord), ("parcels", ParcelRecord)):
        valid = model.latitude.between(-90, 90) & model.longitude.between(-180, 180)
        total, located = active_query(db.query(
            func.count(model.id), func.sum(case((valid, 1), else_=0)),
        ), model).filter(model.is_active.is_(True)).one()
        counts[label] = int(total)
        counts[f"geocoded_{label}"] = int(located or 0)
    counts["saved_searches"] = active_query(
        db.query(func.count(NearbyParcelSearch.id)), NearbyParcelSearch,
    ).scalar() or 0
    counts["has_geocoded_signals"] = counts["geocoded_permits"] > 0
    counts["has_geocoded_parcels"] = counts["geocoded_parcels"] > 0
    counts["has_saved_searches"] = counts["saved_searches"] > 0
    counts["ready_for_ranked_map"] = (
        counts["has_geocoded_signals"]
        and counts["has_geocoded_parcels"]
        and counts["has_saved_searches"]
    )
    return counts
