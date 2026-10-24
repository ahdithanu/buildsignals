"""Deterministic, offline replay tests for the REAL Development Velocity v0 signal.

These exercise the bridge in ``eval/replay/dv_signal.py`` end to end: the signal
is produced only through ``develop_velocity`` -> ``activity_baseline`` at ``as_of=T``,
so it is cutoff-safe by construction, and the firing decision uses a PREDECLARED
threshold that is read from the hashed thresholds file and copied into
``series.params`` (never hardcoded). The 0-100 score stays unvalidated; this only
replays the existing signal.

Fixtures (``devvelocity_dv_columbus*.jsonl``) are a Columbus permit time-series
whose trailing-mean standardized score crosses the predeclared threshold:
  * as-of 2026-01-05 the baseline is empty      -> abstain -> insufficient_history
  * as-of 2026-01-26 score 60   (< 70)          -> no_signal
  * as-of 2026-02-02 score 90.4 (>= 70)         -> fired
The correction fixture adds two later-dated clears (recorded 2026-02-03) that are
invisible at 2026-02-02 and only lower the count at a later cutoff.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

import app.models  # noqa: F401  (register tables)
from eval.replay import (
    DV_METHOD_ID,
    DV_METHOD_VERSION,
    REGISTRY,
    SeriesSpec,
    dv_series,
    firing_threshold_value,
    freeze,
    load_fixture,
    load_thresholds,
    replay,
)
from eval.replay.dv_signal import development_velocity_signal
from eval.replay.manifest import FIXTURES

UTC = timezone.utc
THRESHOLDS = FIXTURES / "thresholds.devvelocity-v0.json"
CREATED = datetime(2026, 1, 1, tzinfo=UTC)

COLUMBUS = "devvelocity_dv_columbus.jsonl"
COLUMBUS_CORRECTION = "devvelocity_dv_columbus_correction.jsonl"

# Baseline cohort kwargs WITHOUT as_of (the driver supplies as_of=T per cutoff).
BASELINE_PARAMS = {
    "sources": [{"source_id": "src-columbus", "methodology_version": "permit-v1"}],
    "city": "Columbus", "state": "OH", "attribute": "permit.filed_at",
    "period_days": 7, "baseline_periods": 3, "reporting_lag_days": 0,
    "minimum_baseline_records": 1,
}

T_ABSTAIN = datetime(2026, 1, 5, tzinfo=UTC)   # empty baseline -> abstain
T_NO = datetime(2026, 1, 26, tzinfo=UTC)       # score 60 -> no_signal
T_FIRE = datetime(2026, 2, 2, tzinfo=UTC)      # score 90.4 -> fired
T_CORR = datetime(2026, 2, 4, tzinfo=UTC)      # correction now visible


def _build(db, fixture, cutoffs, *, thresholds=None):
    loaded = load_fixture(db, FIXTURES / fixture)
    if thresholds is None:
        thresholds, _ = load_thresholds(THRESHOLDS)
    series = dv_series(loaded, thresholds=thresholds, baseline_params=BASELINE_PARAMS)
    manifest = freeze(
        db, method_id=DV_METHOD_ID, method_version=DV_METHOD_VERSION, series=series,
        cutoffs=cutoffs, thresholds=thresholds, data_scope="local_fixture",
        created_at=CREATED,
    )
    run = replay(
        db, method_id=DV_METHOD_ID, method_version=DV_METHOD_VERSION,
        cutoffs=cutoffs, series=series, manifest=manifest,
    )
    return loaded, series, manifest, run


def _mem_session(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import Base

    path = str(tmp_path / f"dv_{uuid.uuid4().hex[:8]}.db")
    engine = create_engine(
        f"sqlite:///{path}", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_method_is_registered():
    assert DV_METHOD_ID in REGISTRY
    entry = REGISTRY[DV_METHOD_ID]
    assert entry.fn is development_velocity_signal
    assert DV_METHOD_VERSION in entry.versions


def test_fired_vs_no_signal_and_abstention(db):
    _, _, _, run = _build(db, COLUMBUS, [T_ABSTAIN, T_NO, T_FIRE])
    by_cutoff = {signal.as_of: signal for signal in run.signals}
    threshold = firing_threshold_value(load_thresholds(THRESHOLDS)[0])

    # Empty baseline -> the real signal abstains -> insufficient_history, no value.
    assert by_cutoff[T_ABSTAIN].status == "insufficient_history"
    assert by_cutoff[T_ABSTAIN].value is None

    # Score below the predeclared threshold -> no_signal (value is the score).
    no_signal = by_cutoff[T_NO]
    assert no_signal.status == "no_signal"
    assert no_signal.value == pytest.approx(60.0)
    assert no_signal.value < threshold

    # Score at/above the predeclared threshold -> fired.
    fired = by_cutoff[T_FIRE]
    assert fired.status == "fired"
    assert fired.value >= threshold
    assert fired.value == pytest.approx(90.4)
    assert fired.mode == "known_then"
    # Drivers are cited evidence observation ids with role "driver".
    assert fired.drivers
    assert all(d["role"] == "driver" for d in fired.drivers)


def test_later_dated_correction_does_not_change_earlier_result(db, tmp_path):
    # Known-then (no corrections) run.
    kt_run = _build(db, COLUMBUS, [T_FIRE, T_CORR])[3]
    kt_by = {s.as_of: s for s in kt_run.signals}

    # Same series plus two later-dated clears (recorded 2026-02-03), isolated DB.
    corr_db = _mem_session(tmp_path)
    try:
        corr_run = _build(corr_db, COLUMBUS_CORRECTION, [T_FIRE, T_CORR])[3]
    finally:
        corr_db.close()
    corr_by = {s.as_of: s for s in corr_run.signals}

    # As-of T_FIRE (before the correction was recorded): byte-identical on the
    # REAL signal — the later correction is simply not known yet.
    assert corr_by[T_FIRE].fingerprint == kt_by[T_FIRE].fingerprint
    assert corr_by[T_FIRE].status == "fired"

    # The correction only takes effect at the later cutoff, flipping the result.
    assert kt_by[T_CORR].status == "fired"
    assert corr_by[T_CORR].status == "no_signal"


def test_reproducible_run_fingerprint(db):
    _, series, manifest, run_a = _build(db, COLUMBUS, [T_ABSTAIN, T_NO, T_FIRE])
    run_b = replay(
        db, method_id=DV_METHOD_ID, method_version=DV_METHOD_VERSION,
        cutoffs=[T_ABSTAIN, T_NO, T_FIRE], series=series, manifest=manifest,
    )
    assert run_a.run_fingerprint == run_b.run_fingerprint
    assert [s.fingerprint for s in run_a.signals] == [s.fingerprint for s in run_b.signals]


def test_threshold_is_predeclared_hashed_and_pinned(db, tmp_path):
    thresholds, thresholds_hash = load_thresholds(THRESHOLDS)
    file_value = firing_threshold_value(thresholds)
    assert file_value == 70.0  # the predeclared PROVISIONAL cutoff

    _, series, manifest, run = _build(db, COLUMBUS, [T_NO, T_FIRE], thresholds=thresholds)

    # The threshold the signal uses equals the file value, carried immutably in
    # series.params (part of run_fingerprint) — never hardcoded in the signal fn.
    assert series.params["firing_threshold"] == file_value
    # The whole thresholds file is hashed and pinned into the manifest.
    assert manifest.thresholds_id == thresholds_hash

    # Tampering with the thresholds file changes BOTH the hash and the fingerprint:
    # a threshold can neither be hidden from the manifest nor tuned after results.
    tampered = dict(thresholds)
    tampered["firing_threshold"] = {"status": "predeclared_provisional", "value": 55}
    tampered_db = _mem_session(tmp_path)
    try:
        _, t_series, t_manifest, t_run = _build(
            tampered_db, COLUMBUS, [T_NO, T_FIRE], thresholds=tampered,
        )
    finally:
        tampered_db.close()

    assert t_manifest.thresholds_id != manifest.thresholds_id
    assert t_run.run_fingerprint != run.run_fingerprint

    # Behavioural proof the fn reads the (now-lowered) threshold from params/file:
    # the same T_NO cutoff that was no_signal at 70 now fires at 55.
    assert t_series.params["firing_threshold"] == 55.0
    t_by = {s.as_of: s for s in t_run.signals}
    assert t_by[T_NO].status == "fired"


def test_signal_fn_rejects_unknown_version():
    series = SeriesSpec(
        series_keys=("k",), methodology_version="permit-v1",
        params={"baseline": BASELINE_PARAMS, "firing_threshold": 70},
    )
    with pytest.raises(ValueError):
        development_velocity_signal(None, as_of=T_FIRE, series=series, method_version="nope")


def test_p2_2_evaluation_over_available_fixture_is_insufficient_sample(db):
    """P2.2 backtest over the only available (synthetic, non-qualified) fixture.

    No P0.8-qualified corpus exists, so no corpus_qualification receipt is passed:
    the enforced precondition must return corpus_not_qualified (HOLD), never a
    validation claim. (Even with a receipt the fixture is far too short to meet the
    predeclared minimums.) Real evaluation needs the P0.8 qualified corpus.
    """
    from eval.replay.evaluate import evaluate_outcomes, load_protocol

    _, _, _, run = _build(db, COLUMBUS, [T_ABSTAIN, T_NO, T_FIRE])
    protocol = load_protocol(FIXTURES / "dv_v0_evaluation_protocol.json")
    outcomes: dict = {}  # fixture too short to realize a 90-day outcome -> undecidable
    report = evaluate_outcomes(run, outcomes=outcomes, protocol=protocol)

    assert report["verdict"]["verdict"] == "corpus_not_qualified"
    assert report["verdict"]["corpus_qualification"] is None
    assert report["verdict"]["fired_n"] < protocol["min_fired_signals"]
    # Deterministic / reproducible.
    assert evaluate_outcomes(run, outcomes=outcomes, protocol=protocol) == report
