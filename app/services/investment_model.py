"""Research-only relative metro ranking, never a predicted return or buy score."""
from __future__ import annotations

import math
import re
from collections import Counter
from statistics import mean

MODEL_VERSION = "metro-research-v0.3"
MIN_COHORT = 20


def _number(value, *, positive=False):
    return (type(value) in {int, float} and math.isfinite(value)
            and (not positive or value > 0))


def _percentiles(values):
    # Equal values receive their average rank; source iteration order has no effect.
    counts, ranks, position = Counter(values), {}, 0
    for value in sorted(counts):
        ranks[value] = (position + (counts[value] - 1) / 2) / (len(values) - 1)
        position += counts[value]
    return ranks


def observed_demand(metro):
    before, now = metro.get("population_2024"), metro.get("population_2025")
    migration = metro.get("net_migration_2025")
    growth = now / before - 1 if _number(now, positive=True) and _number(before, positive=True) else None
    rate = migration / now * 1000 if _number(migration) and _number(now, positive=True) else None
    return {"population_growth_1yr": growth if _number(growth) else None,
            "net_migration_per_1000": rate if _number(rate) else None}


def rank_metros(snapshot):
    year = snapshot["year"]
    rows, identities = [], set()
    for metro in snapshot["metros"]:
        cbsa = metro["cbsa"]
        if not re.fullmatch(r"\d{5}", cbsa):
            raise ValueError("Invalid CBSA")
        if cbsa in identities:
            raise ValueError("Duplicate CBSA")
        identities.add(cbsa)
        hpi, units = metro["hpi"], metro["units"]
        base = [units.get(y) for y in range(year - 3, year)]
        if (not _number(hpi.get(year), positive=True)
                or not _number(hpi.get(year - 2), positive=True)
                or not all(_number(v) and v >= 0 for v in base)
                or not _number(units.get(year)) or units[year] < 0
                or mean(base) <= 0):
            continue
        momentum, surge = hpi[year] / hpi[year - 2] - 1, units[year] / mean(base)
        if not _number(momentum) or not _number(surge):
            continue
        rows.append({
            "cbsa": cbsa, "name": metro["name"],
            "price_momentum_2yr": momentum, "supply_surge": surge,
            **observed_demand(metro),
        })
    if len(rows) < MIN_COHORT:
        raise ValueError("Insufficient eligible metro cohort")
    momentum = _percentiles([r["price_momentum_2yr"] for r in rows])
    supply = _percentiles([r["supply_surge"] for r in rows])
    for row in rows:
        row["momentum_percentile"] = momentum[row["price_momentum_2yr"]]
        row["supply_percentile"] = supply[row["supply_surge"]]
        row["score"] = .7 * row["momentum_percentile"] + .3 * row["supply_percentile"]
    return sorted(rows, key=lambda row: (-row["score"], row["cbsa"]))
