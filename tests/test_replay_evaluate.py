"""Synthetic, offline tests for the P2.2 evaluation-metric machinery.

Every input here is hand-built (``CutoffSignal`` lists, an ``outcomes`` mapping,
and a ``protocol`` dict); nothing runs a replay or touches a database. No test
asserts a ``meets_predeclared_threshold`` verdict -- a pass is never fabricated.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from eval.replay.driver import (
    BaselineCrossing,
    BaselineRun,
    CutoffSignal,
    ReplayRun,
)
from eval.replay.evaluate import (
    by_confidence,
    evaluate_outcomes,
    false_positive_rate,
    hit_rate,
    lead_time_summary,
    subsequent_outcome,
    verdict,
)

UTC = timezone.utc


def _at(day: int) -> datetime:
    return datetime(2026, 1, day, tzinfo=UTC)


def _sig(
    as_of: datetime, status: str, *, mode: str = "known_then", drivers=None,
) -> CutoffSignal:
    return CutoffSignal(
        as_of=as_of, status=status, value=None,
        drivers=list(drivers or []), fingerprint="fp", mode=mode,
    )


# Predeclared protocol: outcome meets at >= 100; minimum 3 fired / 3 evaluable;
# required hit rate 0.7; false-positive tolerance 0.3. (None of these values is
# hardcoded in evaluate.py -- they are read from this dict.)
PROTOCOL = {
    "outcome_threshold": 100,
    "outcome_direction": "gte",
    "min_sample_size": 3,
    "min_hit_rate": 0.7,
    "false_positive_tolerance": 0.3,
}

# A ``ready`` qualify_corpus receipt: the enforced P0.8 precondition. Tests that
# exercise the sample/threshold logic must clear this gate first.
READY_CQ = {
    "verdict": "ready",
    "request_fingerprint": "a" * 64,
    "methodology_version": "corpus-qualification-v1",
}


def _four_fired_three_hits():
    signals = [
        _sig(_at(1), "fired"),
        _sig(_at(2), "fired"),
        _sig(_at(3), "fired"),
        _sig(_at(4), "fired"),
        _sig(_at(5), "no_signal"),
    ]
    outcomes = {
        _at(1): 150,   # hit
        _at(2): 120,   # hit
        _at(3): 100,   # hit (boundary, gte)
        _at(4): 40,    # miss -> false positive
        _at(5): 30,    # non-fired outcome
    }
    return signals, outcomes


def test_hit_rate_and_false_positive_rate_from_known_hits_and_misses():
    signals, outcomes = _four_fired_three_hits()

    hr = hit_rate(signals, outcomes=outcomes, protocol=PROTOCOL)
    assert hr["hits"] == 3
    assert hr["n"] == 4
    assert hr["hit_rate"] == 0.75
    assert hr["fired_without_decidable_outcome"] == 0
    assert hr["interval"]["low"] < 0.75 < hr["interval"]["high"]
    assert hr["outcome"] == {"threshold": 100, "direction": "gte"}

    fpr = false_positive_rate(signals, outcomes=outcomes, protocol=PROTOCOL)
    assert fpr["false_positives"] == 1
    assert fpr["n"] == 4
    assert fpr["false_positive_rate"] == 0.25
    assert fpr["tolerance"] == 0.3
    # The two rates partition the decidable, fired denominator.
    assert hr["hit_rate"] + fpr["false_positive_rate"] == 1.0


def test_excludes_reconstructed_and_nonexistent_data_from_denominators():
    signals = [
        _sig(_at(1), "fired"),
        _sig(_at(2), "fired", mode="reconstructed"),   # excluded: leakage
        _sig(_at(3), "unavailable"),                   # excluded: no data at T
        _sig(_at(4), "insufficient_history"),          # excluded: no data at T
    ]
    outcomes = {_at(1): 150, _at(2): 10, _at(3): 10, _at(4): 10}
    hr = hit_rate(signals, outcomes=outcomes, protocol=PROTOCOL)
    assert hr["n"] == 1
    assert hr["hits"] == 1
    assert hr["reconstructed_excluded"] == 1
    assert hr["status_excluded"] == 2


def test_fired_without_decidable_outcome_is_not_a_miss():
    signals = [_sig(_at(1), "fired"), _sig(_at(2), "fired")]
    outcomes = {_at(1): 150}  # cutoff 2 has no realized outcome yet
    hr = hit_rate(signals, outcomes=outcomes, protocol=PROTOCOL)
    assert hr["n"] == 1
    assert hr["hits"] == 1
    assert hr["fired_without_decidable_outcome"] == 1


def test_subsequent_outcome_mean_and_median_fired_vs_non_fired():
    signals = [
        _sig(_at(1), "fired"),
        _sig(_at(2), "fired"),
        _sig(_at(3), "fired"),
        _sig(_at(4), "no_signal"),
        _sig(_at(5), "no_signal"),
    ]
    outcomes = {_at(1): 10, _at(2): 20, _at(3): 60, _at(4): 1, _at(5): 3}
    out = subsequent_outcome(signals, outcomes=outcomes, protocol=PROTOCOL)
    assert out["fired"] == {"n": 3, "mean": 30.0, "median": 20}
    assert out["non_fired"] == {"n": 2, "mean": 2.0, "median": 2.0}


def test_verdict_insufficient_sample_on_thin_fired_count():
    signals = [_sig(_at(1), "fired"), _sig(_at(2), "fired")]
    outcomes = {_at(1): 150, _at(2): 150}  # only 2 fired, min is 3
    out = verdict(signals, outcomes=outcomes, protocol=PROTOCOL, corpus_qualification=READY_CQ)
    assert out["verdict"] == "insufficient_sample"
    assert out["fired_n"] == 2
    assert out["min_fired_signals"] == 3


def test_verdict_insufficient_sample_when_minimums_not_predeclared():
    signals, outcomes = _four_fired_three_hits()
    protocol = {"outcome_threshold": 100, "outcome_direction": "gte"}  # no minimums
    out = verdict(signals, outcomes=outcomes, protocol=protocol, corpus_qualification=READY_CQ)
    assert out["verdict"] == "insufficient_sample"
    assert "minimums" in out["reason"]


def test_verdict_inconclusive_when_sample_ok_but_below_tolerance():
    # Adequate sample, but hit rate (0.5) is clearly below the required 0.9.
    signals = [
        _sig(_at(1), "fired"),
        _sig(_at(2), "fired"),
        _sig(_at(3), "fired"),
        _sig(_at(4), "fired"),
    ]
    outcomes = {_at(1): 150, _at(2): 150, _at(3): 10, _at(4): 10}
    protocol = {
        "outcome_threshold": 100,
        "outcome_direction": "gte",
        "min_sample_size": 3,
        "min_hit_rate": 0.9,
        "false_positive_tolerance": 0.1,
    }
    out = verdict(signals, outcomes=outcomes, protocol=protocol, corpus_qualification=READY_CQ)
    assert out["verdict"] == "inconclusive"
    assert out["verdict"] != "meets_predeclared_threshold"
    assert out["fired_n"] == 4
    assert out["hit_rate"]["hit_rate"] == 0.5


def test_by_confidence_unavailable_without_confidence():
    signals = [_sig(_at(1), "fired"), _sig(_at(2), "fired")]
    outcomes = {_at(1): 150, _at(2): 10}
    out = by_confidence(signals, outcomes=outcomes, protocol=PROTOCOL)
    assert out["status"] == "unavailable"
    assert out["n"] == 0


def test_by_confidence_groups_when_drivers_carry_confidence():
    signals = [
        _sig(_at(1), "fired", drivers=[{"observation_id": "a", "confidence": 0.9}]),
        _sig(_at(2), "fired", drivers=[{"observation_id": "b", "confidence": 0.6}]),
        _sig(_at(3), "fired", drivers=[{"observation_id": "c", "confidence": 0.4}]),
    ]
    outcomes = {_at(1): 150, _at(2): 150, _at(3): 10}
    out = by_confidence(signals, outcomes=outcomes, protocol=PROTOCOL)
    assert out["status"] == "calculated"
    assert out["n"] == 3
    assert out["confidence_buckets"] == [0.5, 0.8]
    # Default edges (0.5, 0.8) -> three buckets; one signal in each.
    assert [bucket["n"] for bucket in out["buckets"]] == [1, 1, 1]
    assert [bucket["label"] for bucket in out["buckets"]] == ["<0.5", ">=0.5,<0.8", ">=0.8"]


def _run(signals) -> ReplayRun:
    # manifest is unused by lead_time; a lightweight stand-in keeps this offline.
    return ReplayRun(manifest=None, signals=tuple(signals), run_fingerprint="rfp")


def test_lead_time_summary_wraps_existing_metric():
    signals = [_sig(_at(5), "no_signal"), _sig(_at(10), "fired"), _sig(_at(20), "fired")]
    run = _run(signals)
    baseline = BaselineRun(
        crossings=(
            BaselineCrossing(as_of=_at(10), crossed=False),
            BaselineCrossing(as_of=_at(20), crossed=True),
        ),
        move=2.0,
    )
    out = lead_time_summary(run, baseline=baseline, protocol=PROTOCOL)
    assert out["fired_known_then_cutoffs"] == 2
    inner = out["lead_time_vs_trailing_baseline"]
    assert inner["status"] == "calculated"
    assert inner["lead_time_days"] == 10  # baseline crosses day 20, signal fires day 10


def test_metrics_are_deterministic():
    signals, outcomes = _four_fired_three_hits()

    def render():
        return json.dumps(
            {
                "hit_rate": hit_rate(signals, outcomes=outcomes, protocol=PROTOCOL),
                "false_positive_rate": false_positive_rate(
                    signals, outcomes=outcomes, protocol=PROTOCOL,
                ),
                "subsequent_outcome": subsequent_outcome(
                    signals, outcomes=outcomes, protocol=PROTOCOL,
                ),
                "verdict": verdict(
                    signals, outcomes=outcomes, protocol=PROTOCOL,
                    corpus_qualification=READY_CQ,
                ),
            },
            sort_keys=True,
        )

    assert render() == render()


def test_evaluate_outcomes_bundle_is_deterministic_and_json_safe():
    signals, outcomes = _four_fired_three_hits()

    class _M:  # minimal manifest stand-in for the bundle's provenance fields
        run_id = "rid"
        method_id = "m"
        method_version = "v"
        thresholds_id = "tid"

    run = ReplayRun(manifest=_M(), signals=tuple(signals), run_fingerprint="rfp")
    first = evaluate_outcomes(run, outcomes=outcomes, protocol=PROTOCOL, corpus_qualification=READY_CQ)
    second = evaluate_outcomes(run, outcomes=outcomes, protocol=PROTOCOL, corpus_qualification=READY_CQ)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["verdict"]["verdict"] in (
        "insufficient_sample", "inconclusive", "meets_predeclared_threshold",
    )
    # 4 fired, but default protocol has no lead-time baseline passed here.
    assert "lead_time_summary" not in first


def test_verdict_corpus_not_qualified_without_receipt():
    # Adequate sample, clearing thresholds -- but no corpus qualification at all.
    signals, outcomes = _four_fired_three_hits()
    out = verdict(signals, outcomes=outcomes, protocol=PROTOCOL)
    assert out["verdict"] == "corpus_not_qualified"
    assert out["corpus_qualification"] is None
    assert "P0.8" in out["reason"]


def test_verdict_corpus_not_qualified_when_receipt_not_ready():
    signals, outcomes = _four_fired_three_hits()
    not_ready = {"verdict": "insufficient_depth", "request_fingerprint": "b" * 64}
    out = verdict(signals, outcomes=outcomes, protocol=PROTOCOL, corpus_qualification=not_ready)
    assert out["verdict"] == "corpus_not_qualified"
    assert out["corpus_qualification"]["verdict"] == "insufficient_depth"


def test_verdict_corpus_fingerprint_must_match_predeclared():
    signals, outcomes = _four_fired_three_hits()
    protocol = {
        **PROTOCOL,
        "preconditions": {
            "qualified_historical_corpus_P0_8": {"required_request_fingerprint": "c" * 64},
        },
    }
    # READY_CQ's fingerprint ("a"*64) does not match the predeclared ("c"*64).
    out = verdict(signals, outcomes=outcomes, protocol=protocol, corpus_qualification=READY_CQ)
    assert out["verdict"] == "corpus_not_qualified"
    assert "does not match" in out["reason"]
    # The matching receipt clears the gate (and then the sample/threshold logic runs).
    matching = {**READY_CQ, "request_fingerprint": "c" * 64}
    cleared = verdict(signals, outcomes=outcomes, protocol=protocol, corpus_qualification=matching)
    assert cleared["verdict"] != "corpus_not_qualified"
    assert cleared["corpus_qualification"]["fingerprint_bound"] is True


def test_verdict_non_mapping_receipt_fails_safe_to_hold():
    # A malformed (non-Mapping) receipt must HOLD, not raise.
    signals, outcomes = _four_fired_three_hits()
    out = verdict(signals, outcomes=outcomes, protocol=PROTOCOL, corpus_qualification="ready")
    assert out["verdict"] == "corpus_not_qualified"
    assert out["corpus_qualification"] is None


def test_verdict_tolerates_malformed_preconditions():
    # preconditions=None must not crash; a ready receipt (no binding) still clears.
    signals, outcomes = _four_fired_three_hits()
    protocol = {**PROTOCOL, "preconditions": None}
    out = verdict(signals, outcomes=outcomes, protocol=protocol, corpus_qualification=READY_CQ)
    assert out["verdict"] != "corpus_not_qualified"
    assert out["corpus_qualification"]["fingerprint_bound"] is False
