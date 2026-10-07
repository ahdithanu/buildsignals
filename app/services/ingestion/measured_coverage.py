"""Tenant-scoped stored-record measurements, never catalog-derived coverage claims."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func

from app.models.ingestion import IngestionRun, IngestionSource, PermitRecord, RawSourceRecord
from app.models.parcel import ParcelRecord
from app.models.planning import PlanningRecord
from app.services.ingestion.catalog import US_STATE_CODES
from app.utils.org_scope import get_org_id, scope_query

MODELS = {"parcel": ParcelRecord, "permit": PermitRecord, "planning": PlanningRecord}
READINESS_STATUSES = (
    "fresh",
    "empty",
    "disabled",
    "stale_collection",
    "stale_source_date",
    "unknown_source_date",
)


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


def _readiness_status_counts(source_payloads: list[dict]) -> dict[str, int]:
    counts = {status: 0 for status in READINESS_STATUSES}
    for item in source_payloads:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return counts


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


def _jurisdiction_rollup(db, model, *, state, valid_coordinate, cutoff: datetime,
                         now: datetime, source_ids: list[str], limit: int = 10) -> list[dict]:
    if not source_ids:
        return []
    normalized_jurisdiction = func.nullif(func.trim(model.jurisdiction), "").label("jurisdiction")
    query = scope_query(db.query(
        normalized_jurisdiction,
        state,
        func.count(func.distinct(model.source_id)).label("source_count"),
        func.count(model.id).label("stored_records"),
        func.sum(case((valid_coordinate, 1), else_=0)).label("geocoded_records"),
        func.sum(case((model.last_seen_at.between(cutoff, now), 1), else_=0)).label("recently_seen_records"),
        func.sum(case((RawSourceRecord.source_updated_at.between(cutoff, now), 1), else_=0)).label("recent_source_date_records"),
    ), model).outerjoin(RawSourceRecord, and_(
        RawSourceRecord.id == model.latest_raw_record_id,
        RawSourceRecord.organization_id == get_org_id(),
        RawSourceRecord.source_id == model.source_id,
    )).filter(model.source_id.in_(source_ids))
    if hasattr(model, "is_active"):
        query = query.filter(model.is_active.is_(True))
    rows = query.group_by(normalized_jurisdiction, state).order_by(
        func.count(model.id).desc(),
        state.nulls_last(),
        normalized_jurisdiction.nulls_last(),
    ).limit(limit).all()
    return [dict(row._mapping) for row in rows]


def _source_readiness(source: IngestionSource, rows: list[dict]) -> tuple[str, list[str]]:
    stored = sum(row["stored_records"] for row in rows)
    recent_collection = sum(row["recently_seen_records"] for row in rows)
    recent_source_date = sum(row["recent_source_date_records"] for row in rows)
    unknown_source_dates = sum(row["unknown_source_date_records"] for row in rows)
    geocoded = sum(row["geocoded_records"] for row in rows)
    reasons: list[str] = []
    if not source.is_active:
        reasons.append("collection disabled")
    if stored == 0:
        reasons.append("no stored records measured")
        return "empty", reasons
    if recent_collection == 0:
        reasons.append("no recent collection evidence")
    if recent_source_date == 0:
        reasons.append("no recent source-date evidence")
    if unknown_source_dates > 0:
        reasons.append("some records have unknown source dates")
    if geocoded == 0:
        reasons.append("no valid coordinates measured")
    if not source.is_active:
        return "disabled", reasons
    if recent_collection == 0:
        return "stale_collection", reasons
    if recent_source_date == 0:
        return "stale_source_date", reasons
    if unknown_source_dates > 0:
        return "unknown_source_date", reasons
    return "fresh", reasons


def _source_completion_evidence(db, source: IngestionSource) -> dict:
    settings = source.settings or {}
    latest_run = scope_query(db.query(IngestionRun), IngestionRun).filter(
        IngestionRun.source_id == source.id,
        IngestionRun.trigger != "canary",
    ).order_by(IngestionRun.started_at.desc()).first()
    latest_success = scope_query(db.query(IngestionRun), IngestionRun).filter(
        IngestionRun.source_id == source.id,
        IngestionRun.trigger != "canary",
        IngestionRun.status.in_(("completed", "partial")),
        IngestionRun.records_failed == 0,
    ).order_by(IngestionRun.started_at.desc()).first()
    reconciliation_mode = str(settings.get("reconciliation_mode") or "")
    full_snapshot_source = "full" in reconciliation_mode
    completed_without_cursor = (
        latest_success is not None
        and latest_success.status == "completed"
        and latest_success.checkpoint is None
    )
    full_source_completed = bool(full_snapshot_source and completed_without_cursor)
    completion_kind = (
        "full_source_snapshot_completed" if full_source_completed
        else "incremental_window_completed" if completed_without_cursor
        else "partial_or_cursor_pending" if latest_success
        else "no_successful_run"
    )
    blockers = []
    if not full_snapshot_source:
        blockers.append("source is not configured for full-source snapshot reconciliation")
    if latest_run is None:
        blockers.append("no operational ingestion run recorded")
    elif latest_run.status in {"failed", "partial_with_errors"}:
        blockers.append("latest operational run failed or rejected records")
    if latest_success is None:
        blockers.append("no successful operational run with zero failed records")
    elif latest_success.checkpoint is not None:
        blockers.append("latest successful run left a checkpoint, so extraction is incomplete")
    return {
        "reconciliation_mode": reconciliation_mode or None,
        "full_snapshot_source": full_snapshot_source,
        "latest_run_status": latest_run.status if latest_run else None,
        "latest_run_completed_at": latest_run.completed_at if latest_run else None,
        "latest_run_checkpoint": latest_run.checkpoint if latest_run else None,
        "latest_run_records_seen": latest_run.records_seen if latest_run else None,
        "latest_run_records_inserted": latest_run.records_inserted if latest_run else None,
        "latest_run_records_updated": latest_run.records_updated if latest_run else None,
        "latest_run_records_failed": latest_run.records_failed if latest_run else None,
        "latest_success_status": latest_success.status if latest_success else None,
        "latest_success_completed_at": latest_success.completed_at if latest_success else None,
        "latest_success_checkpoint": latest_success.checkpoint if latest_success else None,
        "latest_success_records_seen": latest_success.records_seen if latest_success else None,
        "full_source_completed": full_source_completed,
        "completion_kind": completion_kind,
        "completion_blockers": blockers,
        "deduplication_invariant": (
            "Stored parcel identity is unique by source_id + external_parcel_id; "
            "raw versions are unique by source_id + external_record_id + content_hash."
        ),
    }


def measured_coverage(db, *, record_type: str, limit: int = 50, offset: int = 0,
                      freshness_hours: int = 72, now: datetime | None = None,
                      readiness_status: str | None = None) -> dict:
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
    source_payloads = []
    for source in all_sources:
        rows = by_source.get(source.id, [])
        status, reasons = _source_readiness(source, rows)
        source_payloads.append({
            "source": source,
            "status": status,
            "reasons": reasons,
            "stored_records": sum(row["stored_records"] for row in rows),
            "observed_states": rows,
        })
    readiness_status_counts = _readiness_status_counts(source_payloads)
    if readiness_status:
        source_payloads = [item for item in source_payloads if item["status"] == readiness_status]
    page_payloads = source_payloads[offset:offset + limit + 1]
    has_more = len(page_payloads) > limit
    page_payloads = page_payloads[:limit]
    page_ids = [item["source"].id for item in page_payloads]
    page_states = [row for source_id in page_ids for row in by_source.get(source_id, [])]
    return {
        "measured_at": now, "record_type": record_type,
        "scope": "Stored active canonical records for the authenticated organization; not provider totals or statewide completeness",
        "count_semantics": "Unique within each source; overlapping sources are not deduplicated",
        "freshness_hours": freshness_hours, "limit": limit, "offset": offset, "has_more": has_more,
        "page_totals": _sum_totals(page_states, source_count=len(page_payloads)) if page_states else _zero_totals(len(page_payloads)),
        "readiness": _readiness_rollup(all_sources, by_source),
        "readiness_status_counts": readiness_status_counts,
        "readiness_states": _state_rollup(by_source),
        "readiness_jurisdictions": _jurisdiction_rollup(
            db, model, state=state, valid_coordinate=valid_coordinate,
            cutoff=cutoff, now=now, source_ids=all_ids,
        ),
        "sources": [
            {
                "source_id": item["source"].id,
                "source_key": item["source"].key,
                "configured_active": item["source"].is_active,
                "configured_jurisdiction": item["source"].jurisdiction,
                "stored_records": item["stored_records"],
                "readiness_status": item["status"],
                "readiness_reasons": item["reasons"],
                "completion_evidence": _source_completion_evidence(db, item["source"]),
                "observed_states": item["observed_states"],
            }
            for item in page_payloads
        ],
        "warnings": ["Last seen is collection evidence, not source publication freshness.",
                     "Coordinate extents bound observed points only; they do not imply complete coverage inside the bounds.",
                     "Unknown source dates and geography remain unknown; no catalog fallback is used.",
                     "A configured jurisdiction or an observed state does not establish complete geographic coverage.",
                     "Parcel records do not establish for-sale availability."],
    }
