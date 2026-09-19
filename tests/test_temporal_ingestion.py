import csv
from datetime import datetime, timezone

from app.models.graph import GraphEntity, GraphEntityLink, GraphEntityType
from app.models.ingestion import RawSourceRecord
from app.models.planning import PlanningRecord
from app.models.temporal import TemporalEvent, TemporalObservation
from tests.test_permit_ingestion import _source_payload, _write_csv
from tests.test_planning_intelligence import _planning_source


def test_same_run_reversion_and_methodology_change_keep_event_identity(client, db, tmp_path):
    from app.models.ingestion import PermitRecord
    from app.services.ingestion.temporal_projection import project_record_observations

    path = tmp_path / "permit.csv"
    _write_csv(path, status="Submitted", approval_stage="pre_approval")
    source = client.post("/ingestion/sources", json=_source_payload(str(path))).json()
    run = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1}).json()
    assert run["records_failed"] == 0
    permit = db.query(PermitRecord).one()
    permit.status_updated_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    raw = db.query(RawSourceRecord).one()
    entity_id = db.query(GraphEntityLink).filter_by(record_type="permit", record_id=permit.id).one().entity_id

    def project(entity=entity_id):
        project_record_observations(db, record=permit, raw=raw, entity_id=entity, run_id=run["id"])
        db.flush()

    for status in ["Under Review", "Submitted", "Submitted"]:
        permit.status = status
        project()
    statuses = db.query(TemporalObservation).filter_by(attribute="permit.status").order_by(
        TemporalObservation.recorded_at,
    ).all()
    assert [row.value for row in statuses] == ["Submitted", "Under Review", "Submitted"]
    assert db.query(TemporalEvent).filter_by(event_type="permit.status_observed").count() == 3
    count = db.query(TemporalEvent).count()
    permit.normalization_hash = "f" * 64
    project()
    assert db.query(TemporalEvent).count() == count
    survivor = GraphEntity(
        entity_type=GraphEntityType.permit, display_name="Surviving permit", normalized_name="surviving permit",
    )
    db.add(survivor)
    db.flush()
    assert permit.filed_at is not None
    permit.filed_at = None
    project(survivor.id)
    assert db.query(TemporalEvent).count() == count
    latest_filing = db.query(TemporalObservation).filter_by(
        attribute="permit.filed_at",
    ).order_by(TemporalObservation.recorded_at.desc()).first()
    assert latest_filing.entity_id == survivor.id
    assert latest_filing.value is None and latest_filing.effective_at is None

    from app.schemas.activity_baseline import ActivityBaselineRequest
    from app.services.activity_baseline import activity_baseline

    baseline = activity_baseline(db, ActivityBaselineRequest(
        as_of=datetime.now(timezone.utc), city=permit.city, state=permit.state,
        period_days=90, reporting_lag_days=0,
        sources=[{"source_id": source["id"], "methodology_version": latest_filing.methodology_version}],
    ))
    assert all(window["observed_records"] == 0 for window in baseline["sources"][0]["windows"])


def test_permit_projection_captures_changes_reversions_and_missing_dates(client, db, tmp_path):
    path = tmp_path / "permits.csv"
    _write_csv(path, status="Submitted", approval_stage="pre_approval")
    source = client.post("/ingestion/sources", json=_source_payload(str(path))).json()

    def run():
        response = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
        assert response.status_code == 201, response.text
        assert response.json()["records_failed"] == 0, response.text
        db.expire_all()

    run()
    count = db.query(TemporalObservation).count()
    assert count > 0
    run()
    assert db.query(TemporalObservation).count() == count
    _write_csv(path, status="Issued")
    run()
    _write_csv(path, status="Submitted", approval_stage="pre_approval")
    run()
    statuses = db.query(TemporalObservation).filter_by(attribute="permit.status").order_by(
        TemporalObservation.recorded_at,
    ).all()
    assert [row.value for row in statuses] == ["Submitted", "Issued", "Submitted"]
    assert statuses[0].raw_source_record_id == statuses[-1].raw_source_record_id
    assert len({row.id for row in statuses}) == 3
    assert db.query(RawSourceRecord).count() == 2
    assert all(row.effective_at is None for row in statuses)
    assert db.query(TemporalEvent).filter_by(event_type="permit.issued").count() == 0
    assert db.query(TemporalEvent).filter_by(event_type="permit.status_observed").count() == 3
    # Historic filing dates are explicit; old source content still has a new recorded time.
    filed = db.query(TemporalObservation).filter_by(attribute="permit.filed_at").first()
    assert filed.effective_at.year == 2026 and filed.effective_at.month == 7
    assert filed.recorded_at >= filed.first_observed_at


def test_planning_reversion_restores_canonical_state_and_retains_timeline(client, db, tmp_path):
    path = tmp_path / "planning.csv"

    def write(stage):
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["id", "type", "stage", "title", "city", "state", "meeting_at"])
            writer.writeheader()
            writer.writerow({
                "id": "agenda-1", "type": "agenda_item", "stage": stage,
                "title": "Data center rezoning hearing", "city": "Columbus", "state": "OH",
                "meeting_at": "2027-01-10T18:00:00Z",
            })

    write("scheduled")
    source = client.post("/ingestion/sources", json=_planning_source(str(path))).json()
    for stage in ["scheduled", "continued", "scheduled", "scheduled"]:
        write(stage)
        run = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
        assert run.status_code == 201, run.text
        assert run.json()["records_failed"] == 0, run.text
        db.expire_all()
    assert db.query(PlanningRecord).one().stage == "scheduled"
    rows = db.query(TemporalObservation).filter_by(attribute="planning.stage").order_by(
        TemporalObservation.recorded_at,
    ).all()
    assert [row.value for row in rows] == ["scheduled", "continued", "scheduled"]
    assert db.query(TemporalEvent).filter_by(event_type="planning.meeting_scheduled").count() == 1
    assert db.query(TemporalEvent).filter_by(event_type="planning.approved").count() == 0
