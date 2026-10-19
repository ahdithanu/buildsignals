"""JSON-only metric stubs: frequency, lead-time vs trailing baseline, reproducibility."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import app.models  # noqa: F401
from eval.replay import (
    REFERENCE_METHOD_ID,
    REFERENCE_METHOD_VERSION,
    SeriesSpec,
    baseline_run,
    freeze,
    lead_time_vs_trailing_baseline,
    load_rows,
    load_thresholds,
    replay,
    reproducibility_check,
    signal_frequency,
)
from eval.replay.manifest import FIXTURES

UTC = timezone.utc
REF_ID = REFERENCE_METHOD_ID
REF_V = REFERENCE_METHOD_VERSION
THRESHOLDS = FIXTURES / "thresholds.devvelocity-v0.json"
CREATED = datetime(2026, 1, 1, tzinfo=UTC)

T_PRE = datetime(2025, 12, 31, tzinfo=UTC)
T_ONE = datetime(2026, 1, 5, tzinfo=UTC)
T_BOTH = datetime(2026, 1, 20, tzinfo=UTC)
LEAD_CUTOFFS = [
    datetime(2026, 1, 10, tzinfo=UTC),
    datetime(2026, 2, 5, tzinfo=UTC),
    datetime(2026, 2, 10, tzinfo=UTC),
    datetime(2026, 2, 20, tzinfo=UTC),
]


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


def _kt_rows(b_value):
    return [
        _numeric_row("kt-a", "ent-devvel", "src-devvel", 100, "2026-01-01", "2026-01-02"),
        _numeric_row("kt-b", "ent-devvel", "src-devvel", b_value, "2026-01-10", "2026-01-11"),
    ]


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
    run = replay(
        db, method_id=REF_ID, method_version=REF_V, cutoffs=cutoffs,
        series=series, manifest=manifest,
    )
    return run


def _mem_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import Base

    engine = create_engine(
        f"sqlite:///:memory:{uuid.uuid4().hex}", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_signal_frequency_excludes_unavailable_and_reconstructed(db):
    run = _run_rows(db, _kt_rows(150), [T_PRE, T_ONE, T_BOTH])
    freq = signal_frequency(run, thresholds=load_thresholds(THRESHOLDS)[0])
    assert freq == {
        "fired": 1,
        "eligible_cutoffs": 1,
        "frequency": 1.0,
        "reconstructed_excluded": 0,
        "unavailable_excluded": 2,
        "threshold": 0.5,
    }


def test_signal_frequency_excludes_reconstructed_cutoffs(db):
    rows = [
        _numeric_row("bf-a", "ent-bf", "src-bf", 100, "2026-01-16", "2026-01-18"),
        _numeric_row("bf-b", "ent-bf", "src-bf", 150, "2026-01-19", "2026-01-20"),
    ]
    run = _run_rows(db, rows, [T_BOTH])
    freq = signal_frequency(run, thresholds=load_thresholds(THRESHOLDS)[0])
    assert run.signals[0].mode == "reconstructed"
    assert freq["reconstructed_excluded"] == 1
    assert freq["eligible_cutoffs"] == 0
    assert freq["frequency"] is None


def test_lead_time_vs_trailing_baseline_reports_signed_delta(db):
    # Numeric signal series (fires 2026-02-05).
    signal_rows = [
        _numeric_row("sg-a", "ent-sig", "src-sig", 100, "2026-01-01", "2026-01-02"),
        _numeric_row("sg-b", "ent-sig", "src-sig", 150, "2026-01-18", "2026-01-20"),
    ]
    _seed_permits(db)
    run = _run_rows(db, signal_rows, LEAD_CUTOFFS)
    baseline = baseline_run(db, cutoffs=LEAD_CUTOFFS, request_params=_baseline_params(), move=2.0)

    thresholds = load_thresholds(THRESHOLDS)[0]
    metric = lead_time_vs_trailing_baseline(run, baseline=baseline, thresholds=thresholds)
    assert metric["status"] == "calculated"
    assert metric["first_signal_cutoff"] == datetime(2026, 2, 5, tzinfo=UTC).isoformat()
    assert metric["first_baseline_cutoff"] == datetime(2026, 2, 20, tzinfo=UTC).isoformat()
    assert metric["lead_time_days"] == 15


def test_lead_time_unavailable_when_baseline_never_crosses(db):
    signal_rows = [
        _numeric_row("sg-a", "ent-sig", "src-sig", 100, "2026-01-01", "2026-01-02"),
        _numeric_row("sg-b", "ent-sig", "src-sig", 150, "2026-01-18", "2026-01-20"),
    ]
    _seed_permits(db)
    run = _run_rows(db, signal_rows, LEAD_CUTOFFS)
    baseline = baseline_run(db, cutoffs=LEAD_CUTOFFS, request_params=_baseline_params(), move=100.0)

    metric = lead_time_vs_trailing_baseline(run, baseline=baseline)
    assert metric["status"] == "unavailable"
    assert metric["lead_time_days"] is None


def test_reproducibility_check_reports_zero_divergences(db):
    run = _run_rows(db, _kt_rows(150), [T_PRE, T_ONE, T_BOTH])
    report = reproducibility_check(run, run)
    assert report["run_fingerprint_match"] is True
    assert report["divergent_cutoffs"] == []
    assert report["checked_cutoffs"] == 3


def test_reproducibility_check_flags_the_perturbed_cutoff(db):
    run_a = _run_rows(db, _kt_rows(150), [T_PRE, T_ONE, T_BOTH])
    other = _mem_session()
    try:
        run_b = _run_rows(other, _kt_rows(300), [T_PRE, T_ONE, T_BOTH])
    finally:
        other.close()
    report = reproducibility_check(run_a, run_b)
    assert report["run_fingerprint_match"] is False
    assert report["divergent_cutoffs"] == [T_BOTH.isoformat()]


# ── permit baseline seed ────────────────────────────────────────────────────

def _permit_row(key, external, filed):
    stamp = f"{filed}T00:00:00+00:00"
    return {
        "key": key, "entity_id": "ent-permit", "source_key": "src-permit",
        "external_record_id": external, "attribute": "permit.filed_at",
        "value": stamp, "effective_at": stamp, "first_observed_at": stamp,
        "recorded_at": stamp, "methodology_version": "permit-v1",
        "record_type": "permit", "source_type": "permit",
        "geography": {"city": "Austin", "state": "TX"},
    }


def _seed_permits(db):
    load_rows(db, [
        _permit_row("p1", "permit-1", "2026-01-15"),
        _permit_row("p2", "permit-2", "2026-01-25"),
        _permit_row("p3", "permit-3", "2026-02-05"),
        _permit_row("p4", "permit-4", "2026-02-12"),
        _permit_row("p5", "permit-5", "2026-02-14"),
        _permit_row("p6", "permit-6", "2026-02-16"),
    ])


def _baseline_params():
    return {
        "sources": [{"source_id": "src-permit", "methodology_version": "permit-v1"}],
        "city": "Austin", "state": "TX", "attribute": "permit.filed_at",
        "period_days": 10, "baseline_periods": 3, "reporting_lag_days": 0,
        "minimum_baseline_records": 1,
    }
