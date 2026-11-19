"""Appreciation outlook — the LAST and most gated layer of the investment-area
track. A metro's research rank (momentum/supply percentiles, ICP tier) is a
RELATIVE growth signal; turning it into an appreciation projection requires proof
that the signal actually predicted realized forward price change OUT OF SAMPLE.

This module is that proof gate, not a forecast generator:
  * `backtest()` measures, from a panel of (as-of signal, realized forward
    return, horizon) observations, whether the signal has demonstrated skill
    (rank correlation + top/bottom tercile lift) at each horizon. Pure.
  * `appreciation_outlook()` derives those observations from a snapshot and only
    ever returns a projection once the panel clears the skill bar.

The packaged 2025 reference holds a single HPI vintage pair per metro (2023 &
2025) — that pair IS the momentum signal, so there is no disjoint forward window
to backtest. The outlook is therefore `insufficient_history` and NO appreciation
number is produced. Emitting a figure before the gate clears would be a predicted
return, which this product never makes. The layer is additionally gated OFF by
default (APPRECIATION_OUTLOOK_ENABLED) so it stays dark until real multi-vintage
history is packaged.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from statistics import mean

MODEL_VERSION = "appreciation-backtest-v0.1"

# Gate thresholds. A horizon is "calibrated" only with enough out-of-sample
# observations AND a positive rank correlation that clears noise. Deliberately
# conservative — a floor for showing ANY projection, never a performance claim.
MIN_OBSERVATIONS_PER_HORIZON = 30
MIN_HORIZONS = 1
MIN_RANK_CORRELATION = 0.2


def _number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _ranks(values):
    # Average rank for ties; source order has no effect.
    counts, ranks, position = Counter(values), {}, 0
    for value in sorted(counts):
        ranks[value] = position + (counts[value] + 1) / 2
        position += counts[value]
    return [ranks[v] for v in values]


def rank_correlation(pairs):
    """Spearman rank correlation of (x, y) pairs. None when undefined (fewer than
    two points, or no variation on either axis). Pure."""
    pairs = [(x, y) for x, y in pairs if _number(x) and _number(y)]
    if len(pairs) < 2:
        return None
    xr, yr = _ranks([x for x, _ in pairs]), _ranks([y for _, y in pairs])
    mx, my = mean(xr), mean(yr)
    sxx = sum((r - mx) ** 2 for r in xr)
    syy = sum((r - my) ** 2 for r in yr)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((a - mx) * (b - my) for a, b in zip(xr, yr))
    return sxy / math.sqrt(sxx * syy)


def _tercile_lift(obs):
    """Mean realized return of the top signal third minus the bottom third.
    None when there are too few observations to split."""
    if len(obs) < 3:
        return None
    ordered = sorted(obs, key=lambda o: o["signal"])
    k = len(ordered) // 3
    if k == 0:
        return None
    bottom = mean(o["realized_return"] for o in ordered[:k])
    top = mean(o["realized_return"] for o in ordered[-k:])
    return top - bottom


def backtest(observations, *, min_observations=MIN_OBSERVATIONS_PER_HORIZON,
             min_horizons=MIN_HORIZONS, min_rank_correlation=MIN_RANK_CORRELATION):
    """Measure out-of-sample signal skill from (signal, realized_return,
    horizon_years) observations, grouped by horizon. Pure: no DB, no clock.
    `status` is 'calibrated' only when at least `min_horizons` horizons each have
    enough observations and a rank correlation clearing `min_rank_correlation`."""
    groups = defaultdict(list)
    for obs in observations:
        horizon = obs.get("horizon_years")
        if (isinstance(horizon, int) and horizon >= 1
                and _number(obs.get("signal")) and _number(obs.get("realized_return"))):
            groups[horizon].append({"signal": obs["signal"],
                                    "realized_return": obs["realized_return"]})
    horizons = []
    for horizon in sorted(groups):
        obs = groups[horizon]
        corr = rank_correlation([(o["signal"], o["realized_return"]) for o in obs])
        lift = _tercile_lift(obs)
        calibrated = (len(obs) >= min_observations and corr is not None
                      and corr >= min_rank_correlation)
        horizons.append({
            "horizon_years": horizon, "observations": len(obs),
            "rank_correlation": round(corr, 3) if corr is not None else None,
            "tercile_lift": round(lift, 4) if lift is not None else None,
            "calibrated": calibrated,
        })
    calibrated_horizons = [h for h in horizons if h["calibrated"]]
    status = "calibrated" if len(calibrated_horizons) >= min_horizons else "insufficient_history"
    return {
        "model_version": MODEL_VERSION, "status": status, "horizons": horizons,
        "observation_count": sum(h["observations"] for h in horizons),
        "min_observations_per_horizon": min_observations,
        "min_rank_correlation": min_rank_correlation,
    }


def observations_from_snapshot(snapshot):
    """Out-of-sample (signal as-of t1, realized return over the disjoint [t1, t2])
    observations derivable from a snapshot's HPI vintages. For vintages
    t0 < t1 < t2, the signal is the momentum known at t1 (hpi[t1]/hpi[t0]-1) and
    the realized return is the strictly-later window (hpi[t2]/hpi[t1]-1), so the
    two windows never overlap. The packaged 2025 reference holds a single pair
    (2023 & 2025) per metro, which yields NO observations; this becomes nonempty
    only when multi-vintage HPI history is packaged. Pure."""
    observations = []
    for metro in snapshot.get("metros", []):
        hpi = metro.get("hpi", {})
        vintages = sorted(y for y in hpi
                          if isinstance(y, int) and _number(hpi.get(y)) and hpi[y] > 0)
        for i in range(len(vintages) - 2):
            t0, t1, t2 = vintages[i], vintages[i + 1], vintages[i + 2]
            signal = hpi[t1] / hpi[t0] - 1          # momentum known AS OF t1
            realized = hpi[t2] / hpi[t1] - 1        # strictly-later, disjoint window
            if _number(signal) and _number(realized):
                observations.append({"signal": signal, "realized_return": realized,
                                     "horizon_years": t2 - t1})
    return observations


_REQUIRED = (
    "An appreciation projection is shown only after the metro signal demonstrates "
    "out-of-sample skill against realized forward price change. The packaged "
    "reference holds a single HPI vintage pair (the momentum signal itself), so "
    "there is no disjoint forward window to backtest; multi-vintage HPI history is "
    "required before any projection can be produced."
)
_LIMITATIONS = (
    "Appreciation is the last and most gated layer: a projection is withheld until a backtest clears the skill bar.",
    "Research relative-growth signal, not an expected return; metro home-price research does not establish parcel or retail returns.",
    "The backtest needs multiple HPI vintages per metro to form disjoint signal and realized-return windows; the 2025 reference has one pair.",
    "A calibrated outlook would present the realized forward-return distribution for a signal band, never a single predicted return.",
)


def appreciation_outlook(snapshot, cbsa):
    """Research appreciation outlook for a metro. Returns a projection ONLY once
    the signal is backtested as skillful; otherwise reports insufficient_history
    with exactly what is missing. Never emits a naked forecast. Pure (snapshot
    only — no tenant data, no clock)."""
    report = backtest(observations_from_snapshot(snapshot))
    if report["status"] != "calibrated":
        return {"status": "insufficient_history", "model_version": MODEL_VERSION,
                "cbsa": cbsa, "calibration": report, "required": _REQUIRED,
                "limitations": list(_LIMITATIONS)}
    # Calibrated path (not reachable with the current single-vintage reference):
    # the gate has cleared, but turning calibration into a per-metro outlook is a
    # later step, so this still withholds a point forecast.
    return {"status": "research", "model_version": MODEL_VERSION, "cbsa": cbsa,
            "calibration": report,
            "note": ("Signal is backtested; a calibrated outlook presents the "
                     "realized forward-return distribution for this signal band, "
                     "not a single predicted return."),
            "limitations": list(_LIMITATIONS)}
