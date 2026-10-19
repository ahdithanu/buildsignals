"""Minimal P2.2 evaluation skeleton: JSON-only metric stubs, no UI, no verdict.

Each metric computes a mechanical quantity and records the predeclared threshold.
None of them renders a keep/revise/kill decision - outcome labeling, holdouts,
hit/false-positive rates and go/no-go are later work (P2.2/P2.3). Thresholds are
read, never written back.
"""
from __future__ import annotations

from typing import Any, Mapping

from eval.replay.driver import BaselineRun, ReplayRun


def _threshold(thresholds: Mapping[str, Any], name: str) -> Any:
    entry = thresholds.get(name)
    if isinstance(entry, Mapping):
        return entry.get("value")
    return entry


def signal_frequency(run: ReplayRun, *, thresholds: Mapping[str, Any] | None = None) -> dict:
    """Fraction of known-then cutoffs where the signal fired.

    Reconstructed cutoffs and cutoffs whose data did not exist yet are reported
    separately with counts; they are never folded into the denominator.
    """
    thresholds = thresholds or {}
    reconstructed_excluded = 0
    unavailable_excluded = 0
    eligible = 0
    fired = 0
    for signal in run.signals:
        if signal.status in ("unavailable", "insufficient_history"):
            unavailable_excluded += 1
            continue
        if signal.mode == "reconstructed":
            reconstructed_excluded += 1
            continue
        eligible += 1
        if signal.status == "fired":
            fired += 1
    frequency = (fired / eligible) if eligible else None
    return {
        "fired": fired,
        "eligible_cutoffs": eligible,
        "frequency": frequency,
        "reconstructed_excluded": reconstructed_excluded,
        "unavailable_excluded": unavailable_excluded,
        "threshold": _threshold(thresholds, "signal_frequency"),
    }


def lead_time_vs_trailing_baseline(
    run: ReplayRun, *, baseline: BaselineRun, thresholds: Mapping[str, Any] | None = None,
) -> dict:
    """Signed lead-time delta (days) between the signal and the trailing baseline.

    Positive means the signal fired before the baseline crossed its predeclared
    move. ``unavailable`` when either never fires/crosses in the cutoff range.
    It computes the comparison only; it does not assert the lead time is real or
    significant (that needs P2.2 outcomes and sample sizes).
    """
    thresholds = thresholds or {}
    first_signal = next(
        (
            signal.as_of
            for signal in run.signals
            if signal.status == "fired" and signal.mode == "known_then"
        ),
        None,
    )
    first_baseline = baseline.first_cross()
    if first_signal is None or first_baseline is None:
        return {
            "status": "unavailable",
            "first_signal_cutoff": first_signal.isoformat() if first_signal else None,
            "first_baseline_cutoff": first_baseline.isoformat() if first_baseline else None,
            "lead_time_days": None,
            "comparator": _threshold(thresholds, "lead_time_comparator"),
            "baseline_move": baseline.move,
        }
    lead_time_days = (first_baseline - first_signal).days
    return {
        "status": "calculated",
        "first_signal_cutoff": first_signal.isoformat(),
        "first_baseline_cutoff": first_baseline.isoformat(),
        "lead_time_days": lead_time_days,
        "comparator": _threshold(thresholds, "lead_time_comparator"),
        "baseline_move": baseline.move,
    }


def reproducibility_check(run_a: ReplayRun, run_b: ReplayRun) -> dict:
    """Per-cutoff + overall fingerprint equality between two identical runs."""
    by_cutoff_a = {signal.as_of.isoformat(): signal.fingerprint for signal in run_a.signals}
    by_cutoff_b = {signal.as_of.isoformat(): signal.fingerprint for signal in run_b.signals}
    cutoffs = sorted(set(by_cutoff_a) | set(by_cutoff_b))
    divergent = [
        cutoff for cutoff in cutoffs
        if by_cutoff_a.get(cutoff) != by_cutoff_b.get(cutoff)
    ]
    return {
        "run_fingerprint_match": run_a.run_fingerprint == run_b.run_fingerprint,
        "run_fingerprint": run_a.run_fingerprint,
        "checked_cutoffs": len(cutoffs),
        "divergent_cutoffs": divergent,
    }


def evaluate(
    run: ReplayRun, *, baseline: BaselineRun, thresholds: Mapping[str, Any],
    repro_run: ReplayRun,
) -> dict:
    """Bundle all three metric stubs plus the pinned thresholds into one JSON blob."""
    return {
        "run_id": run.manifest.run_id,
        "run_fingerprint": run.run_fingerprint,
        "method_id": run.manifest.method_id,
        "method_version": run.manifest.method_version,
        "thresholds_id": run.manifest.thresholds_id,
        "signal_frequency": signal_frequency(run, thresholds=thresholds),
        "lead_time_vs_trailing_baseline": lead_time_vs_trailing_baseline(
            run, baseline=baseline, thresholds=thresholds,
        ),
        "reproducibility_check": reproducibility_check(run, repro_run),
    }
