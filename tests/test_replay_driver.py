"""Deterministic, offline tests for the cutoff-safe replay driver."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

import app.models  # noqa: F401  (register tables for any standalone session)
import app.services.temporal_service as temporal
from eval.replay import (
    REFERENCE_METHOD_ID,
    REFERENCE_METHOD_VERSION,
    SeriesSpec,
    SignalOutput,
    freeze,
    load_fixture,
    load_rows,
    load_thresholds,
    register,
    replay,
)
from eval.replay.driver import ClockAccessError, ReplayWriteError
from eval.replay.manifest import FIXTURES

UTC = timezone.utc
REF_ID = REFERENCE_METHOD_ID
REF_V = REFERENCE_METHOD_VERSION
THRESHOLDS = FIXTURES / "thresholds.devvelocity-v0.json"
CREATED = datetime(2026, 1, 1, tzinfo=UTC)

# Pinned reproducibility constant for the known-then run over the three cutoffs
# below. Catches any accidental change to the canonical result format.
KNOWN_THEN_RUN_FINGERPRINT = "7546a4f05c31cf16f5aeadbc3d3caf1cbe97053101c88ddfd979c508eab24484"

T_PRE = datetime(2025, 12, 31, tzinfo=UTC)
T_ONE = datetime(2026, 1, 5, tzinfo=UTC)
T_BOTH = datetime(2026, 1, 20, tzinfo=UTC)


def _run(db, fixture_name, cutoffs, *, method_id=REF_ID, method_version=REF_V):
    loaded = load_fixture(db, FIXTURES / fixture_name)
    thresholds, _ = load_thresholds(THRESHOLDS)
    series = SeriesSpec(
        series_keys=loaded.series_keys, methodology_version=loaded.methodology_version,
    )
    manifest = freeze(
        db, method_id=method_id, method_version=method_version, series=series,
        cutoffs=cutoffs, thresholds=thresholds, data_scope="local_fixture",
        created_at=CREATED,
    )
    run = replay(
        db, method_id=method_id, method_version=method_version,
        cutoffs=cutoffs, series=series, manifest=manifest,
    )
    return loaded, series, manifest, run


def test_known_delta_reproduces_expected_signal(db):
    _, _, _, run = _run(db, "devvelocity_v0_known_then.jsonl", [T_BOTH, T_PRE, T_ONE])
    by_cutoff = {signal.as_of: signal for signal in run.signals}

    # Before any data exists and when only one observation is eligible: no
    # fabrication - status is insufficient_history and value is None.
    assert by_cutoff[T_PRE].status == "insufficient_history"
    assert by_cutoff[T_PRE].value is None
    assert by_cutoff[T_ONE].status == "insufficient_history"
    assert by_cutoff[T_ONE].value is None

    fired = by_cutoff[T_BOTH]
    assert fired.status == "fired"
    assert fired.value == pytest.approx(50.0)
    assert fired.mode == "known_then"

    assert run.run_fingerprint == KNOWN_THEN_RUN_FINGERPRINT


def test_replay_is_deterministic(db):
    _, series, manifest, run_a = _run(db, "devvelocity_v0_known_then.jsonl", [T_PRE, T_ONE, T_BOTH])
    run_b = replay(
        db, method_id=REF_ID, method_version=REF_V,
        cutoffs=[T_PRE, T_ONE, T_BOTH], series=series, manifest=manifest,
    )
    assert run_a.run_fingerprint == run_b.run_fingerprint
    assert [s.fingerprint for s in run_a.signals] == [s.fingerprint for s in run_b.signals]


def test_later_dated_correction_does_not_change_earlier_result(db, tmp_path):
    # Known-then run in its own isolated snapshot.
    kt_run = _run(db, "devvelocity_v0_known_then.jsonl", [T_BOTH, _t_corr()])[3]
    kt_by = {s.as_of: s for s in kt_run.signals}

    # The correction fixture in a separate snapshot (same ids, plus one
    # later-dated correction row recorded after T_BOTH).
    corr_db = _mem_session(tmp_path)
    try:
        corr_run = _run(corr_db, "devvelocity_v0_with_correction.jsonl", [T_BOTH, _t_corr()])[3]
    finally:
        corr_db.close()
    corr_by = {s.as_of: s for s in corr_run.signals}

    # As-of T_BOTH (before the correction was recorded): byte-identical.
    assert corr_by[T_BOTH].fingerprint == kt_by[T_BOTH].fingerprint
    assert corr_by[T_BOTH].drivers[0]["observation_id"] == "obs-kt-b"

    # The correction appears (changes the result) only at cutoffs >= T_corr.
    assert kt_by[_t_corr()].status == "fired"
    assert corr_by[_t_corr()].status == "no_signal"
    assert corr_by[_t_corr()].drivers[0]["observation_id"] == "obs-kt-c"


def test_known_then_vs_reconstructed_labeling(db):
    aged = [
        _numeric_row("ag-a", "ent-aged", "src-aged", 100, "2026-01-01", "2026-01-02"),
        _numeric_row("ag-b", "ent-aged", "src-aged", 150, "2026-01-05", "2026-01-05"),
    ]
    backfill = [
        _numeric_row("bf-a", "ent-bf", "src-bf", 100, "2026-01-16", "2026-01-18"),
        _numeric_row("bf-b", "ent-bf", "src-bf", 150, "2026-01-19", "2026-01-20"),
    ]
    cutoff = datetime(2026, 1, 20, tzinfo=UTC)

    aged_run = _run_rows(db, aged, [cutoff])
    backfill_run = _run_rows(db, backfill, [cutoff])

    assert aged_run.signals[0].status == "fired"
    assert aged_run.signals[0].mode == "known_then"
    assert backfill_run.signals[0].status == "fired"
    assert backfill_run.signals[0].mode == "reconstructed"


def test_run_fails_if_method_reads_the_wall_clock(db):
    def clock_method(db, *, as_of, series, method_version):
        temporal._utcnow()  # patched to raise during replay
        return SignalOutput("no_signal", None, [], method_version)

    register("bad-clock", ["v0"], clock_method)
    series, manifest = _manifest_for(db, "bad-clock", "v0")
    with pytest.raises(ClockAccessError):
        replay(
            db, method_id="bad-clock", method_version="v0",
            cutoffs=[T_BOTH], series=series, manifest=manifest,
        )


def test_run_fails_if_method_attempts_a_write(db):
    from app.models.organization import Organization

    def write_method(db, *, as_of, series, method_version):
        db.add(Organization(id="evil-org", name="evil", slug="evil"))
        return SignalOutput("no_signal", None, [{"observation_id": "obs-kt-a", "role": "current"}], method_version)

    register("bad-write", ["v0"], write_method)
    series, manifest = _manifest_for(db, "bad-write", "v0")
    with pytest.raises(ReplayWriteError):
        replay(
            db, method_id="bad-write", method_version="v0",
            cutoffs=[T_BOTH], series=series, manifest=manifest,
        )


# ── helpers ─────────────────────────────────────────────────────────────────

def _t_corr():
    return datetime(2026, 2, 5, tzinfo=UTC)


def _numeric_row(key, entity, source, value, effective, recorded):
    return {
        "key": key, "entity_id": entity, "source_key": source,
        "external_record_id": "repo", "attribute": "devvelocity.commit_count",
        "value": value, "unit": "count",
        "effective_at": f"{effective}T00:00:00+00:00",
        "first_observed_at": f"{effective}T00:00:00+00:00",
        "recorded_at": f"{recorded}T00:00:00+00:00",
        "methodology_version": "canonical-observation-v1",
    }


def _run_rows(db, rows, cutoffs):
    loaded = load_rows(db, rows)
    thresholds, _ = load_thresholds(THRESHOLDS)
    series = SeriesSpec(
        series_keys=loaded.series_keys, methodology_version=loaded.methodology_version,
    )
    manifest = freeze(
        db, method_id=REF_ID, method_version=REF_V, series=series, cutoffs=cutoffs,
        thresholds=thresholds, data_scope="local_fixture", created_at=CREATED,
    )
    return replay(
        db, method_id=REF_ID, method_version=REF_V, cutoffs=cutoffs,
        series=series, manifest=manifest,
    )


def _manifest_for(db, method_id, method_version):
    loaded = load_fixture(db, FIXTURES / "devvelocity_v0_known_then.jsonl")
    thresholds, _ = load_thresholds(THRESHOLDS)
    series = SeriesSpec(
        series_keys=loaded.series_keys, methodology_version=loaded.methodology_version,
    )
    manifest = freeze(
        db, method_id=method_id, method_version=method_version, series=series,
        cutoffs=[T_BOTH], thresholds=thresholds, data_scope="local_fixture",
        created_at=CREATED,
    )
    return series, manifest


def _mem_session(tmp_path):
    import uuid

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import Base

    path = str(tmp_path / f"corr_{uuid.uuid4().hex[:8]}.db")
    engine = create_engine(
        f"sqlite:///{path}", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()
