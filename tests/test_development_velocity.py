"""Deterministic, offline unit tests for Development Velocity v0.

Reuses the cohort fixture pattern from ``tests/test_activity_baseline.py`` (same
``_cohort_factory``, monkeypatched ``temporal._utcnow``, fixed ``AS_OF``/``END``).
Every test is offline and deterministic: the only data path is ``activity_baseline``.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

import app.services.activity_baseline as baseline
from app.schemas.activity_baseline import ActivityBaselineRequest
from app.schemas.development_velocity import DevelopmentVelocityRequest, DevelopmentVelocitySignal
from app.services.development_velocity import develop_velocity
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.test_activity_baseline import AS_OF, END, _cohort_factory

# Mid-window days for a 3-period, 7-day-window, zero-lag layout:
#   window0 [END-28, END-21) ; window1 [END-21, END-14) ; window2 [END-14, END-7)
#   current [END-7, END)
BASELINE_DAYS = {0: 25, 1: 18, 2: 11}
CURRENT_DAY = 4


@pytest.fixture
def cohort(db, monkeypatch):
    return _cohort_factory(db, monkeypatch)


def dv_request(*sources, minimum_populated_baseline_windows=1, seasonal_adjustment="off", **baseline_overrides):
    values = dict(
        as_of=AS_OF, city="Columbus", state="OH", period_days=7, baseline_periods=3,
        reporting_lag_days=0, minimum_baseline_records=1,
        sources=[{"source_id": source.id, "methodology_version": "test-v1"} for source in sources],
    )
    values.update(baseline_overrides)
    return DevelopmentVelocityRequest(
        baseline=ActivityBaselineRequest(**values),
        minimum_populated_baseline_windows=minimum_populated_baseline_windows,
        seasonal_adjustment=seasonal_adjustment,
    )


def seed(add, baseline_counts, current_count):
    """Add distinct-external-id records so each window reaches an exact count."""
    index = 0
    for window_index, count in enumerate(baseline_counts):
        for _ in range(count):
            add(f"b{window_index}-{index}", END - timedelta(days=BASELINE_DAYS[window_index]))
            index += 1
    for _ in range(current_count):
        add(f"c-{index}", END - timedelta(days=CURRENT_DAY))
        index += 1


def only(signal):
    return signal["sources"][0]


def test_happy_path_calculated_bounded_score(db, cohort):
    source, add = cohort()
    seed(add, [2, 3, 1], current_count=5)
    signal = develop_velocity(db, dv_request(source))
    DevelopmentVelocitySignal.model_validate(signal)
    src = only(signal)
    assert signal["status"] == "calculated"
    assert src["status"] == "calculated"
    assert src["baseline_mean"] == 2.0
    assert src["baseline_std"] == 1.0
    assert src["delta"] == 3.0
    assert src["z"] == 3.0
    assert 0 <= signal["score"] <= 100
    assert signal["score"] == 80.0
    # score and confidence are independent, separately reported fields.
    assert signal["score_is_validated"] is False
    assert signal["confidence"] == "medium"
    assert "score" in signal and "confidence" in signal


def test_abstain_on_thin_baseline(db, cohort):
    source, add = cohort()
    seed(add, [1, 1, 0], current_count=5)
    signal = develop_velocity(db, dv_request(source, minimum_populated_baseline_windows=3))
    DevelopmentVelocitySignal.model_validate(signal)
    src = only(signal)
    assert signal["status"] == "abstained_insufficient_sample"
    assert src["status"] == "abstained_insufficient_sample"
    assert signal["score"] is None
    assert signal["confidence"] == "low"
    assert src["delta"] is None and src["percent_change"] is None and src["z"] is None
    assert src["source_score"] is None


def test_zero_baseline_no_divide(db, cohort):
    source, add = cohort()
    seed(add, [0, 0, 0], current_count=5)
    signal = develop_velocity(db, dv_request(source))
    DevelopmentVelocitySignal.model_validate(signal)
    src = only(signal)
    assert src["status"] == "zero_baseline"
    assert src["delta"] == 5.0
    assert src["percent_change"] is None
    assert src["z"] is None
    assert "percent_change (zero_baseline)" in signal["unavailable_fields"]


def test_zero_variance_baseline(db, cohort):
    source, add = cohort()
    seed(add, [3, 3, 3], current_count=5)
    signal = develop_velocity(db, dv_request(source, minimum_populated_baseline_windows=3))
    DevelopmentVelocitySignal.model_validate(signal)
    src = only(signal)
    assert src["status"] == "zero_variance_baseline"
    assert src["z"] is None
    assert src["delta"] == 2.0
    assert src["percent_change"] is not None
    assert "z (zero_variance_baseline)" in signal["unavailable_fields"]


def test_cutoff_safety_no_lookahead(db, cohort):
    source, add = cohort()
    seed(add, [2, 3, 1], current_count=0)
    add("known", END - timedelta(days=CURRENT_DAY))
    add("late-backfill", END - timedelta(days=CURRENT_DAY), received=AS_OF + timedelta(days=1))
    add("late-interpretation", END - timedelta(days=CURRENT_DAY), recorded=AS_OF + timedelta(days=1))
    signal = develop_velocity(db, dv_request(source))
    assert signal["status"] == "calculated"
    assert only(signal)["current"] == 1  # the two late records are not visible at as_of
    early = develop_velocity(db, dv_request(source, as_of=AS_OF - timedelta(days=10)))
    assert early["score"] is None  # nothing received yet at the earlier cutoff


def test_correction_removes_current_window_count(db, cohort):
    source, add = cohort()
    seed(add, [2, 2, 2], current_count=0)
    add("gone", END - timedelta(days=CURRENT_DAY), recorded=AS_OF - timedelta(hours=2))
    add("gone", effective=None)  # latest correction clears the filing date
    signal = develop_velocity(db, dv_request(source))
    src = only(signal)
    assert src["current"] == 0
    assert src["delta"] == -2.0


def test_determinism_reproducible_fingerprint(db, cohort):
    first, add_first = cohort()
    second, add_second = cohort()
    seed(add_first, [2, 3, 1], current_count=5)
    seed(add_second, [1, 1, 1], current_count=4)
    report = develop_velocity(db, dv_request(first, second, minimum_populated_baseline_windows=3))
    replay = develop_velocity(db, dv_request(
        second, first, minimum_populated_baseline_windows=3,
        city=" COLUMBUS ", as_of=AS_OF.astimezone(timezone(timedelta(hours=5))),
    ))
    assert report["request_fingerprint"] == replay["request_fingerprint"]
    assert report["sources"] == replay["sources"]
    assert report["score"] == replay["score"]


def test_ambiguous_latest_excluded_and_confidence_lowered(db, cohort):
    clean, add_clean = cohort()
    noisy, add_noisy = cohort()
    seed(add_clean, [2, 3, 1], current_count=5)
    add_noisy("same")
    add_noisy("same", effective=None)  # tie in recorded times -> ambiguous latest
    signal = develop_velocity(db, dv_request(clean, noisy))
    DevelopmentVelocitySignal.model_validate(signal)
    by_id = {src["source_id"]: src for src in signal["sources"]}
    assert by_id[noisy.id]["status"] == "ambiguous_latest_observation"
    assert by_id[noisy.id]["source_score"] is None  # withdrawn from the market score
    assert by_id[clean.id]["status"] == "calculated"
    assert signal["status"] == "calculated"
    assert signal["score"] == by_id[clean.id]["source_score"]
    assert signal["confidence"] == "low"


def test_overflow_passthrough(db, cohort, monkeypatch):
    source, add = cohort()
    seed(add, [2, 3, 1], current_count=5)
    monkeypatch.setattr(baseline, "MAX_COHORT_ROWS", 1)
    signal = develop_velocity(db, dv_request(source))
    DevelopmentVelocitySignal.model_validate(signal)
    assert signal["status"] == "bounded_query_exceeded"
    assert signal["score"] is None
    assert signal["sources"] == []


def test_seasonal_adjustment_refused(db, cohort):
    source, add = cohort()
    seed(add, [2, 3, 1], current_count=5)
    with pytest.raises(ValueError):
        dv_request(source, seasonal_adjustment="on")
    signal = develop_velocity(db, dv_request(source))
    assert signal["seasonal_adjustment_applied"] is False
    assert any("not" in warning and "seasonally" in warning for warning in signal["warnings"])


def test_score_bounds_clamped(db, cohort):
    source, add = cohort()
    seed(add, [1, 2, 1], current_count=1000)
    signal = develop_velocity(db, dv_request(source, minimum_populated_baseline_windows=3))
    src = only(signal)
    assert src["z"] > 5  # the raw standardized distance is huge
    assert src["source_score"] == 100.0  # but the score clamps to the bound
    assert signal["score"] == 100.0


def test_auth_and_cross_tenant(client, db, cohort):
    other, _ = cohort()
    registration = client.post("/auth/register", json={
        "email": "velocity@example.com", "password": "CorrectHorseBattery42",
        "full_name": "Velocity Analyst", "organization_name": "Velocity Research",
    })
    assert registration.status_code == 201, registration.text
    auth = registration.json()
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    token = set_current_context(RequestContext(auth["organization_id"], auth["user_id"]))
    try:
        source, add = cohort()
        seed(add, [2, 3, 1], current_count=5)
        db.commit()
    finally:
        reset_current_context(token)
    endpoint = "/v1/temporal/development-velocity"
    assert client.post(endpoint, json=dv_request(source).model_dump(mode="json")).status_code == 401
    response = client.post(endpoint, headers=headers, json=dv_request(source).model_dump(mode="json"))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "calculated"
    foreign = client.post(endpoint, headers=headers, json=dv_request(other).model_dump(mode="json"))
    assert foreign.status_code == 404
    unknown = dv_request(source).model_dump(mode="json")
    unknown["baseline"]["sources"][0]["source_id"] = str(uuid4())
    assert client.post(endpoint, headers=headers, json=unknown).status_code == 404
    future = dv_request(source, as_of=datetime.now(timezone.utc) + timedelta(days=1)).model_dump(mode="json")
    assert client.post(endpoint, headers=headers, json=future).status_code == 422
