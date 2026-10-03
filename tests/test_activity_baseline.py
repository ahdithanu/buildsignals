from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

import app.services.activity_baseline as baseline
import app.services.temporal_service as temporal
from app.models.graph import GraphEntity, GraphEntityType
from app.models.ingestion import IngestionRun, IngestionSource, RawSourceRecord
from app.models.organization import Organization
from app.schemas.activity_baseline import ActivityBaselineRequest, ActivityBaselineResponse
from app.schemas.temporal import ObservationCreate
from app.utils.org_scope import (
    RequestContext,
    get_org_id,
    reset_current_context,
    set_current_context,
)

AS_OF = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
END = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _cohort_factory(db, monkeypatch):
    def make_source():
        org = get_org_id()
        if not db.get(Organization, org):
            db.add(Organization(id=org, name=org, slug=org))
            db.flush()
        source = IngestionSource(
            organization_id=org, key=f"test-{uuid4()}", name="Test permits", adapter="csv", record_type="permit",
        )
        entity = GraphEntity(
            organization_id=org, entity_type=GraphEntityType.permit,
            display_name="Permit", normalized_name="permit",
        )
        db.add_all([source, entity])
        db.flush()
        run = IngestionRun(organization_id=org, source_id=source.id, status="completed")
        db.add(run)
        db.flush()

        def add(external_id, effective=END - timedelta(days=1), **overrides):
            recorded = overrides.pop("recorded", AS_OF - timedelta(hours=1))
            received = overrides.pop("received", AS_OF - timedelta(days=1))
            raw = RawSourceRecord(
                organization_id=org, source_id=source.id, run_id=run.id,
                external_record_id=external_id, record_type="permit",
                content_hash=temporal.fingerprint(str(uuid4())), payload={}, received_at=received,
            )
            db.add(raw)
            db.flush()
            monkeypatch.setattr(temporal, "_utcnow", lambda: recorded)
            values = dict(
                entity_id=entity.id, raw_source_record_id=raw.id,
                observation_key=temporal.fingerprint(str(uuid4())), attribute="permit.filed_at",
                value=effective.isoformat() if effective else None, effective_at=effective,
                confidence=1, geography={"city": "Columbus", "state": "OH"}, methodology_version="test-v1",
            )
            values.update(overrides)
            return temporal.record_observation(db, ObservationCreate(**values))[0]

        return source, add

    return make_source


@pytest.fixture
def cohort(db, monkeypatch):
    return _cohort_factory(db, monkeypatch)


def request_for(*sources, **overrides):
    values = dict(
        as_of=AS_OF, city="Columbus", state="OH", period_days=7, baseline_periods=3,
        reporting_lag_days=0, minimum_baseline_records=1,
        sources=[{"source_id": source.id, "methodology_version": "test-v1"} for source in sources],
    )
    values.update(overrides)
    return ActivityBaselineRequest(**values)


def counts(report):
    return [window["observed_records"] for window in report["sources"][0]["windows"]]


def test_half_open_complete_windows_and_evidence(db, cohort):
    source, add = cohort()
    evidence = [add(str(index), END - timedelta(days=days)) for index, days in enumerate([28, 21, 14, 7])]
    add("too-old", END - timedelta(days=29))
    add("current-unfinished-day", END)
    report = baseline.activity_baseline(db, request_for(source))
    ActivityBaselineResponse.model_validate(report)
    assert counts(report) == [1, 1, 1, 1]
    assert [w["evidence_observation_ids"] for w in report["sources"][0]["windows"]] == [[row.id] for row in evidence]
    assert report["score"] is None and report["status"] == "coverage_unverified"
    assert report["sources"][0]["status"] == "needs_coverage_review"
    assert report["sources"][0]["baseline_mean_observed_records"] == 1
    assert report["sources"][0]["diagnostics"]["outside_window"] == 2


@pytest.mark.parametrize("correction", [
    {"effective": None},
    {"effective": END - timedelta(days=100)},
    {"geography": {"city": "Phoenix", "state": "AZ"}},
    {"geography": {}},
    {"value": "not-a-date"},
])
def test_latest_correction_removes_old_count_before_filtering(db, cohort, correction):
    source, add = cohort()
    add("same-project", recorded=AS_OF - timedelta(hours=2))
    add("same-project", **correction)
    assert counts(baseline.activity_baseline(db, request_for(source))) == [0, 0, 0, 0]


def test_as_of_prevents_lookahead_both_receipt_and_interpretation(db, cohort):
    source, add = cohort()
    add("known", recorded=AS_OF - timedelta(hours=2))
    add("known", effective=None, recorded=AS_OF + timedelta(days=1))
    add("late-backfill", received=AS_OF + timedelta(days=1))
    add("late-interpretation", recorded=AS_OF + timedelta(days=1))
    report = baseline.activity_baseline(db, request_for(source))
    assert counts(report) == [0, 0, 0, 1]


def test_method_and_attribute_pins_do_not_blend(db, cohort):
    source, add = cohort()
    add("known", recorded=AS_OF - timedelta(hours=2))
    add("known", effective=None, methodology_version="test-v2")
    add("issued-only", attribute="permit.issued_at")
    assert counts(baseline.activity_baseline(db, request_for(source))) == [0, 0, 0, 1]
    issued = baseline.activity_baseline(db, request_for(source, attribute="permit.issued_at"))
    assert counts(issued) == [0, 0, 0, 1]


def test_same_source_record_survives_entity_identity_change(db, cohort):
    source, add = cohort()
    add("same", recorded=AS_OF - timedelta(hours=2))
    entity = GraphEntity(
        organization_id=get_org_id(), entity_type=GraphEntityType.permit,
        display_name="Merged identity", normalized_name="merged identity",
    )
    db.add(entity)
    db.flush()
    add("same", entity_id=entity.id)
    assert counts(baseline.activity_baseline(db, request_for(source))) == [0, 0, 0, 1]


def test_equal_time_ambiguity_is_not_resolved_using_random_uuid(db, cohort):
    source, add = cohort()
    add("same")
    add("same", effective=None)
    report = baseline.activity_baseline(db, request_for(source))
    assert counts(report) == [0, 0, 0, 0]
    assert report["sources"][0]["status"] == "ambiguous_latest_observation"
    assert report["sources"][0]["diagnostics"]["ambiguous_latest_records"] == 1


def test_sources_separate_and_fingerprints_reproducible(db, cohort):
    first, add_first = cohort()
    second, add_second = cohort()
    add_first("same-permit")
    add_second("same-permit")
    report = baseline.activity_baseline(db, request_for(first, second))
    replay = baseline.activity_baseline(db, request_for(
        second, first, city=" COLUMBUS ", as_of=AS_OF.astimezone(timezone(timedelta(hours=5))),
    ))
    assert len(report["sources"]) == 2
    assert all(s["windows"][-1]["observed_records"] == 1 for s in report["sources"])
    assert report["request_fingerprint"] == replay["request_fingerprint"]
    assert report["sources"] == replay["sources"]


def test_row_limit_returns_no_partial_baseline(db, cohort, monkeypatch):
    source, add = cohort()
    add("one")
    add("two")
    monkeypatch.setattr(baseline, "MAX_COHORT_ROWS", 1)
    report = baseline.activity_baseline(db, request_for(source))
    assert report["status"] == "bounded_query_exceeded"
    assert report["sources"] == [] and report["score"] is None


def test_revision_history_limit_applies_even_with_one_latest_record(db, cohort, monkeypatch):
    source, add = cohort()
    add("same", recorded=AS_OF - timedelta(hours=2))
    add("same")
    monkeypatch.setattr(baseline, "MAX_HISTORY_ROWS", 1)
    report = baseline.activity_baseline(db, request_for(source))
    assert report["status"] == "bounded_query_exceeded"
    assert report["sources"] == [] and report["score"] is None


def test_lag_and_bounded_evidence_samples(db, cohort):
    source, add = cohort()
    for index in range(8):
        add(str(index), END - timedelta(days=8))
    add("lagged-out", END - timedelta(days=1))
    report = baseline.activity_baseline(db, request_for(source, reporting_lag_days=7))
    assert counts(report) == [0, 0, 0, 8]
    assert len(report["sources"][0]["windows"][-1]["evidence_observation_ids"]) == 5


def test_other_tenant_sources_are_not_visible(db, cohort):
    token = set_current_context(RequestContext("other-org", "other-user"))
    try:
        other, add = cohort()
        add("private")
    finally:
        reset_current_context(token)
    with pytest.raises(LookupError, match="Source cohort not found"):
        baseline.activity_baseline(db, request_for(other))


def test_empty_history_is_not_market_inactivity(db, cohort):
    source, _ = cohort()
    report = baseline.activity_baseline(db, request_for(source))
    assert counts(report) == [0, 0, 0, 0]
    assert report["sources"][0]["status"] == "insufficient_observed_sample"
    assert report["status"] == "coverage_unverified" and report["score"] is None


def test_invalid_queries_and_auth_required(client, cohort, db):
    source, _ = cohort()
    query = request_for(source)
    payload = query.model_dump(mode="json")
    assert client.post("/v1/temporal/activity-baseline", json=payload).status_code == 401
    with pytest.raises(ValidationError):
        ActivityBaselineRequest(**{**payload, "sources": payload["sources"] * 2})
    for override in [{"period_days": 0}, {"baseline_periods": 99}, {"as_of": "2026-01-01"}, {"organization_id": "other"}]:
        with pytest.raises(ValidationError):
            ActivityBaselineRequest(**{**payload, **override})
    with pytest.raises(ValueError, match="future"):
        baseline.activity_baseline(db, request_for(source, as_of=datetime.now(timezone.utc) + timedelta(days=1)))
    with pytest.raises(ValueError, match="supported date range"):
        baseline.activity_baseline(db, request_for(source, as_of=datetime(1, 1, 1, tzinfo=timezone.utc)))
    with pytest.raises(ValueError, match="supported UTC date range"):
        baseline.activity_baseline(db, request_for(source, as_of="0001-01-01T00:00:00+01:00"))


def test_authenticated_endpoint_and_cross_tenant_rejection(client, db, cohort):
    other, _ = cohort()
    registration = client.post("/auth/register", json={
        "email": "baseline@example.com", "password": "CorrectHorseBattery42",
        "full_name": "Baseline Analyst", "organization_name": "Baseline Research",
    })
    assert registration.status_code == 201, registration.text
    auth = registration.json()
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    token = set_current_context(RequestContext(auth["organization_id"], auth["user_id"]))
    try:
        source, add = cohort()
        add("known")
        db.commit()
    finally:
        reset_current_context(token)
    endpoint = "/v1/temporal/activity-baseline"
    response = client.post(endpoint, headers=headers, json=request_for(source).model_dump(mode="json"))
    assert response.status_code == 200, response.text
    assert counts(response.json()) == [0, 0, 0, 1]
    evidence_id = response.json()["sources"][0]["windows"][-1]["evidence_observation_ids"][0]
    evidence = client.get("/v1/temporal/observations", headers=headers, params={
        "observation_id": evidence_id, "as_of": AS_OF.isoformat(),
    })
    assert evidence.status_code == 200
    assert [row["id"] for row in evidence.json()] == [evidence_id]
    assert evidence.json()[0]["raw_source_record_id"]
    assert client.get("/v1/temporal/observations", headers=headers, params={
        "observation_id": evidence_id, "as_of": (AS_OF - timedelta(days=10)).isoformat(),
    }).json() == []
    foreign = client.post(endpoint, headers=headers, json=request_for(other).model_dump(mode="json"))
    assert foreign.status_code == 404
    unknown = request_for(source).model_dump(mode="json")
    unknown["sources"][0]["source_id"] = str(uuid4())
    assert client.post(endpoint, headers=headers, json=unknown).json() == foreign.json()
    future = request_for(source, as_of=datetime.now(timezone.utc) + timedelta(days=1)).model_dump(mode="json")
    assert client.post(endpoint, headers=headers, json=future).status_code == 422
