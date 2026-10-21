import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

import app.services.temporal_service as temporal
from app.models.graph import GraphEntity, GraphEntityType
from app.models.ingestion import IngestionRun, IngestionSource, RawSourceRecord
from app.models.organization import Organization
from app.schemas.temporal import ObservationCreate
from app.services.corpus_qualification import CorpusQualificationRequest, qualify_corpus
from app.utils.org_scope import (
    RequestContext,
    get_org_id,
    reset_current_context,
    set_current_context,
)

AS_OF = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
BASE_EVENT = datetime(2024, 1, 1, tzinfo=timezone.utc)
WINDOW = timedelta(days=30)


def _cohort_factory(db, monkeypatch):
    def make_source():
        org = get_org_id()
        if not db.get(Organization, org):
            db.add(Organization(id=org, name=org, slug=org))
            db.flush()
        source = IngestionSource(
            organization_id=org, key=f"test-{uuid4()}", name="Columbus permits",
            adapter="csv", record_type="permit",
        )
        db.add(source)
        db.flush()
        run = IngestionRun(organization_id=org, source_id=source.id, status="completed")
        db.add(run)
        db.flush()

        def add(external_id, *, effective, recorded, received=None, entity_id=None,
                geography=None, value="__event__", attribute="permit.filed_at",
                methodology_version="test-v1"):
            if received is None:
                received = recorded - timedelta(days=1)
            if entity_id is None:
                entity = GraphEntity(
                    organization_id=org, entity_type=GraphEntityType.permit,
                    display_name="Permit", normalized_name=f"permit-{uuid4()}",
                )
                db.add(entity)
                db.flush()
                entity_id = entity.id
            if value == "__event__":
                value = effective.isoformat() if effective else None
            if geography is None:
                geography = {"city": "Columbus", "state": "OH"}
            raw = RawSourceRecord(
                organization_id=org, source_id=source.id, run_id=run.id,
                external_record_id=external_id, record_type="permit",
                content_hash=temporal.fingerprint(str(uuid4())), payload={}, received_at=received,
            )
            db.add(raw)
            db.flush()
            monkeypatch.setattr(temporal, "_utcnow", lambda: recorded)
            return temporal.record_observation(db, ObservationCreate(
                entity_id=entity_id, raw_source_record_id=raw.id,
                observation_key=temporal.fingerprint(str(uuid4())), attribute=attribute,
                value=value, effective_at=effective, confidence=1,
                geography=geography, methodology_version=methodology_version,
            ))[0]

        return source, add

    return make_source


@pytest.fixture
def cohort(db, monkeypatch):
    return _cohort_factory(db, monkeypatch)


def request_for(*sources, **overrides):
    values = dict(
        as_of=AS_OF, city="Columbus", state="OH", attribute="permit.filed_at",
        sources=[{"source_id": s.id, "methodology_version": "test-v1"} for s in sources],
    )
    values.update(overrides)
    return CorpusQualificationRequest(**values)


def _event(i):
    return BASE_EVENT + WINDOW * i


def _add_windows(add, count, *, start=0):
    """One dated record per monthly window index [start, start+count)."""
    return [
        add(f"w{i}", effective=_event(i), recorded=_event(i) + timedelta(days=10))
        for i in range(start, start + count)
    ]


def test_deep_corpus_is_ready(db, cohort):
    source, add = cohort()
    _add_windows(add, 22)  # 21 complete windows -> 12 evaluable periods
    report = qualify_corpus(db, request_for(source))
    assert report["status"] == "measured"
    assert report["verdict"] == "ready"
    assert report["shortfall"] == []
    depth = report["time_depth"]
    assert depth["complete_windows"] == 21
    assert depth["evaluable_periods"] == 12
    assert depth["max_possible_fired_signals"] == 12
    assert depth["recorded_time_depth"]["recorded_span_days"] is not None
    comp = report["completeness"]
    assert comp["event_date_completeness"] == 1.0
    assert comp["month_gaps"] == 0
    assert comp["duplicate_project_rate"] == 0.0


def test_shallow_corpus_is_insufficient_depth_with_shortfall(db, cohort):
    source, add = cohort()
    _add_windows(add, 5)  # 4 complete windows -> 0 evaluable periods
    report = qualify_corpus(db, request_for(source))
    assert report["verdict"] == "insufficient_depth"
    assert report["time_depth"]["evaluable_periods"] == 0
    assert "0 evaluable periods vs 12 required" in report["shortfall"]
    # Dates are complete and clean, so the failure is depth, not completeness.
    assert report["completeness"]["event_date_completeness"] == 1.0


def test_date_incompleteness_is_insufficient_completeness(db, cohort):
    source, add = cohort()
    _add_windows(add, 22)  # deep enough on its own (12 evaluable)
    for i in range(12):  # collection-only records drag completeness below 0.95
        add(f"nodate{i}", effective=None, recorded=_event(i) + timedelta(days=11))
    report = qualify_corpus(db, request_for(source))
    assert report["time_depth"]["evaluable_periods"] == 12  # depth still met
    assert report["verdict"] == "insufficient_completeness"
    assert report["completeness"]["collection_only"] == 12
    assert report["completeness"]["event_date_completeness"] < 0.95
    assert any("event-date completeness" in s for s in report["shortfall"])


def test_duplicate_projects_flag_completeness(db, cohort):
    source, add = cohort()
    records = _add_windows(add, 22)
    shared_entity = records[0].entity_id
    for i in range(6):  # extra records for an existing project (duplicate representation)
        add(f"dup{i}", effective=_event(i), recorded=_event(i) + timedelta(days=12),
            entity_id=shared_entity)
    report = qualify_corpus(db, request_for(source))
    assert report["completeness"]["duplicate_records"] == 6
    assert report["completeness"]["duplicate_project_rate"] > 0.10
    assert report["verdict"] == "insufficient_completeness"
    assert any("duplicate-project rate" in s for s in report["shortfall"])


def test_absent_data_reports_zero_and_insufficient(db, cohort):
    source, _ = cohort()
    report = qualify_corpus(db, request_for(source))
    assert report["status"] == "no_eligible_records"
    assert report["verdict"].startswith("insufficient_")
    assert report["time_depth"]["earliest_event_date"] is None
    assert report["time_depth"]["evaluable_periods"] == 0
    assert report["completeness"]["cohort_records"] == 0


def test_determinism_same_inputs_identical_json(db, cohort):
    source, add = cohort()
    _add_windows(add, 22)
    first = qualify_corpus(db, request_for(source))
    second = qualify_corpus(db, request_for(source))
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    # Equivalent request (city casing, cutoff timezone) yields the same fingerprint.
    replay = qualify_corpus(db, request_for(
        source, city=" COLUMBUS ", as_of=AS_OF.astimezone(timezone(timedelta(hours=5))),
    ))
    assert replay["request_fingerprint"] == first["request_fingerprint"]
    assert replay["time_depth"] == first["time_depth"]


def test_cutoff_safety_later_record_invisible_earlier(db, cohort):
    source, add = cohort()
    _add_windows(add, 22)
    early = qualify_corpus(db, request_for(source))
    # A record recorded AFTER the early cutoff must not be visible as-of it.
    late_recorded = AS_OF + timedelta(days=30)
    add("late", effective=_event(22), recorded=late_recorded, received=late_recorded)
    assert qualify_corpus(db, request_for(source)) == early  # unchanged at early cutoff
    later = qualify_corpus(db, request_for(source, as_of=late_recorded + timedelta(hours=1)))
    assert later["completeness"]["cohort_records"] == early["completeness"]["cohort_records"] + 1
    assert later["time_depth"]["latest_event_date"] == _event(22).isoformat()


def test_per_stage_counts_from_stage_attribute(db, cohort):
    source, add = cohort()
    _add_windows(add, 22)
    for i, stage in enumerate(["approved", "approved", "pre_approval"]):
        add(f"stage{i}", effective=None, recorded=_event(i) + timedelta(days=9),
            value=stage, attribute="permit.approval_stage")
    report = qualify_corpus(db, request_for(source))
    assert report["per_stage_counts"] == {"approved": 2, "pre_approval": 1}
    assert report["diagnostics"]["stage_records"] == 3


def test_cross_tenant_sources_not_visible(db, cohort):
    token = set_current_context(RequestContext("other-org", "other-user"))
    try:
        other, _ = cohort()
    finally:
        reset_current_context(token)
    with pytest.raises(LookupError, match="Source cohort not found"):
        qualify_corpus(db, request_for(other))


def test_future_cutoff_rejected(db, cohort):
    source, _ = cohort()
    with pytest.raises(ValueError, match="future"):
        qualify_corpus(db, request_for(source, as_of=datetime.now(timezone.utc) + timedelta(days=1)))


def test_committed_columbus_fixture_is_insufficient_depth(db):
    """P0.8 run over the only committed Columbus fixture: insufficient_depth (HOLD).

    The replay fixture is a ~4-week weekly series, far below the predeclared
    P2.2 floors, so the harness must report insufficient_depth with the exact
    shortfall and never claim the corpus is ready.
    """
    from eval.replay.manifest import FIXTURES, load_fixture

    load_fixture(db, FIXTURES / "devvelocity_dv_columbus.jsonl")
    req = CorpusQualificationRequest(
        as_of=datetime(2026, 10, 20, tzinfo=timezone.utc),
        sources=[{"source_id": "src-columbus", "methodology_version": "permit-v1"}],
        city="Columbus", state="OH", attribute="permit.filed_at",
    )
    report = qualify_corpus(db, req)
    assert report["verdict"] == "insufficient_depth"
    assert report["time_depth"]["evaluable_periods"] < req.min_evaluable_periods
    assert any("evaluable periods" in s for s in report["shortfall"])
    assert qualify_corpus(db, req) == report  # deterministic
