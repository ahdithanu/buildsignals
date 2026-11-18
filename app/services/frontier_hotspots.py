"""Frontier ignition hotspots: WHERE inside a metro permit filing is recent and
accelerating, computed from the requesting tenant's own local permit evidence.

This is the "where to look" layer between the metro research rank and actual
parcels. It is deliberately bounded:
  * It runs ONLY on org-scoped, geocoded PermitRecords already in the tenant's
    database - no external calls, no source activation, demo-safe read-only.
  * A hotspot is a ~1 km grid cell whose recent filing count is high relative to
    its own prior window (acceleration). That is a research signal of where land
    is converting, NOT a verified project, a parcel, or a for-sale listing.
  * Turning a hotspot into ranked, buyable parcels needs external county parcel
    GIS plus a licensed listings feed; that step is computed offline in
    research/appreciation and is not served live here.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

# permit_type / work_class keywords that indicate land conversion rather than
# alterations to an existing building (a development-share proxy, not a taxonomy).
_DEV_KEYWORDS = ("subdivision", "land division", "site plan", "master plan",
                 "partition", "pud", "plat", "new ", "tentative")

MODEL_VERSION = "frontier-hotspots-v0.1"


def _is_dev(*labels) -> bool:
    text = " ".join(label.lower() for label in labels if label)
    return any(keyword in text for keyword in _DEV_KEYWORDS)


def rank_hotspots(records, *, reference_year=None, grid=2, recent_window=3,
                  prior_window=3, min_recent=3, top_n=10):
    """Rank ~1 km cells by ignition. `records` is an iterable of
    (lat, lon, year, is_dev, address). Pure: no DB, no network, no clock unless
    reference_year is None (then it falls back to the current UTC year)."""
    rows = [r for r in records if _valid(r)]
    if reference_year is None:
        years = [r[2] for r in rows]
        reference_year = max(years) if years else datetime.now(timezone.utc).year
    recent_years = set(range(reference_year - recent_window + 1, reference_year + 1))
    prior_years = set(range(reference_year - recent_window - prior_window + 1,
                            reference_year - recent_window + 1))

    cells = defaultdict(lambda: {"recent": 0, "prior": 0, "dev": 0,
                                 "lat": [], "lon": [], "addr": None, "year": -1})
    for lat, lon, year, is_dev, address in rows:
        cell = cells[(round(lat, grid), round(lon, grid))]
        cell["lat"].append(lat); cell["lon"].append(lon)
        if year in recent_years:
            cell["recent"] += 1
            if is_dev:
                cell["dev"] += 1
        elif year in prior_years:
            cell["prior"] += 1
        if year > cell["year"]:
            cell["year"], cell["addr"] = year, address

    hotspots = []
    for cell in cells.values():
        if cell["recent"] < min_recent:
            continue
        accel = cell["recent"] / max(cell["prior"], 1)
        dev_share = cell["dev"] / cell["recent"] if cell["recent"] else 0.0
        score = cell["recent"] * min(accel, 5.0) * (1 + 0.5 * dev_share)
        hotspots.append({
            "lat": round(sum(cell["lat"]) / len(cell["lat"]), 5),
            "lon": round(sum(cell["lon"]) / len(cell["lon"]), 5),
            "recent": cell["recent"], "prior": cell["prior"],
            "acceleration": round(accel, 2), "dev_share": round(dev_share, 2),
            "score": round(score, 1), "sample_address": cell["addr"],
        })
    hotspots.sort(key=lambda h: (-h["score"], -h["recent"]))
    return {"reference_year": reference_year, "recent_window": recent_window,
            "prior_window": prior_window, "cell_count": len(cells),
            "hotspots": hotspots[:top_n]}


def _valid(record) -> bool:
    if len(record) != 5:
        return False
    lat, lon, year, _dev, _addr = record
    return (type(lat) in (int, float) and type(lon) in (int, float)
            and -85 <= lat <= 85 and -180 <= lon <= 180
            and isinstance(year, int))


def metro_hotspots(db, cbsa, source_keys):
    """Org-scoped hotspots from the tenant's geocoded permit evidence for the
    metro's declared local sources. Returns a research block; empty when the
    tenant has no aligned geocoded evidence (never fabricated)."""
    from app.models.ingestion import IngestionSource, PermitRecord
    from app.utils.org_scope import active_query

    if not source_keys:
        return {"status": "insufficient_data", "model_version": MODEL_VERSION,
                "reason": "no_declared_local_source", "hotspots": []}
    sources = active_query(db.query(IngestionSource), IngestionSource).filter(
        IngestionSource.key.in_(source_keys), IngestionSource.is_active.is_(True)).all()
    records = []
    for source in sources:
        rows = active_query(db.query(PermitRecord), PermitRecord).filter(
            PermitRecord.source_id == source.id, PermitRecord.is_active.is_(True),
            PermitRecord.latitude.isnot(None), PermitRecord.longitude.isnot(None),
            PermitRecord.filed_at.isnot(None),
        ).with_entities(PermitRecord.latitude, PermitRecord.longitude,
                        PermitRecord.filed_at, PermitRecord.permit_type,
                        PermitRecord.work_class, PermitRecord.address).all()
        for lat, lon, filed_at, ptype, work_class, address in rows:
            records.append((lat, lon, filed_at.year, _is_dev(ptype, work_class), address))
    if not records:
        return {"status": "insufficient_data", "model_version": MODEL_VERSION,
                "reason": "no_geocoded_dated_evidence", "hotspots": []}
    result = rank_hotspots(records)
    result["status"] = "research" if result["hotspots"] else "insufficient_data"
    result["model_version"] = MODEL_VERSION
    result["evidence_points"] = len(records)
    return result
