"""Freeze/verify/pin behavior for the replay manifest."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

import app.models  # noqa: F401
from app.services.temporal_service import fingerprint
from eval.replay import (
    REFERENCE_METHOD_ID,
    REFERENCE_METHOD_VERSION,
    SeriesSpec,
    freeze,
    load_fixture,
    load_rows,
    load_thresholds,
    verify,
)
from eval.replay.manifest import FIXTURES

UTC = timezone.utc
REF_ID = REFERENCE_METHOD_ID
REF_V = REFERENCE_METHOD_VERSION
THRESHOLDS = FIXTURES / "thresholds.devvelocity-v0.json"
CREATED = datetime(2026, 1, 1, tzinfo=UTC)
CUTOFFS = [datetime(2026, 1, 20, tzinfo=UTC)]


def _freeze(db):
    loaded = load_fixture(db, FIXTURES / "devvelocity_v0_known_then.jsonl")
    thresholds, _ = load_thresholds(THRESHOLDS)
    series = SeriesSpec(
        series_keys=loaded.series_keys, methodology_version=loaded.methodology_version,
    )
    manifest = freeze(
        db, method_id=REF_ID, method_version=REF_V, series=series, cutoffs=CUTOFFS,
        thresholds=thresholds, data_scope="local_fixture", created_at=CREATED,
    )
    return loaded, manifest


def test_freeze_then_verify_passes_on_untouched_snapshot(db):
    _, manifest = _freeze(db)
    verify(db, manifest)  # does not raise
    assert manifest.snapshot_id
    assert manifest.feature_version.startswith("canonical-observation-v1:")


def test_appending_to_the_cohort_breaks_verify(db):
    _, manifest = _freeze(db)
    # Append a brand-new observation into the same frozen series.
    load_rows(db, [{
        "key": "kt-extra", "entity_id": "ent-devvel", "source_key": "src-devvel",
        "external_record_id": "repo-main", "attribute": "devvelocity.commit_count",
        "value": 175, "unit": "count",
        "effective_at": "2026-01-18T00:00:00+00:00",
        "first_observed_at": "2026-01-18T00:00:00+00:00",
        "recorded_at": "2026-01-19T00:00:00+00:00",
        "methodology_version": "canonical-observation-v1",
    }])
    with pytest.raises(ValueError, match="drift"):
        verify(db, manifest)


def test_thresholds_edit_changes_thresholds_id(db):
    data, thresholds_id = load_thresholds(THRESHOLDS)
    tampered = dict(data)
    tampered["signal_frequency"] = {"status": "predeclared", "value": 0.9}
    assert fingerprint(tampered) != thresholds_id


def test_unapproved_data_scope_refuses_to_start(db):
    loaded = load_fixture(db, FIXTURES / "devvelocity_v0_known_then.jsonl")
    thresholds, _ = load_thresholds(THRESHOLDS)
    series = SeriesSpec(
        series_keys=loaded.series_keys, methodology_version=loaded.methodology_version,
    )
    with pytest.raises(ValueError, match="data_scope"):
        freeze(
            db, method_id=REF_ID, method_version=REF_V, series=series, cutoffs=CUTOFFS,
            thresholds=thresholds, data_scope="production", created_at=CREATED,
        )


def test_approved_local_snapshot_scope_is_allowed(db):
    loaded = load_fixture(db, FIXTURES / "devvelocity_v0_known_then.jsonl")
    thresholds, _ = load_thresholds(THRESHOLDS)
    series = SeriesSpec(
        series_keys=loaded.series_keys, methodology_version=loaded.methodology_version,
    )
    manifest = freeze(
        db, method_id=REF_ID, method_version=REF_V, series=series, cutoffs=CUTOFFS,
        thresholds=thresholds, data_scope="approved_local_snapshot", created_at=CREATED,
    )
    verify(db, manifest)
    assert manifest.data_scope == "approved_local_snapshot"
