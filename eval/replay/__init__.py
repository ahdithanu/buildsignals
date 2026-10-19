"""Cutoff-safe replay / backtest scaffold (offline, deterministic, reproducible).

See ``docs/signals/2026-10-18-replay-backtest-scaffold-design.md``. Replay runs
only against isolated local fixtures or an explicitly approved local snapshot;
it authorizes no deployment, no worker, and no production data access.
"""
from __future__ import annotations

from eval.replay.driver import (
    REFERENCE_METHOD_ID,
    REFERENCE_METHOD_VERSION,
    REGISTRY,
    BaselineRun,
    CutoffSignal,
    ReplayRun,
    SignalFn,
    SignalOutput,
    baseline_run,
    get_method,
    register,
    replay,
)

# Importing the bridge registers the REAL Development Velocity v0 signal
# (method id ``development-velocity-v0``) with the driver registry.
from eval.replay.dv_signal import (
    DV_METHOD_ID,
    DV_METHOD_VERSION,
    development_velocity_signal,
    dv_series,
    firing_threshold_value,
)
from eval.replay.manifest import (
    APPROVED_DATA_SCOPES,
    FIXTURES,
    LoadedFixture,
    ReplayManifest,
    SeriesSpec,
    freeze,
    load_fixture,
    load_rows,
    load_thresholds,
    series_key_for,
    verify,
)
from eval.replay.metrics import (
    evaluate,
    lead_time_vs_trailing_baseline,
    reproducibility_check,
    signal_frequency,
)

__all__ = [
    "APPROVED_DATA_SCOPES",
    "DV_METHOD_ID",
    "DV_METHOD_VERSION",
    "FIXTURES",
    "BaselineRun",
    "CutoffSignal",
    "LoadedFixture",
    "REFERENCE_METHOD_ID",
    "REFERENCE_METHOD_VERSION",
    "REGISTRY",
    "development_velocity_signal",
    "dv_series",
    "firing_threshold_value",
    "ReplayManifest",
    "ReplayRun",
    "SeriesSpec",
    "SignalFn",
    "SignalOutput",
    "baseline_run",
    "evaluate",
    "freeze",
    "get_method",
    "lead_time_vs_trailing_baseline",
    "load_fixture",
    "load_rows",
    "load_thresholds",
    "register",
    "replay",
    "reproducibility_check",
    "series_key_for",
    "signal_frequency",
    "verify",
]
