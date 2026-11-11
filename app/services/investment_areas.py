"""Join a public research snapshot to separately scoped local source evidence."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import Lock
from time import monotonic

from sqlalchemy import func

from app.models.ingestion import IngestionRun, IngestionSource, PermitRecord
from app.services.investment_model import MODEL_VERSION, observed_demand, rank_metros
from app.utils.org_scope import active_query

_public_cache = None
_retry_after = 0.0
_cache_lock = Lock()
log = logging.getLogger(__name__)

# Explicit source-authority linkage, not a postal/ZIP inference or a complete
# metro sample. The Census 2025 crosswalk identifies Ocala as CBSA 36100.
LOCAL_CONTEXT_SOURCES = {"36100": ("ocala_fl_gis_new_building_projects",)}


def current_snapshot():
    global _public_cache, _retry_after
    if _public_cache is not None:
        return _public_cache
    if monotonic() < _retry_after:
        raise RuntimeError("Public input refresh unavailable")
    with _cache_lock:
        if _public_cache is not None:
            return _public_cache
        if monotonic() < _retry_after:
            raise RuntimeError("Public input refresh unavailable")
        try:
            from app.services.investment_reference import load_reference_snapshot

            value = load_reference_snapshot()
            rank_metros(value)
            _public_cache = value
            return value
        except Exception as exc:
            _retry_after = monotonic() + 60
            log.warning("investment_reference.load_failed category=%s", type(exc).__name__)
            raise RuntimeError("Public input refresh unavailable") from None


def local_evidence(db, cbsa):
    result = {"records": 0, "geocoded": 0, "sources": [],
              "geography_match": "unmapped", "is_complete_metro_inventory": False}
    keys = LOCAL_CONTEXT_SOURCES.get(cbsa, ())
    if not keys:
        return result
    result["geography_match"] = "declared_source_scope"
    sources = active_query(db.query(IngestionSource), IngestionSource).filter(
        IngestionSource.key.in_(keys), IngestionSource.is_active.is_(True),
    ).all()
    for source in sources:
        query = active_query(db.query(PermitRecord), PermitRecord).filter(
            PermitRecord.source_id == source.id, PermitRecord.is_active.is_(True))
        count = query.count()
        geocoded = query.filter(PermitRecord.latitude.between(-85, 85),
                               PermitRecord.longitude.between(-180, 180)).count()
        collected = active_query(db.query(func.max(IngestionRun.completed_at)), IngestionRun).filter(
            IngestionRun.source_id == source.id, IngestionRun.status == "completed").scalar()
        result["records"] += count
        result["geocoded"] += geocoded
        result["sources"].append({"id": str(source.id), "name": "Public local records", "records": count,
            "context_only": (source.settings or {}).get("context_only") is True,
            "last_collected_at": collected.isoformat() if collected else None})
    return result


def investment_area(db, cbsa, *, snapshot=None):
    snapshot = snapshot if snapshot is not None else current_snapshot()
    rows = rank_metros(snapshot)
    market = next((row for row in rows if row["cbsa"] == cbsa), None)
    if market is None:
        context = snapshot.get("context_metros", {}).get(cbsa)
        if context is None:
            raise LookupError("Metro has insufficient aligned input data")
        market = {"cbsa": cbsa, "name": context["name"], "score": None,
                  "momentum_percentile": None, "supply_percentile": None,
                  "price_momentum_2yr": None, "supply_surge": None,
                  **observed_demand(context)}
    return {
        "model_version": MODEL_VERSION, "status": "research" if market["score"] is not None else "insufficient_data", "year": snapshot["year"],
        "captured_at": snapshot["captured_at"], "snapshot_id": snapshot["snapshot_id"],
        "input_mode": "release_reference",
        "cohort_size": len(rows), "market": market,
        "local_evidence": local_evidence(db, cbsa),
        "investment_quality": {"status": "insufficient_data", "missing": [
            "rent_yield", "vacancy", "lease_quality", "capex", "liquidity", "parcel_economics",
            "jobs_and_wages", "verified_anchor_and_entitlement_events"]},
        "provenance": [{"label": "Public records", "captured_at": item["captured_at"],
                        "period": item["period"]} for item in snapshot["provenance"]],
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "limitations": [
            "Rank requires complete aligned HPI and unit histories; absent or mismatched geography yields no score, not zero.",
            "Research relative metro rank, not expected return, calibrated confidence or a buy recommendation.",
            "Annual 2025 release reference; newer government releases are not checked by this request. Not real-time or historical known-then data.",
            "Fixed 70% price-momentum / 30% residential-unit-surge research weights; no performance claim for this implementation.",
            "Population and migration are separate observed context, not validated score boosts.",
            "Local source evidence is incomplete, separately dated and does not change the metro score.",
            "Metro home-price research does not establish parcel, multifamily or retail investment returns.",
        ],
    }
