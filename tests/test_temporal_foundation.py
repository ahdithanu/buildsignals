from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

import app.services.temporal_service as temporal
from app.models.graph import GraphEntity, GraphEntityType
from app.models.ingestion import IngestionRun, IngestionSource, RawSourceRecord
from app.models.organization import Organization
from app.models.temporal import TemporalObservation
from app.schemas.temporal import EventCreate, ObservationCreate
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _seed(db, *, org_id="default-org", external_id="project-1", received_at=START):
    if db.get(Organization, org_id) is None:
        db.add(Organization(id=org_id, name=org_id, slug=org_id))
        db.flush()
    source = IngestionSource(
        organization_id=org_id, key=f"source-{uuid4()}", name="Public source",
        adapter="csv", record_type="utility_filing",
    )
    entity = GraphEntity(
        organization_id=org_id, entity_type=GraphEntityType.company,
        display_name="Example utility", normalized_name="example utility",
    )
    db.add_all([source, entity])
    db.flush()
    run = IngestionRun(organization_id=org_id, source_id=source.id, status="completed")
    db.add(run)
    db.flush()
    raw = RawSourceRecord(
        organization_id=org_id, source_id=source.id, run_id=run.id,
        external_record_id=external_id, record_type="utility_filing",
        content_hash="a" * 64, payload={"capacity": 100}, received_at=received_at,
    )
    db.add(raw)
    db.flush()
    return entity, raw


def _payload(entity, raw, *, key="first", **overrides):
    data = dict(
        entity_id=entity.id, raw_source_record_id=raw.id,
        observation_key=temporal.fingerprint(key), attribute="power.capacity",
        value=100, unit="MW", effective_at=START,
        confidence=0.95, methodology_version="test-v1", geography={"state": "VA"},
        source_url="https://example.test/filing/1",
    )
    data.update(overrides)
    return ObservationCreate(**data)


def test_creation_is_evidence_linked_idempotent_and_append_only(db):
    entity, raw = _seed(db)
    payload = _payload(entity, raw)
    row, created = temporal.record_observation(db, payload)
    db.commit()
    assert created
    assert row.source_id == raw.source_id
    assert row.source_type == "utility_filing"
    assert temporal.utc(row.first_observed_at) == START
    again, created = temporal.record_observation(db, payload)
    assert again.id == row.id and not created
    with pytest.raises(ValueError, match="different evidence or content"):
        temporal.record_observation(db, _payload(entity, raw, value=200))
    row.value = 999
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()
    assert db.get(TemporalObservation, row.id).value == 100
    db.delete(row)
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()


def test_as_of_does_not_leak_backfilled_or_reinterpreted_evidence(db, monkeypatch):
    entity, raw = _seed(db, received_at=START + timedelta(days=20))
    recorded = START + timedelta(days=30)
    monkeypatch.setattr(temporal, "_utcnow", lambda: recorded)
    row, _ = temporal.record_observation(db, _payload(entity, raw, effective_at=START))
    assert temporal.observations_as_of(db, as_of=START + timedelta(days=19)) == []
    assert temporal.observations_as_of(db, as_of=START + timedelta(days=29)) == []
    assert temporal.observations_as_of(db, as_of=recorded) == [row]
    recorded += timedelta(days=10)
    correction, _ = temporal.record_observation(db, _payload(
        entity, raw, key="correction", value=80, methodology_version="test-v2",
    ))
    assert temporal.observations_as_of(db, as_of=START + timedelta(days=35)) == [row]
    assert temporal.observations_as_of(db, as_of=recorded) == [correction, row]
    assert correction.series_key != row.series_key


def test_retry_keeps_historical_identity_after_live_entity_is_retired(db):
    entity, raw = _seed(db)
    payload = _payload(entity, raw)
    row, _ = temporal.record_observation(db, payload)
    db.delete(entity)
    db.flush()
    replayed, created = temporal.record_observation(db, payload)
    assert replayed.id == row.id and not created
    with pytest.raises(LookupError):
        temporal.record_observation(db, payload.model_copy(update={"observation_key": "e" * 64}))


def test_event_keeps_unknown_occurrence_unknown_and_is_idempotent(db, monkeypatch):
    entity, raw = _seed(db)
    monkeypatch.setattr(temporal, "_utcnow", lambda: START + timedelta(days=1))
    observation, _ = temporal.record_observation(db, _payload(entity, raw, effective_at=None))
    payload = EventCreate(observation_id=observation.id, event_type="utility.capacity_observed")
    event, created = temporal.record_event(db, payload)
    assert created and event.occurred_at is None
    again, created = temporal.record_event(db, payload)
    assert again.id == event.id and not created
    assert temporal.events_as_of(db, as_of=START) == []
    assert temporal.events_as_of(db, as_of=START + timedelta(days=1)) == [event]
    with pytest.raises(ValueError, match="different occurrence time"):
        temporal.record_event(db, payload.model_copy(update={"occurred_at": START}))
    db.commit()
    event.event_type = "tampered"
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()


def test_future_scheduled_event_is_known_but_not_claimed_to_have_occurred(db, monkeypatch):
    entity, raw = _seed(db)
    monkeypatch.setattr(temporal, "_utcnow", lambda: START)
    future = START + timedelta(days=90)
    row, _ = temporal.record_observation(db, _payload(entity, raw, effective_at=future))
    event, _ = temporal.record_event(db, EventCreate(
        observation_id=row.id, event_type="planning.meeting_scheduled", occurred_at=future,
    ))
    assert temporal.events_as_of(db, as_of=START) == [event]
    assert event.occurred_at == future


def test_non_utc_cutoffs_use_the_same_instant_on_sqlite(db, monkeypatch):
    entity, raw = _seed(db)
    recorded = START + timedelta(hours=11)
    monkeypatch.setattr(temporal, "_utcnow", lambda: recorded)
    row, _ = temporal.record_observation(db, _payload(entity, raw))
    temporal.record_event(db, EventCreate(observation_id=row.id, event_type="capacity.reported"))
    before = datetime(2026, 1, 1, 12, tzinfo=timezone(timedelta(hours=2)))
    assert temporal.observations_as_of(db, as_of=before) == []
    assert temporal.events_as_of(db, as_of=before) == []
    assert temporal.numeric_change(db, series_key=row.series_key, as_of=before)["current_observation_id"] is None
    same_instant = datetime(2026, 1, 1, 13, tzinfo=timezone(timedelta(hours=2)))
    assert temporal.observations_as_of(db, as_of=same_instant) == [row]


def test_cross_tenant_references_and_queries_are_isolated(db):
    entity_a, raw_a = _seed(db, org_id="org-a")
    entity_b, raw_b = _seed(db, org_id="org-b")
    token = set_current_context(RequestContext("org-a", "system"))
    try:
        row, _ = temporal.record_observation(db, _payload(entity_a, raw_a))
        temporal.record_event(db, EventCreate(observation_id=row.id, event_type="capacity.reported"))
        with pytest.raises(LookupError):
            temporal.record_observation(db, _payload(entity_a, raw_b, key="wrong-raw"))
        with pytest.raises(LookupError):
            temporal.record_observation(db, _payload(entity_b, raw_a, key="wrong-entity"))
    finally:
        reset_current_context(token)
    token = set_current_context(RequestContext("org-b", "system"))
    try:
        cutoff = datetime.now(timezone.utc) + timedelta(seconds=1)
        assert temporal.observations_as_of(db, as_of=cutoff) == []
        assert temporal.events_as_of(db, as_of=cutoff) == []
        assert temporal.numeric_change(db, series_key=row.series_key, as_of=cutoff)["status"] == "insufficient_history"
        with pytest.raises(LookupError):
            temporal.record_event(db, EventCreate(observation_id=row.id, event_type="wrong"))
        same_key, _ = temporal.record_observation(db, _payload(entity_b, raw_b))
        assert same_key.id != row.id
    finally:
        reset_current_context(token)


@pytest.mark.parametrize(("previous", "current", "unit", "status", "delta", "percent"), [
    (100, 150, "MW", "calculated", 50, 50),
    (100, 50, "MW", "calculated", -50, -50),
    (100, 100, "MW", "calculated", 0, 0),
    (0, 50, "MW", "zero_baseline", 50, None),
    (100, 150, "GW", "incompatible_units", None, None),
    (100, None, "MW", "non_numeric", None, None),
    (100, True, "MW", "non_numeric", None, None),
    (100, "150", "MW", "non_numeric", None, None),
    (-1e308, 1e308, "MW", "numeric_overflow", None, None),
    (100, 10**400, "MW", "numeric_overflow", None, None),
])
def test_basic_change_reports_only_supported_comparisons(db, monkeypatch, previous, current, unit, status, delta, percent):
    entity, raw = _seed(db)
    now = START
    monkeypatch.setattr(temporal, "_utcnow", lambda: now)
    row, _ = temporal.record_observation(db, _payload(entity, raw, value=previous))
    assert temporal.numeric_change(db, series_key=row.series_key, as_of=now)["status"] == "insufficient_history"
    now += timedelta(days=1)
    temporal.record_observation(db, _payload(entity, raw, key="second", value=current, unit=unit))
    change = temporal.numeric_change(db, series_key=row.series_key, as_of=now)
    assert change["status"] == status
    assert change["absolute_change"] == delta
    assert change["percent_change"] == percent
    assert "score" not in change


@pytest.mark.parametrize("overrides", [
    {"confidence": float("nan")}, {"confidence": 1.1}, {"value": float("inf")},
    {"value": "x" * 33000}, {"attribute": "   "}, {"methodology_version": ""},
    {"effective_at": "2026-01-01T00:00:00"}, {"observation_key": "unbounded"},
    {"recorded_at": START}, {"organization_id": "other-org"},
])
def test_input_rejects_invalid_or_backdated_metadata(db, overrides):
    entity, raw = _seed(db)
    with pytest.raises(ValidationError):
        _payload(entity, raw, **overrides)


def test_temporal_api_requires_login_and_validates_query_bounds(client, db):
    for path in ("observations", "events", "changes"):
        assert client.get(f"/v1/temporal/{path}").status_code == 401
    registration = client.post("/auth/register", json={
        "email": "temporal@example.com", "password": "CorrectHorseBattery42",
        "full_name": "Temporal Analyst", "organization_name": "Temporal Research",
    })
    assert registration.status_code == 201, registration.text
    auth = registration.json()
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    entity, raw = _seed(db, org_id=auth["organization_id"])
    token = set_current_context(RequestContext(auth["organization_id"], auth["user_id"]))
    try:
        row, _ = temporal.record_observation(db, _payload(entity, raw))
        temporal.record_event(db, EventCreate(observation_id=row.id, event_type="capacity.reported"))
        db.commit()
    finally:
        reset_current_context(token)
    response = client.get("/v1/temporal/observations", headers=headers)
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()] == [row.id]
    assert response.json()[0]["raw_source_record_id"] == raw.id
    assert len(client.get("/v1/temporal/events", headers=headers).json()) == 1
    assert client.get("/v1/temporal/observations?limit=501", headers=headers).status_code == 422
    assert client.get("/v1/temporal/events?offset=10001", headers=headers).status_code == 422
    assert client.get("/v1/temporal/events?as_of=2026-01-01T00:00:00", headers=headers).status_code == 422
    change = client.get(f"/v1/temporal/changes?series_key={row.series_key}", headers=headers)
    assert change.status_code == 200, change.text
    assert change.json()["status"] == "insufficient_history"
    for path in ("observations", "events", "changes"):
        for cutoff in ("0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"):
            response = client.get(f"/v1/temporal/{path}", headers=headers, params={
                "as_of": cutoff, "series_key": row.series_key,
            })
            assert response.status_code == 422, response.text
