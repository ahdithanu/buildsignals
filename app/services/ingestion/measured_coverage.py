"""Tenant-scoped stored-record measurements, never catalog-derived coverage claims."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func

from app.models.ingestion import IngestionSource, PermitRecord, RawSourceRecord
from app.models.parcel import ParcelRecord
from app.models.planning import PlanningRecord
from app.services.ingestion.catalog import US_STATE_CODES
from app.utils.org_scope import get_org_id, scope_query

MODELS = {"parcel": ParcelRecord, "permit": PermitRecord, "planning": PlanningRecord}


def measured_coverage(db, *, record_type: str, limit: int = 50, offset: int = 0,
                      freshness_hours: int = 72, now: datetime | None = None) -> dict:
    if record_type not in MODELS or not 1 <= limit <= 100 or offset < 0 or not 1 <= freshness_hours <= 8760:
        raise ValueError("Invalid coverage query")
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=freshness_hours)
    model = MODELS[record_type]
    normalized_state = func.upper(func.trim(model.state))
    state = case((normalized_state.in_((*US_STATE_CODES, "DC")), normalized_state), else_=None).label("state")
    sources = scope_query(db.query(IngestionSource), IngestionSource).filter_by(
        record_type=record_type,
    ).order_by(IngestionSource.key, IngestionSource.id).offset(offset).limit(limit + 1).all()
    has_more = len(sources) > limit
    sources = sources[:limit]
    ids = [source.id for source in sources]
    valid_coordinate = and_(model.latitude.between(-90, 90), model.longitude.between(-180, 180))
    query = scope_query(db.query(
        model.source_id, state,
        func.count(model.id).label("stored_records"),
        func.sum(case((valid_coordinate, 1), else_=0)).label("geocoded_records"),
        func.sum(case((model.last_seen_at.between(cutoff, now), 1), else_=0)).label("recently_seen_records"),
        func.sum(case((RawSourceRecord.source_updated_at.is_(None), 1), else_=0)).label("unknown_source_date_records"),
        func.sum(case((RawSourceRecord.source_updated_at > now, 1), else_=0)).label("future_source_date_records"),
        func.sum(case((RawSourceRecord.source_updated_at.between(cutoff, now), 1), else_=0)).label("recent_source_date_records"),
        func.max(model.last_seen_at).label("newest_seen_at"),
        func.max(RawSourceRecord.source_updated_at).label("newest_source_date"),
        func.count(func.distinct(model.jurisdiction)).label("observed_jurisdiction_count"),
        func.min(case((valid_coordinate, model.latitude))).label("min_latitude"),
        func.max(case((valid_coordinate, model.latitude))).label("max_latitude"),
        func.min(case((valid_coordinate, model.longitude))).label("min_longitude"),
        func.max(case((valid_coordinate, model.longitude))).label("max_longitude"),
    ), model).outerjoin(RawSourceRecord, and_(
        RawSourceRecord.id == model.latest_raw_record_id,
        RawSourceRecord.organization_id == get_org_id(),
        RawSourceRecord.source_id == model.source_id,
    )).filter(model.source_id.in_(ids))
    if hasattr(model, "is_active"):
        query = query.filter(model.is_active.is_(True))
    groups = query.group_by(model.source_id, state).order_by(model.source_id, state).all() if ids else []
    by_source = {}
    for row in groups:
        item = dict(row._mapping)
        source_id = item.pop("source_id")
        by_source.setdefault(source_id, []).append(item)
    return {
        "measured_at": now, "record_type": record_type,
        "scope": "Stored active canonical records for the authenticated organization; not provider totals or statewide completeness",
        "count_semantics": "Unique within each source; overlapping sources are not deduplicated",
        "freshness_hours": freshness_hours, "limit": limit, "offset": offset, "has_more": has_more,
        "sources": [{"source_id": source.id, "source_key": source.key,
                     "configured_active": source.is_active, "configured_jurisdiction": source.jurisdiction,
                     "stored_records": sum(row["stored_records"] for row in by_source.get(source.id, [])),
                     "observed_states": by_source.get(source.id, [])} for source in sources],
        "warnings": ["Last seen is collection evidence, not source publication freshness.",
                     "Coordinate extents bound observed points only; they do not imply complete coverage inside the bounds.",
                     "Unknown source dates and geography remain unknown; no catalog fallback is used.",
                     "A configured jurisdiction or an observed state does not establish complete geographic coverage.",
                     "Parcel records do not establish for-sale availability."],
    }
