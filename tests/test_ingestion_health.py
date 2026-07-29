from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.ingestion import (
    IngestionCandidateCanaryAttempt,
    IngestionRun,
    IngestionSource,
    RawSourceRecord,
    SourceFieldMapping,
)
from app.services.ingestion.catalog import load_candidate_catalog, load_catalog
from app.services.ingestion.connector_config import resolve_connector_config_dates
from app.services.ingestion.connectors import FetchEnvelope
from app.services.ingestion.health import (
    CandidateCanaryResult,
    evaluate_source_health,
    resolve_resume_checkpoint,
    validate_source_canary,
)


class FakeConnector:
    def __init__(self, records):
        self.records = records

    def fetch_page(self):
        return FetchEnvelope(
            source="test",
            records=tuple(self.records),
            checkpoint={"offset": len(self.records)},
            has_more=True,
        )


def test_connector_config_resolves_rolling_utc_date_placeholders():
    config = {
        "where": "opened <= '{utc_today_plus_7}' AND opened >= '{utc_today_minus_30}'",
        "query": {"$where": "updated <= '{utc_today}'"},
    }
    now = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)

    resolved = resolve_connector_config_dates(config, now=now)

    assert resolved["where"] == (
        "opened <= '2026-07-25T00:00:00' AND opened >= '2026-06-18T00:00:00'"
    )
    assert resolved["query"]["$where"] == "updated <= '2026-07-18T00:00:00'"


def _source(db, *, key: str = "canary_source", name: str = "Canary source"):
    source = IngestionSource(
        organization_id="default-org",
        key=key,
        name=name,
        adapter="socrata",
        record_type="permit",
        jurisdiction="Austin, TX",
        base_url="https://example.test/records.json",
        settings={"connector": {"page_size": 500}, "defaults": {"state": "TX"}},
    )
    db.add(source)
    db.flush()
    db.add_all([
        SourceFieldMapping(
            organization_id="default-org", source_id=source.id,
            source_field="id", canonical_field="source_record_id",
            is_required=True, is_active=True,
        ),
        SourceFieldMapping(
            organization_id="default-org", source_id=source.id,
            source_field="stage", canonical_field="approval_stage",
            is_required=False, is_active=True,
        ),
    ])
    db.flush()
    db.refresh(source)
    return source


def test_canary_validates_without_persisting_records(db, monkeypatch):
    source = _source(db)
    monkeypatch.setattr(
        "app.services.ingestion.health.build_connector",
        lambda adapter, config: FakeConnector([
            {"id": "1", "stage": "pre_approval"},
            {"id": "2", "stage": "approved"},
        ]),
    )

    result = validate_source_canary(source, sample_size=2)

    assert result.ok is True
    assert result.records_valid == 2
    assert result.approval_stages == {"pre_approval": 1, "approved": 1}
    assert result.sample_record_ids == ["1", "2"]
    assert result.next_checkpoint == {"offset": 2}
    assert source.permit_records == []


def test_canary_reports_record_level_mapping_failures(db, monkeypatch):
    source = _source(db)
    monkeypatch.setattr(
        "app.services.ingestion.health.build_connector",
        lambda adapter, config: FakeConnector([
            {"id": "1", "stage": "pre_approval"},
            {"stage": "pre_approval"},
        ]),
    )

    result = validate_source_canary(source, sample_size=2)

    assert result.ok is False
    assert result.records_valid == 1
    assert result.records_failed == 1
    assert "Missing required source fields" in result.errors[0]


def test_canary_reports_duplicate_normalized_source_record_ids(db, monkeypatch):
    source = _source(db)
    monkeypatch.setattr(
        "app.services.ingestion.health.build_connector",
        lambda adapter, config: FakeConnector([
            {"id": "duplicate", "stage": "pre_approval"},
            {"id": "duplicate", "stage": "approved"},
        ]),
    )

    result = validate_source_canary(source, sample_size=2)

    assert result.ok is False
    assert result.records_valid == 2
    assert result.records_failed == 0
    assert result.sample_record_ids == ["duplicate", "duplicate"]
    assert (
        "Duplicate normalized source_record_id values in canary sample: ['duplicate']"
        in result.errors
    )


def test_canary_reports_page_wide_schema_drift(db, monkeypatch):
    source = _source(db)
    source.settings = {
        **source.settings,
        "canary_required_fields": ["id", "description", "status"],
    }
    monkeypatch.setattr(
        "app.services.ingestion.health.build_connector",
        lambda adapter, config: FakeConnector([{"id": "1", "stage": "pre_approval"}]),
    )

    result = validate_source_canary(source, sample_size=1)

    assert result.ok is False
    assert result.records_valid == 1
    assert "description" in result.errors[0]
    assert "status" in result.errors[0]


def test_canary_accepts_recent_declared_freshness_field(db, monkeypatch):
    source = _source(db)
    now = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)
    source.settings = {
        **source.settings,
        "freshness_field": "updated_at",
        "freshness_sla_hours": 24,
    }
    monkeypatch.setattr(
        "app.services.ingestion.health.build_connector",
        lambda adapter, config: FakeConnector([
            {
                "id": "1",
                "stage": "pre_approval",
                "updated_at": "2026-07-18T06:00:00.000",
            }
        ]),
    )

    result = validate_source_canary(source, sample_size=1, now=now)

    assert result.ok is True
    assert result.records_valid == 1
    assert result.errors == []


def test_canary_fails_stale_declared_freshness_field(db, monkeypatch):
    source = _source(db)
    now = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)
    source.settings = {
        **source.settings,
        "freshness_field": "updated_at",
        "freshness_sla_hours": 24,
    }
    monkeypatch.setattr(
        "app.services.ingestion.health.build_connector",
        lambda adapter, config: FakeConnector([
            {
                "id": "1",
                "stage": "pre_approval",
                "updated_at": "2026-07-16T06:00:00.000",
            }
        ]),
    )

    result = validate_source_canary(source, sample_size=1, now=now)

    assert result.ok is False
    assert result.records_valid == 1
    assert "Latest canary source watermark is 54.0 hours old" in result.errors[0]


def test_canary_freshness_probe_allows_stable_main_pagination(db, monkeypatch):
    source = _source(db)
    now = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)
    source.settings = {
        **source.settings,
        "freshness_field": "updated_at",
        "freshness_sla_hours": 24,
        "canary_freshness_probe": {
            "sample_size": 1,
            "connector": {"order_by": "updated_at DESC", "keyset_fields": []},
        },
    }

    def fake_builder(_adapter, config):
        if config.get("order_by") == "updated_at DESC":
            return FakeConnector([
                {
                    "id": "recent",
                    "stage": "pre_approval",
                    "updated_at": "2026-07-18T06:00:00.000",
                }
            ])
        return FakeConnector([
            {
                "id": "stable",
                "stage": "approved",
                "updated_at": "2026-07-16T06:00:00.000",
            }
        ])

    monkeypatch.setattr("app.services.ingestion.health.build_connector", fake_builder)

    result = validate_source_canary(source, sample_size=1, now=now)

    assert result.ok is True
    assert result.records_fetched == 2
    assert result.records_valid == 2
    assert result.approval_stages == {"approved": 1, "pre_approval": 1}
    assert result.sample_record_ids == ["stable", "recent"]
    assert result.errors == []


def test_canary_freshness_probe_fails_when_latest_rows_are_stale(db, monkeypatch):
    source = _source(db)
    now = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)
    source.settings = {
        **source.settings,
        "freshness_field": "updated_at",
        "freshness_sla_hours": 24,
        "canary_freshness_probe": {
            "sample_size": 1,
            "connector": {"order_by": "updated_at DESC", "keyset_fields": []},
        },
    }

    def fake_builder(_adapter, config):
        if config.get("order_by") == "updated_at DESC":
            return FakeConnector([
                {
                    "id": "stale_latest",
                    "stage": "pre_approval",
                    "updated_at": "2026-07-16T06:00:00.000",
                }
            ])
        return FakeConnector([
            {
                "id": "stable",
                "stage": "approved",
                "updated_at": "2026-07-16T06:00:00.000",
            }
        ])

    monkeypatch.setattr("app.services.ingestion.health.build_connector", fake_builder)

    result = validate_source_canary(source, sample_size=1, now=now)

    assert result.ok is False
    assert "freshness_probe: Latest canary source watermark is 54.0 hours old" in result.errors[0]


def test_canary_stage_probe_validates_targeted_lifecycle_records(db, monkeypatch):
    source = _source(db)
    source.settings = {
        **source.settings,
        "canary_stage_probes": [
            {
                "name": "pre_approval_probe",
                "expected_stage": "pre_approval",
                "sample_size": 1,
                "connector": {"query": {"$where": "stage='pre_approval'"}},
            }
        ],
    }

    def fake_builder(_adapter, config):
        if config.get("query", {}).get("$where") == "stage='pre_approval'":
            return FakeConnector([{"id": "review", "stage": "pre_approval"}])
        return FakeConnector([{"id": "issued", "stage": "approved"}])

    monkeypatch.setattr("app.services.ingestion.health.build_connector", fake_builder)

    result = validate_source_canary(source, sample_size=1)

    assert result.ok is True
    assert result.records_fetched == 2
    assert result.records_valid == 2
    assert result.approval_stages == {"approved": 1, "pre_approval": 1}
    assert result.sample_record_ids == ["issued", "review"]


def test_canary_stage_probe_fails_when_expected_stage_is_absent(db, monkeypatch):
    source = _source(db)
    source.settings = {
        **source.settings,
        "canary_stage_probes": [
            {
                "name": "pre_approval_probe",
                "expected_stage": "pre_approval",
                "connector": {"query": {"$where": "stage='pre_approval'"}},
            }
        ],
    }

    monkeypatch.setattr(
        "app.services.ingestion.health.build_connector",
        lambda _adapter, _config: FakeConnector([{"id": "issued", "stage": "approved"}]),
    )

    result = validate_source_canary(source, sample_size=1)

    assert result.ok is False
    assert "pre_approval_probe" in result.errors[-1]
    assert "Expected normalized stage 'pre_approval'" in result.errors[-1]


def test_health_detects_three_run_cursor_stall(db):
    source = _source(db)
    now = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    for hours_ago in (3, 2, 1):
        db.add(IngestionRun(
            organization_id="default-org",
            source_id=source.id,
            status="partial",
            trigger="scheduled",
            started_at=now - timedelta(hours=hours_ago),
            completed_at=now - timedelta(hours=hours_ago) + timedelta(minutes=5),
            checkpoint={"offset": 500},
            records_seen=500,
            records_inserted=0,
            records_updated=0,
            records_failed=0,
        ))
    db.flush()

    health = evaluate_source_health(db, source, now=now)

    assert health.status == "critical"
    assert health.cursor_stalled is True
    assert health.run_failure_rate == 0
    assert "Checkpoint did not advance" in health.reasons[0]


def test_resume_checkpoint_excludes_failed_and_canary_runs(db):
    source = _source(db)
    now = datetime.now(timezone.utc)
    db.add_all([
        IngestionRun(
            organization_id="default-org", source_id=source.id, status="partial",
            trigger="scheduled", started_at=now - timedelta(hours=3),
            checkpoint={"offset": 100}, records_failed=0,
        ),
        IngestionRun(
            organization_id="default-org", source_id=source.id, status="failed",
            trigger="scheduled", started_at=now - timedelta(hours=2),
            checkpoint={"offset": 200}, records_failed=1,
        ),
        IngestionRun(
            organization_id="default-org", source_id=source.id, status="completed",
            trigger="canary", started_at=now - timedelta(hours=1),
            checkpoint={"offset": 300}, records_failed=0,
        ),
    ])
    db.flush()

    assert resolve_resume_checkpoint(db, source.id) == {"offset": 100}


def test_resume_checkpoint_does_not_reuse_partial_after_full_completion(db):
    source = _source(db)
    now = datetime.now(timezone.utc)
    db.add_all([
        IngestionRun(
            organization_id="default-org", source_id=source.id, status="partial",
            trigger="scheduled", started_at=now - timedelta(hours=2),
            checkpoint={"offset": 500}, records_failed=0,
        ),
        IngestionRun(
            organization_id="default-org", source_id=source.id, status="completed",
            trigger="scheduled", started_at=now - timedelta(hours=1),
            checkpoint=None, records_failed=0,
        ),
    ])
    db.flush()

    assert resolve_resume_checkpoint(db, source.id) is None


def test_source_health_endpoint_is_tenant_scoped_and_serializable(client, db):
    source = _source(db)
    source.settings = {
        **source.settings,
        "license": "ODbL 1.0",
        "signal_stage": "pre_approval_and_approved",
        "official_landing_page": "https://example.test/records",
        "attribution_required": True,
        "share_alike_review_required": True,
    }
    db.commit()

    response = client.get(f"/ingestion/sources/{source.id}/health")

    assert response.status_code == 200, response.text
    assert response.json()["source_key"] == "canary_source"
    assert response.json()["jurisdiction"] == "Austin, TX"
    assert response.json()["license"] == "ODbL 1.0"
    assert response.json()["signal_stage"] == "pre_approval_and_approved"
    assert response.json()["official_landing_page"] == "https://example.test/records"
    assert response.json()["attribution_required"] is True
    assert response.json()["share_alike_review_required"] is True
    assert response.json()["status"] == "unknown"


def test_source_health_endpoint_filters_by_state(client, db):
    _source(db)
    db.commit()
    response = client.get("/ingestion/health?state=Texas")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body
    assert all(row["jurisdiction"].endswith("TX") or row["jurisdiction"] == "Texas" for row in body)
    assert any(row["source_key"] == "canary_source" for row in body)


def test_reliability_summary_endpoint_surfaces_watchlist_and_canary_failures(client, db):
    now = datetime.now(timezone.utc)
    healthy_source = _source(db, key="healthy_source", name="Healthy source")
    db.add(IngestionRun(
        organization_id="default-org",
        source_id=healthy_source.id,
        status="completed",
        trigger="scheduled",
        started_at=now - timedelta(hours=1),
        completed_at=now - timedelta(minutes=55),
        records_seen=25,
        records_inserted=25,
        records_failed=0,
    ))

    stale_source = _source(db, key="stale_source", name="Stale source")
    db.add(IngestionRun(
        organization_id="default-org",
        source_id=stale_source.id,
        status="running",
        trigger="scheduled",
        started_at=now - timedelta(minutes=12),
        heartbeat_at=now - timedelta(minutes=6),
        records_seen=10,
        records_failed=0,
    ))

    db.add(IngestionCandidateCanaryAttempt(
        organization_id="default-org",
        candidate_key="candidate_retry",
        candidate_name="Candidate Retry",
        sample_size=10,
        ok=False,
        records_fetched=10,
        records_valid=0,
        records_failed=10,
        approval_stages={},
        sample_record_ids=[],
        next_checkpoint=None,
        errors=["No valid records"],
    ))
    db.commit()

    response = client.get("/ingestion/reliability-summary")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["healthy_sources"] == 1
    assert body["attention_sources"] == 0
    assert body["critical_sources"] == 1
    assert body["stale_runs"] == 1
    assert body["stalled_cursors"] == 0
    assert body["failed_retry_canaries"] == 1
    assert len(body["watchlist_sources"]) == 1
    assert body["watchlist_sources"][0]["source_name"] == "Stale source"
    assert body["watchlist_sources"][0]["status"] == "critical"
    assert body["watchlist_sources"][0]["active_run_stale"] is True


def test_health_marks_stale_active_heartbeat_critical(db):
    source = _source(db)
    now = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    db.add(IngestionRun(
        organization_id="default-org",
        source_id=source.id,
        status="running",
        trigger="scheduled",
        started_at=now - timedelta(minutes=10),
        heartbeat_at=now - timedelta(minutes=6),
    ))
    db.flush()

    health = evaluate_source_health(db, source, now=now)

    assert health.status == "critical"
    assert health.active_run_stale is True
    assert health.heartbeat_age_seconds == 360
    assert any("heartbeat" in reason for reason in health.reasons)


def test_health_marks_recovered_source_degraded_for_historical_failures(db):
    source = _source(db)
    now = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    db.add_all([
        IngestionRun(
            organization_id="default-org",
            source_id=source.id,
            status="failed",
            trigger="scheduled",
            started_at=now - timedelta(hours=3),
            completed_at=now - timedelta(hours=3) + timedelta(minutes=2),
            records_seen=100,
            records_failed=100,
        ),
        IngestionRun(
            organization_id="default-org",
            source_id=source.id,
            status="completed",
            trigger="scheduled",
            started_at=now - timedelta(hours=1),
            completed_at=now - timedelta(hours=1) + timedelta(minutes=5),
            records_seen=100,
            records_inserted=100,
            records_failed=0,
        ),
    ])
    db.flush()

    health = evaluate_source_health(db, source, now=now)

    assert health.status == "degraded"
    assert health.run_failure_rate == 0.5
    assert any("Latest run recovered" in reason for reason in health.reasons)


def test_health_marks_stale_source_watermark_degraded(db):
    source = _source(db)
    now = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    source.settings = {**(source.settings or {}), "freshness_sla_hours": 24}
    run = IngestionRun(
        organization_id="default-org",
        source_id=source.id,
        status="completed",
        trigger="scheduled",
        started_at=now - timedelta(hours=1),
        completed_at=now - timedelta(minutes=55),
        records_seen=1,
        records_failed=0,
    )
    db.add(run)
    db.flush()
    db.add(RawSourceRecord(
        organization_id="default-org",
        source_id=source.id,
        run_id=run.id,
        external_record_id="stale",
        record_type="permit",
        content_hash="abc",
        payload={"id": "stale"},
        source_updated_at=now - timedelta(hours=30),
        received_at=now - timedelta(minutes=55),
    ))
    db.flush()

    health = evaluate_source_health(db, source, now=now)

    assert health.status == "degraded"
    assert health.source_lag_hours == 30
    assert any("source watermark" in reason for reason in health.reasons)


def test_health_keeps_latest_failure_critical(db):
    source = _source(db)
    now = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    db.add_all([
        IngestionRun(
            organization_id="default-org",
            source_id=source.id,
            status="completed",
            trigger="scheduled",
            started_at=now - timedelta(hours=3),
            completed_at=now - timedelta(hours=3) + timedelta(minutes=5),
            records_seen=100,
            records_inserted=100,
            records_failed=0,
        ),
        IngestionRun(
            organization_id="default-org",
            source_id=source.id,
            status="failed",
            trigger="scheduled",
            started_at=now - timedelta(hours=1),
            completed_at=now - timedelta(hours=1) + timedelta(minutes=2),
            records_seen=100,
            records_failed=100,
        ),
    ])
    db.flush()

    health = evaluate_source_health(db, source, now=now)

    assert health.status == "critical"
    assert health.run_failure_rate == 0.5
    assert any("Run failure rate" in reason for reason in health.reasons)


def test_ingestion_candidates_endpoint_returns_structured_queue(client):
    response = client.get("/ingestion/candidates")

    assert response.status_code == 200, response.text
    body = response.json()
    assert {row["key"] for row in body} == {
        "bend_or_planning_applications",
        "bend_or_permit_applications_point",
        "bend_or_permit_applications_line",
        "washington_state_lcb_local_authority_letters",
        "orlando_fl_planning_applications",
        "atlanta_ga_building_permit_tracker",
        "phoenix_az_plan_review_and_permits",
        "huntsville_al_issued_building_permits",
        "birmingham_al_digital_plan_room",
        "mobile_al_build_mobile_portal",
        "evansville_in_building_commission_permits",
    }
    bend_planning = next(row for row in body if row["key"] == "bend_or_planning_applications")
    assert bend_planning["status"] == "operational_retry"
    assert bend_planning["can_run_canary"] is True
    bend_permits = next(row for row in body if row["key"] == "bend_or_permit_applications_point")
    assert bend_permits["status"] == "operational_retry"
    assert bend_permits["can_run_canary"] is True
    bend_lines = next(row for row in body if row["key"] == "bend_or_permit_applications_line")
    assert bend_lines["status"] == "operational_retry"
    assert bend_lines["can_run_canary"] is True
    lcb = next(row for row in body if row["key"] == "washington_state_lcb_local_authority_letters")
    assert lcb["status"] == "operational_retry"
    assert lcb["can_run_canary"] is True
    assert lcb["last_checked_on"] == "2026-07-18"
    assert lcb["next_audit_on"] == "2026-07-25"


def test_ingestion_candidates_endpoint_filters_by_state(client):
    response = client.get("/ingestion/candidates?state=Oregon")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body
    assert all(row["jurisdiction"] == "Bend, OR" for row in body)
    assert {row["key"] for row in body} == {
        "bend_or_planning_applications",
        "bend_or_permit_applications_point",
        "bend_or_permit_applications_line",
    }


def test_candidate_canary_endpoint_runs_retry_probe(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.ingestion.validate_candidate_source_canary",
        lambda candidate, sample_size: CandidateCanaryResult(
            candidate_key=candidate.key,
            candidate_name=candidate.name,
            ok=True,
            records_fetched=1,
            records_valid=1,
            records_failed=0,
            approval_stages={"pre_approval": 1},
            sample_record_ids=["ABC-1"],
            next_checkpoint={"offset": 1},
            errors=[],
        ),
    )

    response = client.post(
        "/ingestion/candidates/washington_state_lcb_local_authority_letters/canary",
        json={"sample_size": 1},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["candidate_key"] == "washington_state_lcb_local_authority_letters"
    assert body["ok"] is True
    assert body["approval_stages"] == {"pre_approval": 1}

    history = client.get("/ingestion/candidates/washington_state_lcb_local_authority_letters/canary-history")
    assert history.status_code == 200, history.text
    rows = history.json()
    assert len(rows) == 1
    assert rows[0]["candidate_key"] == "washington_state_lcb_local_authority_letters"
    assert rows[0]["ok"] is True


def test_candidate_canary_endpoint_rejects_unrunnable_candidates(client):
    response = client.post(
        "/ingestion/candidates/orlando_fl_planning_applications/canary",
        json={"sample_size": 1},
    )

    assert response.status_code == 422, response.text
    assert "operational_retry" in response.json()["detail"]


def test_ingestion_candidates_endpoint_includes_latest_canary_summary(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.ingestion.validate_candidate_source_canary",
        lambda candidate, sample_size: CandidateCanaryResult(
            candidate_key=candidate.key,
            candidate_name=candidate.name,
            ok=False,
            records_fetched=1,
            records_valid=0,
            records_failed=1,
            approval_stages={},
            sample_record_ids=[],
            next_checkpoint=None,
            errors=["sample failed"],
        ),
    )
    client.post(
        "/ingestion/candidates/washington_state_lcb_local_authority_letters/canary",
        json={"sample_size": 1},
    )

    response = client.get("/ingestion/candidates")
    assert response.status_code == 200, response.text
    body = response.json()
    lcb = next(row for row in body if row["key"] == "washington_state_lcb_local_authority_letters")
    assert lcb["last_canary_ok"] is False
    assert lcb["last_canary_records_valid"] == 0
    assert lcb["last_canary_records_failed"] == 1
    assert lcb["last_canary_at"] is not None


def test_ingestion_candidates_endpoint_uses_most_recent_canary_attempt(client, monkeypatch):
    outcomes = iter([False, True])

    def fake_validate(candidate, sample_size):
        ok = next(outcomes)
        return CandidateCanaryResult(
            candidate_key=candidate.key,
            candidate_name=candidate.name,
            ok=ok,
            records_fetched=1,
            records_valid=1 if ok else 0,
            records_failed=0 if ok else 1,
            approval_stages={"pre_approval": 1} if ok else {},
            sample_record_ids=["ABC-1"] if ok else [],
            next_checkpoint=None,
            errors=[] if ok else ["sample failed"],
        )

    monkeypatch.setattr("app.routes.ingestion.validate_candidate_source_canary", fake_validate)
    client.post(
        "/ingestion/candidates/washington_state_lcb_local_authority_letters/canary",
        json={"sample_size": 1},
    )
    client.post(
        "/ingestion/candidates/washington_state_lcb_local_authority_letters/canary",
        json={"sample_size": 1},
    )

    response = client.get("/ingestion/candidates")
    assert response.status_code == 200, response.text
    body = response.json()
    lcb = next(row for row in body if row["key"] == "washington_state_lcb_local_authority_letters")
    assert lcb["last_canary_ok"] is True
    assert lcb["last_canary_records_valid"] == 1
    assert lcb["last_canary_records_failed"] == 0


def test_ingestion_coverage_endpoint_reports_catalog_footprint(client):
    response = client.get("/ingestion/coverage")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["live_source_count"] == len(load_catalog())
    assert body["candidate_count"] == len(load_candidate_catalog())
    assert body["jurisdiction_count"] > 0
    assert body["pre_approval_source_count"] > 0
    assert body["approved_only_source_count"] > 0
    assert body["retailer_opening_source_count"] == 2
    assert {row["source_key"] for row in body["retailer_opening_sources"]} == {
        "texas_comptroller_sales_tax_locations",
        "washington_dc_basic_business_licenses_retail_openings",
    }
    assert body["approved_only_sources"]
    assert any(row["source_key"] == "detroit_mi_bseed_building_permits" for row in body["approved_only_sources"])
    assert body["top_jurisdictions"]
    assert body["state_buckets"]
    assert body["activation_queue"]
    assert len(body["candidate_only_states"]) == body["candidate_only_state_count"]
    assert [bucket["state"] for bucket in body["activation_queue"]] == body["candidate_only_states"]
    assert body["covered_state_count"] + body["missing_state_count"] == 50
    assert len(body["covered_states"]) == body["covered_state_count"]
    assert len(body["missing_states"]) == body["missing_state_count"]


def test_ingestion_candidate_promotion_creates_source_with_probe_context(client):
    candidate = next(entry for entry in load_candidate_catalog() if entry.status == "operational_retry")

    response = client.post(f"/ingestion/candidates/{candidate.key}/promote")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["key"] == candidate.key
    assert body["name"] == candidate.name
    assert body["is_active"] is True
    assert body["settings"]["candidate_key"] == candidate.key
    assert body["settings"]["candidate_status"] == candidate.status
    assert body["settings"]["reconciliation_mode"] == "candidate_promoted"
    assert body["field_mappings"]

    sources = client.get("/ingestion/sources").json()
    promoted = next(source for source in sources if source["key"] == candidate.key)
    assert promoted["id"] == body["id"]
