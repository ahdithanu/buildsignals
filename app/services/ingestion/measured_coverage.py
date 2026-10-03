"""Tenant-scoped stored-record measurements, never catalog-derived coverage claims."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func

from app.models.ingestion import IngestionSource, PermitRecord, RawSourceRecord
from app.models.parcel import ParcelRecord
from app.models.planning import PlanningRecord
from app.services.ingestion.catalog import US_STATE_CODES
from app.utils.org_scope import get_org_id, scope_query

MODELS = {"parcel": ParcelRecord, "permit": PermitRecord, "planning": PlanningRecord}


def _zero_totals(source_count: int = 0) -> dict:
    return {
        "source_count": source_count,
        "stored_records": 0,
        "geocoded_records": 0,
        "recently_seen_records": 0,
        "unknown_source_date_records": 0,
        "future_source_date_records": 0,
        "recent_source_date_records": 0,
        "observed_state_count": 0,
        "observed_jurisdiction_count": 0,
    }


def _sum_totals(rows: list[dict], *, source_count: int) -> dict:
    observed_state_codes = {row["state"] for row in rows if row["state"]}
    return {
        "source_count": source_count,
        "stored_records": sum(row["stored_records"] for row in rows),
        "geocoded_records": sum(row["geocoded_records"] for row in rows),
        "recently_seen_records": sum(row["recently_seen_records"] for row in rows),
        "unknown_source_date_records": sum(row["unknown_source_date_records"] for row in rows),
        "future_source_date_records": sum(row["future_source_date_records"] for row in rows),
        "recent_source_date_records": sum(row["recent_source_date_records"] for row in rows),
        "observed_state_count": len(observed_state_codes),
        "observed_jurisdiction_count": sum(row["observed_jurisdiction_count"] for row in rows),
    }


def _readiness_rollup(all_sources: list[IngestionSource], rows_by_source: dict[str, list[dict]]) -> dict:
    totals = _sum_totals([row for rows in rows_by_source.values() for row in rows],
                         source_count=len(all_sources))
    sources_with_records = 0
    sources_with_recent_collection = 0
    sources_with_recent_source_date = 0
    sources_with_unknown_source_dates = 0
    sources_with_future_source_dates = 0
    sources_with_geocoded_records = 0
    for source in all_sources:
        rows = rows_by_source.get(source.id, [])
        stored = sum(row["stored_records"] for row in rows)
        sources_with_records += int(stored > 0)
        sources_with_recent_collection += int(sum(row["recently_seen_records"] for row in rows) > 0)
        sources_with_recent_source_date += int(sum(row["recent_source_date_records"] for row in rows) > 0)
        sources_with_unknown_source_dates += int(sum(row["unknown_source_date_records"] for row in rows) > 0)
        sources_with_future_source_dates += int(sum(row["future_source_date_records"] for row in rows) > 0)
        sources_with_geocoded_records += int(sum(row["geocoded_records"] for row in rows) > 0)
    return {
        **totals,
        "total_source_count": len(all_sources),
        "active_source_count": sum(1 for source in all_sources if source.is_active),
        "disabled_source_count": sum(1 for source in all_sources if not source.is_active),
        "sources_with_records": sources_with_records,
        "empty_source_count": len(all_sources) - sources_with_records,
        "sources_with_recent_collection": sources_with_recent_collection,
        "sources_with_recent_source_date": sources_with_recent_source_date,
        "sources_with_unknown_source_dates": sources_with_unknown_source_dates,
        "sources_with_future_source_dates": sources_with_future_source_dates,
        "sources_with_geocoded_records": sources_with_geocoded_records,
        "stale_collection_source_count": sources_with_records - sources_with_recent_collection,
        "stale_source_date_source_count": sources_with_records - sources_with_recent_source_date,
    }


def _state_rollup(rows_by_source: dict[str, list[dict]]) -> list[dict]:
    states: dict[str | None, dict] = {}
    source_sets: dict[str | None, set[str]] = {}
    for source_id, rows in rows_by_source.items():
        for row in rows:
            state = row["state"]
            current = states.setdefault(state, {
                "state": state,
                "source_count": 0,
                "stored_records": 0,
                "geocoded_records": 0,
                "recently_seen_records": 0,
                "recent_source_date_records": 0,
                "unknown_source_date_records": 0,
            })
            source_sets.setdefault(state, set()).add(source_id)
            current["stored_records"] += row["stored_records"]
            current["geocoded_records"] += row["geocoded_records"]
            current["recently_seen_records"] += row["recently_seen_records"]
            current["recent_source_date_records"] += row["recent_source_date_records"]
            current["unknown_source_date_records"] += row["unknown_source_date_records"]
    for state, source_ids in source_sets.items():
        states[state]["source_count"] = len(source_ids)
    return sorted(
        states.values(),
        key=lambda row: (-row["stored_records"], row["state"] is None, row["state"] or ""),
    )


def measured_coverage(db, *, record_type: str, limit: int = 50, offset: int = 0,
                      freshness_hours: int = 72, now: datetime | None = None) -> dict:
    if record_type not in MODELS or not 1 <= limit <= 100 or offset < 0 or not 1 <= freshness_hours <= 8760:
        raise ValueError("Invalid coverage query")
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=freshness_hours)
    model = MODELS[record_type]
    normalized_state = func.upper(func.trim(model.state))
    state = case((normalized_state.in_((*US_STATE_CODES, "DC")), normalized_state), else_=None).label("state")
    source_query = scope_query(db.query(IngestionSource), IngestionSource).filter_by(
        record_type=record_type,
    ).order_by(IngestionSource.key, IngestionSource.id)
    all_sources = source_query.all()
    sources = all_sources[offset:offset + limit + 1]
    has_more = len(sources) > limit
    sources = sources[:limit]
    page_ids = [source.id for source in sources]
    all_ids = [source.id for source in all_sources]
    valid_coordinate = and_(model.latitude.between(-90, 90), model.longitude.between(-180, 180))
    base_query = scope_query(db.query(
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
    )).filter(model.source_id.in_(all_ids))
    if hasattr(model, "is_active"):
        base_query = base_query.filter(model.is_active.is_(True))
    groups = base_query.group_by(model.source_id, state).order_by(model.source_id, state).all() if all_ids else []
    by_source = {}
    for row in groups:
        item = dict(row._mapping)
        source_id = item.pop("source_id")
        by_source.setdefault(source_id, []).append(item)
    page_states = [row for source_id in page_ids for row in by_source.get(source_id, [])]
    return {
        "measured_at": now, "record_type": record_type,
        "scope": "Stored active canonical records for the authenticated organization; not provider totals or statewide completeness",
        "count_semantics": "Unique within each source; overlapping sources are not deduplicated",
        "freshness_hours": freshness_hours, "limit": limit, "offset": offset, "has_more": has_more,
        "page_totals": _sum_totals(page_states, source_count=len(sources)) if page_states else _zero_totals(len(sources)),
        "readiness": _readiness_rollup(all_sources, by_source),
        "readiness_states": _state_rollup(by_source),
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
