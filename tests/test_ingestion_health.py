from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.ingestion import (
    IngestionCandidateCanaryAttempt,
    IngestionRun,
    IngestionSource,
    RawSourceRecord,
    SourceFieldMapping,
)
from app.schemas.ingestion import FieldMappingCreate, IngestionSourceCreate
from app.schemas.ingestion_candidate import IngestionSourceCandidate
from app.services.ingestion.catalog import (
    load_candidate_catalog,
    load_catalog,
    summarize_coverage,
    sync_catalog,
)
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


def _retry_candidate() -> IngestionSourceCandidate:
    return IngestionSourceCandidate(
        key="test_retry_candidate",
        name="Test Retry Candidate",
        adapter="csv",
        record_type="permit",
        jurisdiction="Test, OR",
        base_url="https://example.test/retry.csv",
        official_landing_page="https://example.test/retry",
        license="Test License",
        status="operational_retry",
        blocker_summary="Awaiting operational validation.",
        early_warning_value="Test pre-approval records.",
        candidate_source_fields=["id"],
        probe_settings={
            "connector": {"source": "https://example.test/retry.csv", "page_size": 5},
            "defaults": {"state": "OR", "approval_stage": "pre_approval"},
        },
        probe_field_mappings=[
            {"source_field": "id", "canonical_field": "source_record_id"}
        ],
        last_checked_on=date(2026, 7, 1),
        next_audit_on=date(2026, 7, 30),
        notes="Test retry candidate.",
    )


def _install_retry_candidate(monkeypatch) -> IngestionSourceCandidate:
    candidate = _retry_candidate()
    monkeypatch.setattr(
        "app.routes.ingestion.load_candidate_catalog", lambda *args, **kwargs: [candidate]
    )
    monkeypatch.setattr(
        "app.services.ingestion.catalog.load_candidate_catalog",
        lambda *args, **kwargs: [candidate],
    )
    return candidate


def _reviewed_source(candidate: IngestionSourceCandidate) -> IngestionSourceCreate:
    return IngestionSourceCreate(
        key=candidate.key,
        name=f"{candidate.name} production",
        adapter=candidate.adapter,
        record_type=candidate.record_type,
        jurisdiction=candidate.jurisdiction,
        base_url=candidate.base_url,
        settings={
            "candidate_key": candidate.key,
            "candidate_status": "approved_for_production",
            "official_landing_page": candidate.official_landing_page,
            "license": candidate.license,
            "reconciliation_mode": "daily_incremental",
            "signal_stage": "pre_approval_and_approved",
            "connector": {"page_size": 250},
        },
        field_mappings=[
            FieldMappingCreate(
                source_field="id",
                canonical_field="source_record_id",
                is_required=True,
            )
        ],
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


def test_coverage_builds_a_50_state_clustered_rollout_queue():
    coverage = summarize_coverage()

    assert len(coverage.rollout_queue) == 50
    by_state = {item.state: item for item in coverage.rollout_queue}
    assert by_state["TX"].rollout_cluster == 1
    assert by_state["WA"].rollout_cluster == 1
    assert by_state["CA"].rollout_cluster == 2
    assert by_state["CO"].rollout_cluster == 3
    assert by_state["AK"].rollout_cluster == 4
    assert by_state["TX"].jurisdiction_count > 0
    assert by_state["TX"].next_action in {
        "run_candidate_canary",
        "add_pre_approval_source",
        "add_retailer_opening_source",
        "add_secondary_jurisdiction",
    }
    assert by_state["AK"].next_action == "resolve_candidate_blocker"


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
        "freshness_semantics": "record_updated_at",
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
        "freshness_semantics": "record_updated_at",
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
    assert "Latest canary publisher record update is 54.0 hours old" in result.errors[0]


def test_canary_accepts_old_filing_event_from_quiet_source(db, monkeypatch):
    source = _source(db)
    now = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)
    source.settings = {
        **source.settings,
        "freshness_field": "filed_at",
        "freshness_sla_hours": 24,
        "freshness_semantics": "filing_event_at",
    }
    monkeypatch.setattr(
        "app.services.ingestion.health.build_connector",
        lambda adapter, config: FakeConnector([
            {
                "id": "quiet-filing",
                "stage": "pre_approval",
                "filed_at": "2026-06-01T12:00:00.000",
            }
        ]),
    )

    result = validate_source_canary(source, sample_size=1, now=now)

    assert result.ok is True
    assert result.errors == []


def test_canary_freshness_probe_allows_stable_main_pagination(db, monkeypatch):
    source = _source(db)
    now = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)
    source.settings = {
        **source.settings,
        "freshness_field": "updated_at",
        "freshness_sla_hours": 24,
        "freshness_semantics": "record_updated_at",
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
        "freshness_semantics": "record_updated_at",
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
    assert "freshness_probe: Latest canary publisher record update is 54.0 hours old" in result.errors[0]


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
    assert response.json()["freshness_sla_hours"] == 36
    assert response.json()["freshness_sla_configured"] is False
    assert response.json()["freshness_semantics"] == "ingestion_observed_at"
    assert response.json()["source_watermark_enforced"] is False
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
    source.settings = {
        **(source.settings or {}),
        "freshness_sla_hours": 24,
        "freshness_semantics": "record_updated_at",
    }
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
    assert health.freshness_sla_hours == 24
    assert health.freshness_sla_configured is True
    assert health.freshness_semantics == "record_updated_at"
    assert health.freshness_label == "Publisher record update"
    assert health.source_watermark_enforced is True
    assert any("Publisher record update" in reason for reason in health.reasons)


def test_health_uses_collection_sla_independently_from_publisher_freshness(db):
    source = _source(db)
    now = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    source.settings = {
        **(source.settings or {}),
        "collection_interval_minutes": 30 * 24 * 60,
        "freshness_sla_hours": 24,
        "freshness_semantics": "filing_event_at",
    }
    db.add(IngestionRun(
        organization_id="default-org",
        source_id=source.id,
        status="completed",
        trigger="scheduled",
        started_at=now - timedelta(days=2),
        completed_at=now - timedelta(days=2) + timedelta(minutes=5),
        records_seen=1,
        records_failed=0,
    ))
    db.flush()

    health = evaluate_source_health(db, source, now=now)

    assert health.status == "healthy"
    assert health.collection_sla_hours == 720
    assert health.collection_sla_configured is False


def test_health_does_not_treat_quiet_filing_activity_as_source_failure(db):
    source = _source(db)
    now = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    source.settings = {
        **(source.settings or {}),
        "freshness_sla_hours": 24,
        "freshness_semantics": "filing_event_at",
    }
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
        external_record_id="quiet-filing",
        record_type="permit",
        content_hash="quiet-filing",
        payload={"id": "quiet-filing"},
        source_updated_at=now - timedelta(days=30),
        received_at=now - timedelta(minutes=55),
    ))
    db.flush()

    health = evaluate_source_health(db, source, now=now)

    assert health.status == "healthy"
    assert health.source_lag_hours == 720
    assert health.freshness_label == "Latest filing event"
    assert health.source_watermark_enforced is False


def test_health_labels_legacy_and_invalid_custom_semantics_as_unclassified(db):
    source = _source(db)
    now = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    source.settings = {
        **(source.settings or {}),
        "freshness_field": "updated_at",
        "freshness_sla_hours": 24,
        "freshness_semantics": "publisher_magic_clock",
    }
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
        external_record_id="legacy",
        record_type="permit",
        content_hash="legacy",
        payload={"id": "legacy"},
        source_updated_at=now - timedelta(hours=30),
        received_at=now - timedelta(minutes=55),
    ))
    db.flush()

    health = evaluate_source_health(db, source, now=now)

    assert health.status == "degraded"
    assert health.freshness_semantics == "unclassified_source_timestamp"
    assert health.freshness_label == "Unclassified publisher timestamp"
    assert health.source_watermark_enforced is True


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
        "savannah_ga_commercial_building_permits",
        "detroit_mi_bseed_building_plan_reviews",
        "san_marcos_tx_planning_application_notices",
        "taylor_tx_development_notices",
        "orlando_fl_planning_applications",
        "atlanta_ga_building_permit_tracker",
        "phoenix_az_plan_review_and_permits",
        "huntsville_al_issued_building_permits",
        "birmingham_al_digital_plan_room",
        "mobile_al_build_mobile_portal",
        "evansville_in_building_commission_permits",
        "bend_or_permit_applications_line",
        "bend_or_permit_applications_point",
        "bend_or_planning_applications",
        "anchorage_ak_bsd_permit_lookup",
        "juneau_ak_civic_access_permits",
        "honolulu_hi_building_permits_2005_2025",
        "boise_id_development_tracker",
        "cedar_rapids_ia_building_permits",
        "biloxi_ms_development_review_agendas",
        "bozeman_mt_active_planning_projects",
        "bernalillo_county_nm_accela_permits",
        "tulsa_ok_development_plans",
        "charleston_wv_energov_permits",
        "cheyenne_wy_opengov_permits",
        "dallas_tx_legistar_planning_agendas",
        "madison_wi_legistar_plan_commission",
        "arapahoe_county_co_legistar_planning",
        "maricopa_county_az_planning_zoning_agendas",
        "jacksonville_fl_planning_commission_agendas",
        "hillsborough_county_fl_legistar_land_use",
        "san_jose_ca_planning_director_hearings",
        "san_jose_ca_large_energy_projects",
    }
    assert all(
        row["catalog_backed"]
        for row in body
        if row["key"].startswith("bend_or_")
    )
    savannah = next(
        row for row in body
        if row["key"] == "savannah_ga_commercial_building_permits"
    )
    assert savannah["status"] == "operational_retry"
    assert savannah["can_run_canary"] is True
    assert savannah["catalog_backed"] is True


def test_ingestion_candidates_endpoint_filters_by_state(client):
    response = client.get("/ingestion/candidates?state=Oregon")

    assert response.status_code == 200, response.text
    body = response.json()
    assert {row["key"] for row in body} == {
        "bend_or_permit_applications_line",
        "bend_or_permit_applications_point",
        "bend_or_planning_applications",
    }
    assert all(row["catalog_backed"] for row in body)


def test_candidate_canary_endpoint_runs_retry_probe(client, monkeypatch):
    candidate = _install_retry_candidate(monkeypatch)
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
        f"/ingestion/candidates/{candidate.key}/canary",
        json={"sample_size": 1},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["candidate_key"] == candidate.key
    assert body["ok"] is True
    assert body["approval_stages"] == {"pre_approval": 1}

    history = client.get(f"/ingestion/candidates/{candidate.key}/canary-history")
    assert history.status_code == 200, history.text
    rows = history.json()
    assert len(rows) == 1
    assert rows[0]["candidate_key"] == candidate.key
    assert rows[0]["ok"] is True


def test_candidate_canary_endpoint_rejects_unrunnable_candidates(client):
    response = client.post(
        "/ingestion/candidates/orlando_fl_planning_applications/canary",
        json={"sample_size": 1},
    )

    assert response.status_code == 422, response.text
    assert "operational_retry" in response.json()["detail"]


def test_ingestion_candidates_endpoint_includes_latest_canary_summary(client, monkeypatch):
    candidate = _install_retry_candidate(monkeypatch)
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
        f"/ingestion/candidates/{candidate.key}/canary",
        json={"sample_size": 1},
    )

    response = client.get("/ingestion/candidates")
    assert response.status_code == 200, response.text
    body = response.json()
    bend = next(row for row in body if row["key"] == candidate.key)
    assert bend["last_canary_ok"] is False
    assert bend["last_canary_records_valid"] == 0
    assert bend["last_canary_records_failed"] == 1
    assert bend["last_canary_at"] is not None


def test_ingestion_candidates_endpoint_uses_most_recent_canary_attempt(client, monkeypatch):
    candidate = _install_retry_candidate(monkeypatch)
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
        f"/ingestion/candidates/{candidate.key}/canary",
        json={"sample_size": 1},
    )
    client.post(
        f"/ingestion/candidates/{candidate.key}/canary",
        json={"sample_size": 1},
    )

    response = client.get("/ingestion/candidates")
    assert response.status_code == 200, response.text
    body = response.json()
    bend = next(row for row in body if row["key"] == candidate.key)
    assert bend["last_canary_ok"] is True
    assert bend["last_canary_records_valid"] == 1
    assert bend["last_canary_records_failed"] == 0


def test_ingestion_coverage_endpoint_reports_active_catalog_footprint(client, db):
    sync_catalog(db, load_catalog())
    db.commit()
    response = client.get("/ingestion/coverage")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["live_source_count"] == len(load_catalog())
    assert body["candidate_count"] == len(load_candidate_catalog())
    assert body["jurisdiction_count"] > 0
    assert body["pre_approval_source_count"] > 0
    assert body["approved_only_source_count"] > 0
    assert body["retailer_opening_source_count"] == 4
    assert {row["source_key"] for row in body["retailer_opening_sources"]} == {
        "new_york_state_sla_pending_licenses",
        "texas_comptroller_sales_tax_locations",
        "washington_dc_basic_business_licenses_retail_openings",
        "washington_state_lcb_local_authority_letters",
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
    assert body["researched_state_count"] == 50
    assert body["unresearched_state_count"] == 0
    assert body["unresearched_states"] == []
    assert body["covered_state_count"] == 40
    assert body["missing_state_count"] == 10
    assert body["candidate_only_state_count"] == 10
    assert set(body["candidate_only_states"]) == {
        "AK", "HI", "IA", "ID", "MS", "MT", "NM", "OK", "WV", "WY",
    }
    assert set(body["missing_states"]) == set(body["candidate_only_states"])


def test_ingestion_coverage_prioritizes_activation_queue_by_readiness(monkeypatch):
    monkeypatch.setattr("app.services.ingestion.catalog.load_catalog", lambda: [])

    def candidate(key: str, jurisdiction: str, status: str):
        return SimpleNamespace(
            key=key,
            name=key.replace("_", " ").title(),
            adapter="test",
            record_type="permit",
            jurisdiction=jurisdiction,
            base_url="https://example.test",
            official_landing_page="https://example.test",
            license="Public",
            status=status,
            blocker_summary="blocked",
            early_warning_value="value",
            candidate_source_fields=[],
            probe_settings=None,
            probe_field_mappings=[],
            can_run_canary=False,
            last_checked_on=datetime(2026, 7, 1).date(),
            next_audit_on=datetime(2026, 7, 2).date(),
            notes="notes",
            model_dump=lambda: {"state": jurisdiction},
        )

    monkeypatch.setattr(
        "app.services.ingestion.catalog.load_candidate_catalog",
        lambda *args, **kwargs: [
            candidate("texas_retry", "Texas", "operational_retry"),
            candidate("florida_queue_1", "Florida", "queued"),
            candidate("florida_queue_2", "Florida", "queued"),
        ],
    )

    summary = summarize_coverage()

    assert [bucket.state for bucket in summary.activation_queue] == ["FL", "TX"]
    assert summary.activation_queue[0].priority_score > summary.activation_queue[1].priority_score
    assert summary.activation_queue[0].priority_reasons


def test_ingestion_candidate_promotion_requires_reviewed_catalog_manifest(client, monkeypatch):
    candidate = _install_retry_candidate(monkeypatch)
    coverage_before = client.get("/ingestion/coverage").json()
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
            next_checkpoint=None,
            errors=[],
        ),
    )
    canary = client.post(
        f"/ingestion/candidates/{candidate.key}/canary",
        json={"sample_size": 1},
    )
    assert canary.status_code == 200, canary.text

    response = client.post(f"/ingestion/candidates/{candidate.key}/promote")

    assert response.status_code == 409, response.text
    assert "reviewed production catalog manifest" in response.json()["detail"]
    assert candidate.key not in {
        source["key"] for source in client.get("/ingestion/sources").json()
    }
    coverage_after = client.get("/ingestion/coverage").json()
    assert coverage_after["live_source_count"] == coverage_before["live_source_count"]
    assert coverage_after["candidate_count"] == coverage_before["candidate_count"]


def test_ingestion_candidate_promotion_syncs_reviewed_catalog_source(client, monkeypatch):
    candidate = _install_retry_candidate(monkeypatch)
    reviewed = _reviewed_source(candidate)
    monkeypatch.setattr("app.routes.ingestion.load_catalog", lambda: [reviewed])
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
            next_checkpoint=None,
            errors=[],
        ),
    )
    canary = client.post(
        f"/ingestion/candidates/{candidate.key}/canary",
        json={"sample_size": 1},
    )
    assert canary.status_code == 200, canary.text

    candidates = client.get("/ingestion/candidates").json()
    row = next(row for row in candidates if row["key"] == candidate.key)
    assert row["catalog_backed"] is True

    response = client.post(f"/ingestion/candidates/{candidate.key}/promote")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["key"] == candidate.key
    assert body["name"] == reviewed.name
    assert body["is_active"] is True
    assert body["settings"]["candidate_key"] == candidate.key
    assert body["settings"]["candidate_status"] == "approved_for_production"
    assert body["settings"]["reconciliation_mode"] == "daily_incremental"
    assert body["settings"]["connector"]["page_size"] == 250
    assert body["field_mappings"]

    sources = client.get("/ingestion/sources").json()
    promoted = next(source for source in sources if source["key"] == candidate.key)
    assert promoted["id"] == body["id"]

    candidates = client.get("/ingestion/candidates").json()
    assert candidate.key not in {row["key"] for row in candidates}
    repeated = client.post(f"/ingestion/candidates/{candidate.key}/promote")
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["id"] == body["id"]


def test_ingestion_candidate_promotion_requires_successful_canary(client, monkeypatch):
    candidate = _install_retry_candidate(monkeypatch)

    response = client.post(f"/ingestion/candidates/{candidate.key}/promote")

    assert response.status_code == 422, response.text
    assert "successful persisted canary" in response.json()["detail"]


def test_ingestion_candidate_promotion_rejects_stale_successful_canary(
    client, db, monkeypatch
):
    candidate = _install_retry_candidate(monkeypatch)
    db.add(
        IngestionCandidateCanaryAttempt(
            organization_id="default-org",
            candidate_key=candidate.key,
            candidate_name=candidate.name,
            sample_size=1,
            ok=True,
            records_fetched=1,
            records_valid=1,
            records_failed=0,
            approval_stages={"pre_approval": 1},
            sample_record_ids=["ABC-1"],
            next_checkpoint=None,
            errors=[],
            created_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
        )
    )
    db.commit()

    response = client.post(f"/ingestion/candidates/{candidate.key}/promote")

    assert response.status_code == 422, response.text
    assert "current audit date" in response.json()["detail"]
