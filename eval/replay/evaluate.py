"""P2.2 evaluation-metric machinery for the cutoff-safe replay harness.

The metric helpers are pure, offline, deterministic functions. They take an existing replay
result (a :class:`~eval.replay.driver.ReplayRun`, or its ``CutoffSignal`` list),
an ``outcomes`` mapping that the *caller* has already computed from post-cutoff
data (cutoff/``as_of`` -> realized outcome value), and a ``protocol`` dict of the
*predeclared* values. Explicit P0.8 verdicts additionally require a read-only DB
session to verify snapshot-bound qualification and recompute the frozen replay.
No helper hardcodes a statistical threshold or an outcome definition
-- every tolerance, minimum, and outcome rule is read from the passed
``protocol``, exactly like ``metrics.py`` reads its thresholds and never writes
them back.

The output of every function is a JSON-serializable dict that always carries the
sample size(s) it was computed from, and (for rates) a simple Wilson interval, so
a thin sample can never be read as a confident result. ``verdict`` returns
``insufficient_sample`` whenever the fired count or the evaluable-period count is
below the predeclared minimums -- it never claims validation on thin data, and it
never declares ``meets_predeclared_threshold`` unless the protocol predeclared
the minimums and the acceptance thresholds that decision rests on. Before any of
that, ``verdict`` returns ``corpus_not_qualified`` unless the caller supplies a
producer/verifier receipt bound to the actual replay evidence. Legacy
request-only receipts cannot clear this gate, even with ``ready``.
Generic metric protocols without the explicit P0.8 precondition remain usable.
"""
from __future__ import annotations

import hmac
import json
import math
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy.orm import Session

from eval.replay.driver import BaselineRun, CutoffSignal, ReplayRun
from eval.replay.manifest import utc
from eval.replay.metrics import lead_time_vs_trailing_baseline

# 95% two-sided normal quantile, pinned so the Wilson interval is reproducible.
_Z_95 = 1.959963984540054
_DECIDABLE_STATUSES = ("fired", "no_signal")
_EXCLUDED_STATUSES = ("unavailable", "insufficient_history")


# ── protocol / outcome helpers ──────────────────────────────────────────────

def load_protocol(source: str | Path | Mapping[str, Any]) -> dict:
    """Load the predeclared evaluation protocol into the flat shape these metrics read.

    The predeclared file (``fixtures/dv_v0_evaluation_protocol.json``) nests the
    sample minimums under ``min_sample_size.value`` for human readability and
    hashing; this exposes ``min_fired_signals`` / ``min_evaluable_periods`` at the
    top level (where ``verdict`` reads them) without mutating or re-tuning any
    predeclared value. The original keys are preserved for provenance.
    """
    data = dict(json.loads(Path(source).read_text()) if isinstance(source, (str, Path)) else source)
    sample = data.get("min_sample_size")
    inner = sample.get("value") if isinstance(sample, Mapping) else None
    if isinstance(inner, Mapping):
        data.setdefault("min_fired_signals", inner.get("min_fired_signals"))
        data.setdefault("min_evaluable_periods", inner.get("min_evaluable_periods"))
    return data


def _value(protocol: Mapping[str, Any], name: str) -> Any:
    """Read a predeclared value, unwrapping the ``{"value": ...}`` form.

    Matches ``metrics._threshold`` so a protocol can reuse the thresholds-file
    shape (``{"status": "...", "value": X}``) or a plain scalar interchangeably.
    """
    entry = protocol.get(name)
    if isinstance(entry, Mapping):
        return entry.get("value")
    return entry


def _outcome_spec(protocol: Mapping[str, Any]) -> tuple[Any, str]:
    """The predeclared outcome: a threshold and a comparator direction.

    Accepts either a nested ``outcome`` / ``outcome_definition`` mapping with
    ``threshold`` + ``direction`` keys, or flat ``outcome_threshold`` /
    ``outcome_direction`` keys. Direction defaults to ``"gte"``. A ``None``
    threshold means the outcome was not predeclared, so no outcome is decidable.
    """
    nested = protocol.get("outcome")
    if not isinstance(nested, Mapping):
        nested = protocol.get("outcome_definition")
    if isinstance(nested, Mapping):
        threshold = nested.get("threshold", nested.get("value"))
        direction = nested.get("direction", "gte")
        # Structured method-specific outcome rules are not scalar thresholds.
        # Until the cutoff-safe extractor exists, mark them undecidable instead
        # of comparing an observed number/bool with a rule dictionary.
        if isinstance(threshold, Mapping):
            threshold = None
    else:
        threshold = _value(protocol, "outcome_threshold")
        direction = _value(protocol, "outcome_direction") or "gte"
    return threshold, str(direction)


def _outcome_met(value: Any, threshold: Any, direction: str) -> bool | None:
    """Did a realized outcome meet the predeclared outcome? ``None`` if undecidable."""
    if value is None or threshold is None:
        return None
    if direction in ("gte", ">="):
        return value >= threshold
    if direction in ("gt", ">"):
        return value > threshold
    if direction in ("lte", "<="):
        return value <= threshold
    if direction in ("lt", "<"):
        return value < threshold
    if direction in ("eq", "=="):
        return value == threshold
    raise ValueError(f"Unknown outcome direction: {direction!r}")


def _wilson(successes: int, n: int, *, z: float = _Z_95) -> dict | None:
    """95% Wilson score interval for a binomial proportion; ``None`` for n == 0."""
    if n <= 0:
        return None
    phat = successes / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = (z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)) / denom
    return {
        "method": "wilson",
        "confidence": 0.95,
        "low": max(0.0, center - margin),
        "high": min(1.0, center + margin),
    }


# ── signal / outcome alignment ──────────────────────────────────────────────

def _signals(run: ReplayRun | Sequence[CutoffSignal]) -> tuple[CutoffSignal, ...]:
    if isinstance(run, ReplayRun):
        return run.signals
    return tuple(run)


def _norm_key(key: Any) -> str:
    if isinstance(key, datetime):
        return utc(key).isoformat()
    if isinstance(key, str):
        try:
            return utc(datetime.fromisoformat(key)).isoformat()
        except ValueError:
            return key
    return str(key)


def _normalize_outcomes(outcomes: Mapping[Any, Any]) -> dict[str, Any]:
    return {_norm_key(key): value for key, value in outcomes.items()}


def _confidence(signal: CutoffSignal) -> float | None:
    """Confidence attached to a signal, or the max over its cited drivers."""
    direct = getattr(signal, "confidence", None)
    if direct is not None:
        return float(direct)
    values = [
        float(driver["confidence"])
        for driver in signal.drivers
        if isinstance(driver, Mapping) and driver.get("confidence") is not None
    ]
    return max(values) if values else None


class _Record:
    """A single known-then cutoff aligned with its realized outcome."""

    __slots__ = ("signal", "fired", "present", "value", "met", "confidence")

    def __init__(
        self, signal: CutoffSignal, *, present: bool, value: Any,
        met: bool | None,
    ) -> None:
        self.signal = signal
        self.fired = signal.status == "fired"
        self.present = present
        self.value = value
        self.met = met
        self.confidence = _confidence(signal)


def _partition(
    signals: Iterable[CutoffSignal], norm_outcomes: Mapping[str, Any],
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    """Split signals into decidable known-then records plus exclusion counts.

    ``reconstructed`` cutoffs and cutoffs whose data did not exist at T are
    counted and set aside -- never folded into any denominator (same rule the
    frequency metric applies).
    """
    threshold, direction = _outcome_spec(protocol)
    records: list[_Record] = []
    reconstructed_excluded = 0
    status_excluded = 0
    for signal in signals:
        if signal.status in _EXCLUDED_STATUSES:
            status_excluded += 1
            continue
        if signal.mode == "reconstructed":
            reconstructed_excluded += 1
            continue
        if signal.status not in _DECIDABLE_STATUSES:
            status_excluded += 1
            continue
        key = _norm_key(signal.as_of)
        present = key in norm_outcomes and norm_outcomes[key] is not None
        value = norm_outcomes.get(key) if present else None
        met = _outcome_met(value, threshold, direction) if present else None
        records.append(_Record(signal, present=present, value=value, met=met))
    return {
        "records": records,
        "reconstructed_excluded": reconstructed_excluded,
        "status_excluded": status_excluded,
        "outcome_threshold": threshold,
        "outcome_direction": direction,
    }


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ── metrics ─────────────────────────────────────────────────────────────────

def hit_rate(
    run: ReplayRun | Sequence[CutoffSignal], *, outcomes: Mapping[Any, Any],
    protocol: Mapping[str, Any],
) -> dict:
    """Fraction of fired signals whose realized outcome met the predeclared outcome.

    Denominator is the fired, known-then cutoffs for which the outcome is
    *decidable* (both the realized value and the predeclared outcome are present).
    Fired cutoffs without a decidable outcome are reported separately, never
    counted as misses.
    """
    part = _partition(_signals(run), _normalize_outcomes(outcomes), protocol)
    fired = [rec for rec in part["records"] if rec.fired and rec.met is not None]
    fired_without_outcome = sum(
        1 for rec in part["records"] if rec.fired and rec.met is None
    )
    hits = sum(1 for rec in fired if rec.met)
    n = len(fired)
    return {
        "hits": hits,
        "n": n,
        "hit_rate": (hits / n) if n else None,
        "interval": _wilson(hits, n),
        "fired_without_decidable_outcome": fired_without_outcome,
        "reconstructed_excluded": part["reconstructed_excluded"],
        "status_excluded": part["status_excluded"],
        "outcome": {
            "threshold": part["outcome_threshold"],
            "direction": part["outcome_direction"],
        },
    }


def false_positive_rate(
    run: ReplayRun | Sequence[CutoffSignal], *, outcomes: Mapping[Any, Any],
    protocol: Mapping[str, Any],
) -> dict:
    """Fraction of fired signals whose realized outcome did NOT meet the outcome.

    Same decidable, fired, known-then denominator as ``hit_rate``; the two rates
    sum to 1 over that denominator.
    """
    part = _partition(_signals(run), _normalize_outcomes(outcomes), protocol)
    fired = [rec for rec in part["records"] if rec.fired and rec.met is not None]
    false_positives = sum(1 for rec in fired if not rec.met)
    n = len(fired)
    return {
        "false_positives": false_positives,
        "n": n,
        "false_positive_rate": (false_positives / n) if n else None,
        "interval": _wilson(false_positives, n),
        "tolerance": _value(protocol, "false_positive_tolerance"),
    }


def _summary(values: Sequence[float]) -> dict:
    nums = [value for value in values if _numeric(value)]
    return {
        "n": len(nums),
        "mean": (sum(nums) / len(nums)) if nums else None,
        "median": statistics.median(nums) if nums else None,
    }


def subsequent_outcome(
    run: ReplayRun | Sequence[CutoffSignal], *, outcomes: Mapping[Any, Any],
    protocol: Mapping[str, Any],
) -> dict:
    """Mean and median realized outcome after fired vs non-fired known-then cutoffs."""
    part = _partition(_signals(run), _normalize_outcomes(outcomes), protocol)
    fired_values = [rec.value for rec in part["records"] if rec.fired and rec.present]
    non_fired_values = [
        rec.value for rec in part["records"] if not rec.fired and rec.present
    ]
    return {
        "fired": _summary(fired_values),
        "non_fired": _summary(non_fired_values),
    }


def lead_time_summary(
    run: ReplayRun, *, baseline: BaselineRun, protocol: Mapping[str, Any] | None = None,
) -> dict:
    """Wrap the existing lead-time-vs-trailing-baseline metric with its sample size."""
    protocol = protocol or {}
    inner = lead_time_vs_trailing_baseline(run, baseline=baseline, thresholds=protocol)
    fired_known_then = sum(
        1 for signal in run.signals
        if signal.status == "fired" and signal.mode == "known_then"
    )
    return {
        "lead_time_vs_trailing_baseline": inner,
        "fired_known_then_cutoffs": fired_known_then,
        "comparator": inner.get("comparator"),
    }


def _bucket_edges(protocol: Mapping[str, Any]) -> tuple[float, ...]:
    edges = _value(protocol, "confidence_buckets")
    if edges is None:
        edges = (0.5, 0.8)
    return tuple(float(edge) for edge in edges)


def _bucket_index(edges: Sequence[float], value: float) -> int:
    return sum(1 for edge in edges if value >= edge)


def _bucket_label(edges: Sequence[float], index: int) -> str:
    if index == 0:
        return f"<{edges[0]}"
    if index == len(edges):
        return f">={edges[-1]}"
    return f">={edges[index - 1]},<{edges[index]}"


def by_confidence(
    run: ReplayRun | Sequence[CutoffSignal], *, outcomes: Mapping[Any, Any],
    protocol: Mapping[str, Any],
) -> dict:
    """Hit rate of fired signals grouped by their confidence, when available.

    Confidence is read from a signal-level ``confidence`` attribute or the max
    over cited drivers. ``CutoffSignal`` carries none by default, so this reports
    ``status: "unavailable"`` unless the signals (or their drivers) actually
    expose confidence. Buckets are a descriptive grouping, not a pass/fail gate;
    their edges come from the protocol (default splits at 0.5 and 0.8).
    """
    part = _partition(_signals(run), _normalize_outcomes(outcomes), protocol)
    fired = [
        rec for rec in part["records"]
        if rec.fired and rec.met is not None and rec.confidence is not None
    ]
    if not fired:
        return {
            "status": "unavailable",
            "reason": "no confidence available on fired signals or their drivers",
            "n": 0,
        }
    edges = _bucket_edges(protocol)
    counts = [[0, 0] for _ in range(len(edges) + 1)]  # [hits, n] per bucket
    for rec in fired:
        index = _bucket_index(edges, rec.confidence)
        counts[index][1] += 1
        if rec.met:
            counts[index][0] += 1
    buckets = [
        {
            "label": _bucket_label(edges, index),
            "hits": hits,
            "n": n,
            "hit_rate": (hits / n) if n else None,
            "interval": _wilson(hits, n),
        }
        for index, (hits, n) in enumerate(counts)
    ]
    return {
        "status": "calculated",
        "confidence_buckets": list(edges),
        "n": len(fired),
        "buckets": buckets,
    }


# ── verdict ─────────────────────────────────────────────────────────────────

def _corpus_precondition(
    corpus_qualification: Mapping[str, Any] | None, protocol: Mapping[str, Any],
) -> dict:
    """Enforce the roadmap P0.8 precondition: a qualified corpus must exist.

    The caller passes the dict returned by ``qualify_corpus``. The precondition is
    gated only for protocols explicitly declaring P0.8. A ``ready`` receipt
    alone never establishes that the replay snapshot is qualified. When the protocol
    predeclares a required corpus ``request_fingerprint``, it must match (constant
    time), but this request-only identity remains insufficient. Current receipts
    cannot clear this legacy path; the evaluator uses the separate read-only
    binding verifier for supported receipts. Absent or not-ready keeps the evaluation at a ``corpus_not_qualified``
    HOLD -- no validation verdict is reachable without a qualified corpus. Never
    raises; a bad receipt fails safe to HOLD.
    """
    # Read the (optional) predeclared fingerprint binding defensively: a missing or
    # malformed preconditions block means "no binding declared", never a crash.
    prec = protocol.get("preconditions") if isinstance(protocol, Mapping) else None
    prec = prec if isinstance(prec, Mapping) else {}
    if "qualified_historical_corpus_P0_8" not in prec:
        return {"qualified": True, "echo": None,
                "reason": "generic metric protocol does not declare the P0.8 precondition"}
    corpus_pre = prec.get("qualified_historical_corpus_P0_8")
    corpus_pre = corpus_pre if isinstance(corpus_pre, Mapping) else {}
    required = corpus_pre.get("required_request_fingerprint")

    if corpus_qualification is None:
        return {"qualified": False, "echo": None,
                "reason": "P0.8 precondition: no corpus_qualification supplied (corpus not qualified)"}
    if not isinstance(corpus_qualification, Mapping):
        return {"qualified": False, "echo": None,
                "reason": "P0.8 precondition: corpus_qualification is not a mapping (corpus not qualified)"}
    cq_verdict = corpus_qualification.get("verdict")
    cq_fingerprint = corpus_qualification.get("request_fingerprint")
    echo = {
        "verdict": cq_verdict,
        "request_fingerprint": cq_fingerprint,
        "methodology_version": corpus_qualification.get("methodology_version"),
        "fingerprint_bound": required is not None,
    }
    if cq_verdict != "ready":
        return {"qualified": False, "echo": echo,
                "reason": f"P0.8 precondition: corpus qualification verdict is {cq_verdict!r}, not 'ready'"}
    if required is not None and not (
        isinstance(cq_fingerprint, str) and hmac.compare_digest(str(required), cq_fingerprint)
    ):
        return {"qualified": False, "echo": echo,
                "reason": "P0.8 precondition: corpus request_fingerprint does not match the protocol's predeclared corpus"}
    # The current producer signs request parameters only. It supplies no frozen
    # snapshot/evidence digest, source-method pins or replay identity, so even a
    # matching request fingerprint cannot establish that THIS replay uses the
    # independently audited data or the predeclared floors. Do not introduce a
    # caller-asserted binding object that would merely move the same bypass.
    # This legacy receipt cannot clear; verdict handles the supported binding separately.
    return {"qualified": False, "echo": echo,
            "reason": "P0.8 precondition: corpus receipt has no verified binding to the replay snapshot, source methodology and protocol floors"}


def verdict(
    run: ReplayRun | Sequence[CutoffSignal], *, outcomes: Mapping[Any, Any],
    protocol: Mapping[str, Any], corpus_qualification: Mapping[str, Any] | None = None,
    db: Session | None = None, corpus_binding: Mapping[str, Any] | None = None,
) -> dict:
    """Overall go/no-go against the predeclared protocol.

    Returns exactly one of ``corpus_not_qualified`` | ``insufficient_sample`` |
    ``inconclusive`` | ``meets_predeclared_threshold``. ``corpus_not_qualified`` is
    the first gate: without a ``ready`` ``corpus_qualification`` receipt, no other
    verdict is reachable.

    - ``insufficient_sample`` whenever the predeclared minimums are missing, or
      the fired count or the evaluable-period count is below them. Validation is
      never claimed on thin data.
    - ``meets_predeclared_threshold`` only when the sample is adequate AND the
      predeclared acceptance thresholds exist AND the point hit rate and its
      Wilson lower bound clear the required hit rate AND the false-positive rate
      is within the predeclared tolerance.
    - ``inconclusive`` otherwise (adequate sample, but the result neither clears
      nor is meaningfully gated by the predeclared thresholds).
    """
    signals = _signals(run)
    part = _partition(signals, _normalize_outcomes(outcomes), protocol)
    records = part["records"]
    fired_n = sum(1 for rec in records if rec.fired and rec.met is not None)
    evaluable_n = sum(1 for rec in records if rec.present)

    hr = hit_rate(run, outcomes=outcomes, protocol=protocol)
    fpr = false_positive_rate(run, outcomes=outcomes, protocol=protocol)

    min_fired = _value(protocol, "min_fired_signals")
    if min_fired is None:
        min_fired = _value(protocol, "min_sample_size")
    min_periods = _value(protocol, "min_evaluable_periods")
    if min_periods is None:
        min_periods = _value(protocol, "min_sample_size")
    min_hit_rate = _value(protocol, "min_hit_rate")
    fp_tolerance = _value(protocol, "false_positive_tolerance")

    corpus_gate = _corpus_precondition(corpus_qualification, protocol)
    preconditions = protocol.get("preconditions")
    gated = isinstance(preconditions, Mapping) and "qualified_historical_corpus_P0_8" in preconditions
    if gated and db is not None and corpus_binding is not None and isinstance(run, ReplayRun):
        from eval.replay.corpus_binding import verify_corpus_binding, verify_replay_result
        if (run.manifest is None or tuple(signal.as_of for signal in run.signals) != run.manifest.cutoffs):
            corpus_gate = {"qualified": False, "echo": None,
                           "reason": "P0.8 replay signal cutoffs differ from the bound manifest"}
        else:
            corpus_gate = verify_corpus_binding(
                db, manifest=run.manifest, protocol=protocol, receipt=corpus_binding,
            )
            if corpus_gate["qualified"]:
                try:
                    verify_replay_result(db, run)
                except (ValueError, TypeError, KeyError, AttributeError) as exc:
                    corpus_gate = {"qualified": False, "echo": None,
                                   "reason": f"P0.8 replay verification refused: {exc}"}

    base = {
        "fired_n": fired_n,
        "evaluable_n": evaluable_n,
        "min_fired_signals": min_fired,
        "min_evaluable_periods": min_periods,
        "min_hit_rate": min_hit_rate,
        "false_positive_tolerance": fp_tolerance,
        "hit_rate": hr,
        "false_positive_rate": fpr,
        "reconstructed_excluded": part["reconstructed_excluded"],
        "status_excluded": part["status_excluded"],
        "corpus_qualification": corpus_gate["echo"],
    }

    # P0.8 precondition gates everything: no qualified corpus -> no validation.
    if not corpus_gate["qualified"]:
        return {**base, "verdict": "corpus_not_qualified", "reason": corpus_gate["reason"]}

    if min_fired is None or min_periods is None:
        return {
            **base,
            "verdict": "insufficient_sample",
            "reason": "predeclared sample minimums are not set in the protocol",
        }
    if fired_n < min_fired or evaluable_n < min_periods:
        return {
            **base,
            "verdict": "insufficient_sample",
            "reason": (
                f"fired_n={fired_n} (min {min_fired}), "
                f"evaluable_n={evaluable_n} (min {min_periods})"
            ),
        }

    if gated:
        return {**base, "verdict": "inconclusive",
                "reason": "P0.8 evidence is bound, but method-specific outcome extraction, temporal holdout and manifest-bound comparator acceptance are not implemented"}

    rate = hr["hit_rate"]
    interval = hr["interval"]
    fp_rate = fpr["false_positive_rate"]
    meets = (
        min_hit_rate is not None
        and rate is not None
        and interval is not None
        and rate >= min_hit_rate
        and interval["low"] >= min_hit_rate
        and (fp_tolerance is None or (fp_rate is not None and fp_rate <= fp_tolerance))
    )
    if meets:
        return {
            **base,
            "verdict": "meets_predeclared_threshold",
            "reason": (
                f"hit_rate={rate} (Wilson low {interval['low']:.4f}) "
                f">= min {min_hit_rate}; fp_rate={fp_rate} within tolerance"
            ),
        }
    return {
        **base,
        "verdict": "inconclusive",
        "reason": "adequate sample, but the result does not clear the predeclared thresholds",
    }


# ── bundle ──────────────────────────────────────────────────────────────────

def evaluate_outcomes(
    run: ReplayRun, *, outcomes: Mapping[Any, Any], protocol: Mapping[str, Any],
    baseline: BaselineRun | None = None,
    corpus_qualification: Mapping[str, Any] | None = None,
    db: Session | None = None, corpus_binding: Mapping[str, Any] | None = None,
) -> dict:
    """Bundle every P2.2 outcome metric plus the verdict into one JSON dict.

    ``corpus_qualification`` (a ``qualify_corpus`` result) is required for any
    non-HOLD verdict for protocols declaring P0.8. Current request-only receipts
    return ``corpus_not_qualified`` until verified replay evidence binding exists.
    """
    result = {
        "run_id": run.manifest.run_id,
        "run_fingerprint": run.run_fingerprint,
        "method_id": run.manifest.method_id,
        "method_version": run.manifest.method_version,
        "thresholds_id": run.manifest.thresholds_id,
        "hit_rate": hit_rate(run, outcomes=outcomes, protocol=protocol),
        "false_positive_rate": false_positive_rate(
            run, outcomes=outcomes, protocol=protocol,
        ),
        "subsequent_outcome": subsequent_outcome(
            run, outcomes=outcomes, protocol=protocol,
        ),
        "by_confidence": by_confidence(run, outcomes=outcomes, protocol=protocol),
        "verdict": verdict(
            run, outcomes=outcomes, protocol=protocol,
            corpus_qualification=corpus_qualification, db=db, corpus_binding=corpus_binding,
        ),
    }
    if baseline is not None:
        result["lead_time_summary"] = lead_time_summary(
            run, baseline=baseline, protocol=protocol,
        )
    return result
