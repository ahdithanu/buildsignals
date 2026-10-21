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


def test_deep_corpus_requires_coverage_audit(db, cohort):
    source, add = cohort()
    _add_windows(add, 22)  # 21 complete windows -> 12 evaluable periods
    report = qualify_corpus(db, request_for(source))
    assert report["status"] == "measured"
    assert report["verdict"] == "insufficient_coverage"
    assert any("audited" in item for item in report["shortfall"])
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


def test_batch_backfill_cannot_qualify_known_then_history(db, cohort):
    source, add = cohort()
    for i in range(22):
        add(f"batch{i}", effective=_event(i), recorded=AS_OF - timedelta(days=1))
    report = qualify_corpus(db, request_for(source))
    assert report["verdict"] == "insufficient_depth"
    assert report["time_depth"]["known_then_evaluable_periods_upper_bound"] == 0
    assert report["time_depth"]["event_evaluable_periods_upper_bound"] == 12


def test_methodology_mismatch_is_excluded(db, cohort):
    source, add = cohort()
    for i in range(22):
        add(f"wrong{i}", effective=_event(i), recorded=_event(i), methodology_version="other-v2")
    report = qualify_corpus(db, request_for(source))
    assert report["completeness"]["cohort_records"] == 0


def test_sources_cannot_be_pooled(cohort):
    from pydantic import ValidationError
    first, _ = cohort()
    second, _ = cohort()
    with pytest.raises(ValidationError):
        request_for(first, second)


def test_future_event_dates_do_not_extend_depth(db, cohort):
    source, add = cohort()
    _add_windows(add, 22)
    add("future", effective=AS_OF + timedelta(days=365), recorded=AS_OF - timedelta(days=1))
    report = qualify_corpus(db, request_for(source))
    assert report["time_depth"]["latest_event_date"] == _event(21).isoformat()
    assert report["diagnostics"]["future_event_date"] == 1


def test_backfilled_baseline_can_support_first_future_cutoff_without_known_time_warmup(db, cohort):
    source, add = cohort()
    # History is captured together. A decision can use it immediately; after
    # horizon+lag the first decision's outcome could mature, with no extra
    # six-month contemporaneous baseline wait. Coverage remains unaudited.
    captured = AS_OF - timedelta(days=97)
    for i in range(22):
        add(f"future-cutoff{i}", effective=_event(i), recorded=captured)
    report = qualify_corpus(db, request_for(source))
    assert report["time_depth"]["known_then_evaluable_periods_upper_bound"] == 1
    assert report["verdict"] != "ready"


def _audit(fingerprint, windows, **overrides):
    values = dict(
        auditor="analyst@buildsignals",
        attested_at=AS_OF - timedelta(days=1),
        audit_methodology_version="coverage-audit-v1",
        attested_request_fingerprint=fingerprint,
        covered_window_indices=list(range(windows)),
        known_then_availability_confirmed=True,
        decision="coverage_audited",
        rationale="Per-window source coverage independently audited.",
    )
    values.update(overrides)
    return values


def test_coverage_audit_promotes_deep_corpus_to_ready(db, cohort):
    source, add = cohort()
    _add_windows(add, 22)  # 21 complete windows
    fingerprint = qualify_corpus(db, request_for(source))["request_fingerprint"]
    report = qualify_corpus(db, request_for(source, coverage_audit=_audit(fingerprint, 21)))
    assert report["verdict"] == "ready"
    assert report["shortfall"] == []
    assert report["time_depth"]["coverage_audited"] is True
    assert report["coverage_audit"]["fingerprint_matched"] is True
    assert report["coverage_audit"]["auditor"] == "analyst@buildsignals"


def test_coverage_audit_excluded_from_request_fingerprint(db, cohort):
    source, add = cohort()
    _add_windows(add, 22)
    without = qualify_corpus(db, request_for(source))["request_fingerprint"]
    with_audit = qualify_corpus(db, request_for(source, coverage_audit=_audit(without, 21)))
    # The attestation signs the measured-inputs fingerprint; adding it must not
    # change that fingerprint, or the auditor could never reproduce it.
    assert with_audit["request_fingerprint"] == without


def test_coverage_audit_wrong_fingerprint_stays_insufficient(db, cohort):
    source, add = cohort()
    _add_windows(add, 22)
    report = qualify_corpus(db, request_for(source, coverage_audit=_audit("0" * 64, 21)))
    assert report["verdict"] == "insufficient_coverage"
    assert any("fingerprint" in item for item in report["shortfall"])
    assert report["time_depth"]["coverage_audited"] is False


def test_coverage_audit_partial_windows_stays_insufficient(db, cohort):
    source, add = cohort()
    _add_windows(add, 22)
    fingerprint = qualify_corpus(db, request_for(source))["request_fingerprint"]
    report = qualify_corpus(db, request_for(source, coverage_audit=_audit(fingerprint, 20)))
    assert report["verdict"] == "insufficient_coverage"
    assert any("must be explicitly audited" in item for item in report["shortfall"])


def test_coverage_audit_requires_known_then_confirmation(db, cohort):
    source, add = cohort()
    _add_windows(add, 22)
    fingerprint = qualify_corpus(db, request_for(source))["request_fingerprint"]
    audit = _audit(fingerprint, 21, known_then_availability_confirmed=False)
    report = qualify_corpus(db, request_for(source, coverage_audit=audit))
    assert report["verdict"] == "insufficient_coverage"
    assert any("known-then" in item for item in report["shortfall"])


def test_coverage_audit_future_attested_at_stays_insufficient(db, cohort):
    source, add = cohort()
    _add_windows(add, 22)
    fingerprint = qualify_corpus(db, request_for(source))["request_fingerprint"]
    audit = _audit(fingerprint, 21, attested_at=AS_OF + timedelta(days=1))
    report = qualify_corpus(db, request_for(source, coverage_audit=audit))
    assert report["verdict"] == "insufficient_coverage"
    assert any("after the cutoff" in item for item in report["shortfall"])


def test_coverage_audit_cannot_bypass_insufficient_depth(db, cohort):
    source, add = cohort()
    _add_windows(add, 5)  # 4 complete windows -> 0 evaluable periods
    fingerprint = qualify_corpus(db, request_for(source))["request_fingerprint"]
    report = qualify_corpus(db, request_for(source, coverage_audit=_audit(fingerprint, 4)))
    # Depth is gated before coverage: a valid audit cannot rescue a shallow corpus.
    assert report["verdict"] == "insufficient_depth"
