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

# ICP tier: a research classification of a metro's growth/development profile,
# applied to already-ranked rows. It is NOT an expected return, a buy signal or
# an investment-quality score. The tier is set only by the two scored,
# cohort-relative percentiles (price momentum, residential-unit surge);
# population and migration appear in the rationale as context, never as a tier
# input, matching their exclusion from the score. This lives here, downstream of
# the snapshot, so it is deliberately NOT part of the reference's code-version
# binding over the ranking/transform code.
ICP_STRONG_MOMENTUM = 0.75
ICP_STRONG_SUPPLY = 0.60
ICP_EMERGING_SCORE = 0.60
ICP_TIERS = ("strong", "emerging", "stable")


def _demand_phrase(row):
    parts = []
    growth, migration = row.get("population_growth_1yr"), row.get("net_migration_per_1000")
    if growth is not None:
        parts.append(f"population {growth * 100:+.1f}%/yr")
    if migration is not None:
        parts.append(f"net migration {migration:+.1f}/1k")
    return f" Context: {', '.join(parts)}." if parts else ""


def icp_tier(row):
    """Return (tier, rationale) for a scored metro row. Tier is one of ICP_TIERS,
    decided only by the scored momentum/supply percentiles; the rationale adds
    observed demand context without changing the tier."""
    mm, ss, score = row["momentum_percentile"], row["supply_percentile"], row["score"]
    mp, sp = round(mm * 100), round(ss * 100)
    if mm >= ICP_STRONG_MOMENTUM and ss >= ICP_STRONG_SUPPLY:
        tier = "strong"
        why = f"Price growth (P{mp}) and development (P{sp}) both lead the cohort."
    elif score >= ICP_EMERGING_SCORE:
        tier = "emerging"
        lead = "price growth" if mm >= ss else "development"
        why = f"Above-cohort growth; {lead} leads (momentum P{mp}, supply P{sp})."
    else:
        tier = "stable"
        why = f"Around or below the cohort on growth and development (momentum P{mp}, supply P{sp})."
    return tier, why + _demand_phrase(row)


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


def frontier(db, cbsa):
    """Where-to-look layer: ignition hotspots from the tenant's own evidence,
    plus the honest status of the (offline, not-live) ranked-parcel step. Gated
    off by default."""
    from app import config
    from app.services.frontier_hotspots import metro_hotspots

    preview = {
        "status": "research_preview",
        "note": ("Ranked buyable parcels and for-sale status require external "
                 "county parcel GIS plus a licensed listings feed; computed "
                 "offline in research/appreciation, not served live here."),
    }
    if not getattr(config, "FRONTIER_HOTSPOTS_ENABLED", False):
        return {"status": "disabled", "parcel_candidates": preview}
    hotspots = metro_hotspots(db, cbsa, LOCAL_CONTEXT_SOURCES.get(cbsa, ()))
    return {
        **hotspots,
        "parcel_candidates": preview,
        "limitations": [
            "Hotspots mark where permit filing is recent and accelerating, not verified projects, parcels or for-sale listings.",
            "Computed only from this workspace's geocoded, dated permit evidence; coverage is partial and not a complete inventory.",
            "Acceleration is relative to each cell's own prior window; sparse history can over- or under-state a cell.",
            "Not calibrated to appreciation; this is a research locator, not an expected return.",
        ],
    }


def appreciation(db, cbsa, *, snapshot=None):
    """Appreciation outlook, gated off by default. Ships dark; even enabled it
    withholds any projection until the signal is backtested against realized
    price change (currently insufficient_history on the single-vintage reference).
    `db` is accepted for call symmetry and a future tenant realized-outcome join;
    today the outlook is derived purely from the public snapshot."""
    from app import config
    from app.services.appreciation import appreciation_outlook

    preview = {
        "status": "research_preview",
        "note": ("A metro appreciation projection is withheld until the research "
                 "signal is backtested against realized forward price change; it "
                 "is not served live here."),
    }
    if not getattr(config, "APPRECIATION_OUTLOOK_ENABLED", False):
        return {"status": "disabled", "projection": preview}
    snapshot = snapshot if snapshot is not None else current_snapshot()
    return {**appreciation_outlook(snapshot, cbsa), "projection": preview}


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
    tier, rationale = icp_tier(market) if market["score"] is not None else (None, None)
    return {
        "model_version": MODEL_VERSION, "status": "research" if market["score"] is not None else "insufficient_data", "year": snapshot["year"],
        "captured_at": snapshot["captured_at"], "snapshot_id": snapshot["snapshot_id"],
        "input_mode": "release_reference",
        "cohort_size": len(rows), "market": market,
        "icp_tier": tier, "icp_rationale": rationale,
        "local_evidence": local_evidence(db, cbsa),
        "investment_quality": {"status": "insufficient_data", "missing": [
            "rent_yield", "vacancy", "lease_quality", "capex", "liquidity", "parcel_economics",
            "jobs_and_wages", "verified_anchor_and_entitlement_events"]},
        "provenance": [{"label": "Public records", "captured_at": item["captured_at"],
                        "period": item["period"]} for item in snapshot["provenance"]],
        "frontier": frontier(db, cbsa),
        "appreciation": appreciation(db, cbsa, snapshot=snapshot),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "limitations": [
            "Rank requires complete aligned HPI and unit histories; absent or mismatched geography yields no score, not zero.",
            "Research relative metro rank, not expected return, calibrated confidence or a buy recommendation.",
            "ICP tier (strong/emerging/stable) describes the cohort-relative growth and development profile; it is not a return forecast and does not use population or migration as inputs.",
            "Annual 2025 release reference; newer government releases are not checked by this request. Not real-time or historical known-then data.",
            "Fixed 70% price-momentum / 30% residential-unit-surge research weights; no performance claim for this implementation.",
            "Population and migration are separate observed context, not validated score boosts.",
            "Local source evidence is incomplete, separately dated and does not change the metro score.",
            "Metro home-price research does not establish parcel, multifamily or retail investment returns.",
        ],
    }


# Coverage registry: metros for which a tenant-scoped local evidence source is
# declared. The public ranking spans every eligible metro in the snapshot; this
# flag only marks where local permit evidence can deepen the national signal.
def metro_coverage():
    return frozenset(LOCAL_CONTEXT_SOURCES)


def ranked_markets(*, snapshot=None, query=None, limit=50, offset=0):
    """Nationwide research growth ranking: the full ordered metro cohort the
    model scores, surfaced for discovery. Public snapshot only — no tenant data,
    so the same for every workspace. `has_local_evidence` marks which metros a
    local permit source is declared for (the coverage registry), not a score input."""
    snapshot = snapshot if snapshot is not None else current_snapshot()
    rows = rank_metros(snapshot)  # already sorted by score desc, then cbsa
    covered = metro_coverage()
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    needle = (query or "").strip().lower()

    tier_counts = {tier: 0 for tier in ICP_TIERS}
    markets = []
    for rank, row in enumerate(rows, start=1):
        tier, rationale = icp_tier(row)
        tier_counts[tier] += 1  # distribution over the full cohort, not the page
        if needle and needle not in row["name"].lower() and needle not in row["cbsa"]:
            continue
        markets.append({
            "rank": rank, "cbsa": row["cbsa"], "name": row["name"],
            "score": row["score"],
            "icp_tier": tier, "icp_rationale": rationale,
            "momentum_percentile": row["momentum_percentile"],
            "supply_percentile": row["supply_percentile"],
            "price_momentum_2yr": row["price_momentum_2yr"],
            "supply_surge": row["supply_surge"],
            "population_growth_1yr": row.get("population_growth_1yr"),
            "net_migration_per_1000": row.get("net_migration_per_1000"),
            "has_local_evidence": row["cbsa"] in covered,
        })
    total = len(markets)
    window = markets[offset:offset + limit]
    return {
        "model_version": MODEL_VERSION, "status": "research", "year": snapshot["year"],
        "captured_at": snapshot["captured_at"], "snapshot_id": snapshot["snapshot_id"],
        "input_mode": "release_reference",
        "cohort_size": len(rows), "matched": total, "offset": offset, "limit": limit,
        "local_evidence_metros": len(covered),
        "tier_counts": tier_counts,
        "markets": window,
        "limitations": [
            "Research relative growth ranking across metros with aligned public price and supply history; not an expected return, investment-quality score or buy recommendation.",
            "Rank reflects fixed 70% price-momentum / 30% residential-unit-surge research weights on annual 2025 public data; no performance claim.",
            "ICP tier (strong/emerging/stable) classifies the cohort-relative growth and development profile only; it is not a return forecast, and population/migration are context, not tier inputs.",
            "has_local_evidence marks a declared local permit source for discovery; it never changes the national score.",
        ],
    }
