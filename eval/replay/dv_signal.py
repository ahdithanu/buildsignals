"""Bridge the REAL Development Velocity v0 signal into the cutoff-safe replay registry.

This wires ``app.services.development_velocity.develop_velocity`` into the replay
driver by registering a ``SignalFn`` under method id ``development-velocity-v0``.
Importing this module registers the method (same pattern as the reference signal
in ``driver.py``); the driver itself stays domain-neutral.

Cutoff safety and determinism are inherited, not re-implemented: every read goes
through ``develop_velocity`` -> ``activity_baseline`` at ``as_of=T`` only, which
filters strictly on ``first_observed_at``/``recorded_at``/``received_at`` <= ``T``
and chooses the latest interpretation known at ``T`` (so later-dated corrections
cannot change an earlier result). This module reads no wall clock and writes
nothing, honouring the driver's ``_replay_guards``.

The firing threshold is PREDECLARED, never hardcoded here. It is read from the
checked-in, hashed thresholds file and copied into ``series.params`` at build
time (see ``dv_series``), so it is pinned into the manifest's ``thresholds_id``
AND folded into ``run_fingerprint`` via the series params — immutable for the run
and impossible to tune after seeing results (P2.2).

The 0-100 score remains an UNVALIDATED research output: this wiring only replays
the existing signal cutoff-safely; it does not validate or calibrate the score.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.schemas.activity_baseline import ActivityBaselineRequest
from app.schemas.development_velocity import DevelopmentVelocityRequest
from app.services.development_velocity import METHOD_VERSION, develop_velocity
from eval.replay.driver import SignalOutput, register
from eval.replay.manifest import LoadedFixture, SeriesSpec

DV_METHOD_ID = "development-velocity-v0"
# Replay method version == the service's own method version; a run's manifest
# must pin this exact string (get_method rejects anything else).
DV_METHOD_VERSION = METHOD_VERSION

# Key under which the predeclared firing threshold travels, both in the hashed
# thresholds file and in the per-run ``series.params`` copy.
FIRING_THRESHOLD_KEY = "firing_threshold"


def firing_threshold_value(thresholds: Mapping[str, Any]) -> float:
    """Extract the predeclared firing threshold from the loaded thresholds file.

    Accepts either the documented ``{"status": ..., "value": N}`` shape or a bare
    scalar, mirroring ``metrics._threshold``. Raises if it is absent so a run can
    never silently fall back to an un-declared default.
    """
    if FIRING_THRESHOLD_KEY not in thresholds:
        raise KeyError(
            f"Predeclared {FIRING_THRESHOLD_KEY!r} is missing from the thresholds file",
        )
    entry = thresholds[FIRING_THRESHOLD_KEY]
    value = entry.get("value") if isinstance(entry, Mapping) else entry
    if value is None:
        raise ValueError(f"Predeclared {FIRING_THRESHOLD_KEY!r} has no value")
    return float(value)


def dv_series(
    loaded: LoadedFixture,
    *,
    thresholds: Mapping[str, Any],
    baseline_params: Mapping[str, Any],
    minimum_populated_baseline_windows: int = 3,
    seasonal_adjustment: str = "off",
) -> SeriesSpec:
    """Build the frozen ``SeriesSpec`` for a Development Velocity v0 replay.

    The predeclared firing threshold is copied out of ``thresholds`` and into the
    series params *at build time*. ``series.params`` is part of ``SeriesSpec.canonical``
    -> ``ReplayManifest.canonical`` -> ``run_fingerprint``, so the exact threshold
    used by the signal is immutable for the run and reproducible. ``baseline_params``
    carries the baseline cohort kwargs (sources/city/state/attribute/windows/sample
    floor) WITHOUT ``as_of`` — the driver supplies ``as_of=T`` per cutoff.
    """
    params: dict[str, Any] = {
        "baseline": dict(baseline_params),
        "minimum_populated_baseline_windows": minimum_populated_baseline_windows,
        "seasonal_adjustment": seasonal_adjustment,
        FIRING_THRESHOLD_KEY: firing_threshold_value(thresholds),
    }
    return SeriesSpec(
        series_keys=loaded.series_keys,
        methodology_version=loaded.methodology_version,
        params=params,
    )


def development_velocity_signal(
    db: Session, *, as_of: datetime, series: SeriesSpec, method_version: str,
) -> SignalOutput:
    """Replay the real Development Velocity v0 signal as-of ``T``.

    Builds a ``DevelopmentVelocityRequest`` from ``series.params`` with ``as_of=T``,
    calls ``develop_velocity`` once, and maps the top-level status to a replay status:

    - ``calculated`` (score present): ``fired`` when ``score >= firing_threshold``
      else ``no_signal``; ``value`` is the score.
    - ``abstained_insufficient_sample`` -> ``insufficient_history`` (``value`` None).
    - ``bounded_query_exceeded`` -> ``unavailable`` (``value`` None).

    Drivers are the signal's ``cited_driver_observation_ids`` with role ``driver``.
    The firing threshold comes from ``series.params`` (copied from the predeclared,
    hashed thresholds file at build time) — it is never hardcoded here.
    """
    if method_version != DV_METHOD_VERSION:
        raise ValueError(f"Unsupported Development Velocity version: {method_version!r}")

    params = dict(series.params)
    firing_threshold = firing_threshold_value({FIRING_THRESHOLD_KEY: params.get(FIRING_THRESHOLD_KEY)})
    baseline_params = dict(params["baseline"])

    request = DevelopmentVelocityRequest(
        baseline=ActivityBaselineRequest(as_of=as_of, **baseline_params),
        minimum_populated_baseline_windows=int(params.get("minimum_populated_baseline_windows", 3)),
        seasonal_adjustment=params.get("seasonal_adjustment", "off"),
    )
    report = develop_velocity(db, request)

    drivers = [
        {"observation_id": oid, "role": "driver"}
        for oid in report["cited_driver_observation_ids"]
    ]
    status = report["status"]
    score = report["score"]

    if status == "calculated" and score is not None:
        fired = score >= firing_threshold
        return SignalOutput("fired" if fired else "no_signal", score, drivers, method_version)
    if status == "abstained_insufficient_sample":
        return SignalOutput("insufficient_history", None, drivers, method_version)
    if status == "bounded_query_exceeded":
        return SignalOutput("unavailable", None, drivers, method_version)
    # No other top-level status is produced by develop_velocity; treat anything
    # unexpected as undecidable rather than fabricating a decision.
    return SignalOutput("unavailable", None, drivers, method_version)


register(DV_METHOD_ID, [DV_METHOD_VERSION], development_velocity_signal)
