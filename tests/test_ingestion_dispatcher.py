from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, configure_sqlite_foreign_keys
from app.models.ingestion import IngestionRun, IngestionSource
from app.models.ingestion_onboarding import (
    OrganizationIngestionEnrollment,
    OrganizationIngestionEnrollmentSource,
)
from app.models.organization import Organization
from app.services.ingestion import dispatcher
from app.services.ingestion.dispatcher import (
    _claim_enrollment_source,
    dispatch_enrolled_ingestion,
)
from app.utils.org_scope import get_org_id

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def _session_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / f'dispatch-{uuid4().hex}.db'}",
        connect_args={"check_same_thread": False},
    )
    configure_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine), engine


def _add_enrollment(
    session_factory,
    *,
    organization_id: str,
    source_key: str,
    status: str = "active",
    next_run_at: datetime | None = NOW,
    lease_expires_at: datetime | None = None,
) -> str:
    db = session_factory()
    try:
        organization = db.get(Organization, organization_id)
        if organization is None:
            db.add(
                Organization(
                    id=organization_id,
                    name=organization_id,
                    slug=organization_id,
                    is_active=True,
                )
            )
            db.flush()
        enrollment = db.get(OrganizationIngestionEnrollment, organization_id)
        if enrollment is None:
            db.add(
                OrganizationIngestionEnrollment(
                    organization_id=organization_id,
                    enabled=True,
                    coverage_mode="selected_states",
                    state_codes=["TX"],
                    record_types=["permit"],
                    rollout_waves=[1],
                    shard_count=1,
                    catalog_manifest_digest="a" * 64,
                    last_catalog_sync_at=NOW,
                )
            )
            db.flush()
        source = IngestionSource(
            organization_id=organization_id,
            key=source_key,
            name=source_key,
            adapter="arcgis",
            record_type="permit",
            jurisdiction="Example, TX",
            base_url="https://example.test/arcgis",
            settings={},
            is_active=True,
        )
        db.add(source)
        db.flush()
        row = OrganizationIngestionEnrollmentSource(
            organization_id=organization_id,
            ingestion_source_id=source.id,
            source_key=source_key,
            state_code="TX",
            record_type="permit",
            status=status,
            cadence_minutes=60,
            max_pages_per_run=3,
            next_run_at=next_run_at,
            lease_token="existing" if lease_expires_at else None,
            lease_expires_at=lease_expires_at,
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _run(status: str = "completed", error: str | None = None):
    def execute(db, source, **kwargs):
        return IngestionRun(
            id=str(uuid4()),
            organization_id=source.organization_id,
            source_id=source.id,
            status=status,
            trigger=kwargs["trigger"],
            heartbeat_at=NOW,
            error_message=error,
        )

    return execute


def test_dispatches_each_organization_in_an_isolated_context(tmp_path):
    sessions, engine = _session_factory(tmp_path)
    _add_enrollment(sessions, organization_id="org-a", source_key="source-a")
    _add_enrollment(sessions, organization_id="org-b", source_key="source-b")
    observed: list[tuple[str, str]] = []

    def execute(db, source, **_kwargs):
        observed.append((get_org_id(), source.organization_id))
        if source.key == "source-a":
            raise RuntimeError("upstream unavailable")
        return _run()(db, source, trigger="customer_dispatch")

    result = dispatch_enrolled_ingestion(
        session_factory=sessions,
        allowed_source_keys={"source-a", "source-b"},
        now=lambda: NOW,
        run_source=execute,
    )

    assert observed == [("org-a", "org-a"), ("org-b", "org-b")]
    assert result.organizations_dispatched == 2
    assert result.sources_claimed == 2
    assert result.sources_failed == 1
    assert result.sources_succeeded == 1
    engine.dispose()


def test_dispatches_only_due_active_reviewed_sources(tmp_path):
    sessions, engine = _session_factory(tmp_path)
    _add_enrollment(sessions, organization_id="org", source_key="due")
    _add_enrollment(sessions, organization_id="org", source_key="paused", status="paused")
    _add_enrollment(sessions, organization_id="org", source_key="manual", status="manual")
    _add_enrollment(
        sessions,
        organization_id="org",
        source_key="future",
        next_run_at=NOW + timedelta(hours=1),
    )
    _add_enrollment(
        sessions,
        organization_id="org",
        source_key="leased",
        lease_expires_at=NOW + timedelta(minutes=30),
    )
    _add_enrollment(sessions, organization_id="org", source_key="not-reviewed")
    observed: list[str] = []

    def execute(db, source, **kwargs):
        observed.append(source.key)
        return _run()(db, source, **kwargs)

    result = dispatch_enrolled_ingestion(
        session_factory=sessions,
        allowed_source_keys={"due", "paused", "manual", "future", "leased"},
        now=lambda: NOW,
        run_source=execute,
    )

    assert observed == ["due"]
    assert result.sources_due == 1
    assert result.sources_succeeded == 1
    engine.dispose()


def test_plan_only_does_not_claim_or_execute(tmp_path):
    sessions, engine = _session_factory(tmp_path)
    row_id = _add_enrollment(sessions, organization_id="org", source_key="source")
    called = False

    def execute(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("plan-only dispatch executed a source")

    result = dispatch_enrolled_ingestion(
        session_factory=sessions,
        allowed_source_keys={"source"},
        plan_only=True,
        now=lambda: NOW,
        run_source=execute,
    )

    db = sessions()
    row = db.get(OrganizationIngestionEnrollmentSource, row_id)
    assert result.sources_due == 1
    assert result.sources_claimed == 0
    assert result.source_results[0].outcome == "planned"
    assert called is False
    assert row.lease_token is None
    assert row.last_dispatched_at is None
    db.close()
    engine.dispose()


def test_failure_backoff_and_success_reset_source_state(tmp_path):
    sessions, engine = _session_factory(tmp_path)
    row_id = _add_enrollment(sessions, organization_id="org", source_key="source")

    failed = dispatch_enrolled_ingestion(
        session_factory=sessions,
        allowed_source_keys={"source"},
        now=lambda: NOW,
        run_source=_run("failed", "provider timeout"),
    )
    db = sessions()
    row = db.get(OrganizationIngestionEnrollmentSource, row_id)
    assert failed.sources_failed == 1
    assert row.consecutive_failures == 1
    assert row.last_error == "provider timeout"
    assert row.next_run_at.replace(tzinfo=timezone.utc) == NOW + timedelta(minutes=15)
    row.next_run_at = NOW
    db.commit()
    db.close()

    succeeded = dispatch_enrolled_ingestion(
        session_factory=sessions,
        allowed_source_keys={"source"},
        now=lambda: NOW,
        run_source=_run(),
    )
    db = sessions()
    row = db.get(OrganizationIngestionEnrollmentSource, row_id)
    assert succeeded.sources_succeeded == 1
    assert row.consecutive_failures == 0
    assert row.last_error is None
    assert row.last_completed_at.replace(tzinfo=timezone.utc) == NOW
    assert row.next_run_at.replace(tzinfo=timezone.utc) == NOW + timedelta(minutes=60)
    db.close()
    engine.dispose()


def test_claim_is_atomic_across_workers(tmp_path):
    sessions, engine = _session_factory(tmp_path)
    row_id = _add_enrollment(sessions, organization_id="org", source_key="source")
    first = sessions()
    second = sessions()
    try:
        claimed = _claim_enrollment_source(
            first,
            row_id=row_id,
            organization_id="org",
            as_of=NOW,
            lease_token="worker-one",
            lease_seconds=600,
        )
        lost = _claim_enrollment_source(
            second,
            row_id=row_id,
            organization_id="org",
            as_of=NOW,
            lease_token="worker-two",
            lease_seconds=600,
        )
        assert claimed is not None
        assert claimed.lease_token == "worker-one"
        assert lost is None
    finally:
        first.close()
        second.close()
        engine.dispose()


def test_global_and_per_organization_limits_bound_dispatch(tmp_path):
    sessions, engine = _session_factory(tmp_path)
    for index in range(3):
        _add_enrollment(
            sessions,
            organization_id="org-a",
            source_key=f"a-{index}",
        )
        _add_enrollment(
            sessions,
            organization_id="org-b",
            source_key=f"b-{index}",
        )

    result = dispatch_enrolled_ingestion(
        session_factory=sessions,
        allowed_source_keys={*(f"a-{index}" for index in range(3)), *(f"b-{index}" for index in range(3))},
        max_sources=3,
        max_sources_per_organization=2,
        now=lambda: NOW,
        run_source=_run(),
    )

    assert result.sources_claimed == 3
    assert [item.source_key for item in result.source_results] == ["a-0", "a-1", "b-0"]
    engine.dispose()


def test_wall_clock_limit_stops_before_claim(monkeypatch, tmp_path):
    sessions, engine = _session_factory(tmp_path)
    _add_enrollment(sessions, organization_id="org", source_key="source")
    ticks = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(dispatcher, "monotonic", lambda: next(ticks))

    result = dispatch_enrolled_ingestion(
        session_factory=sessions,
        allowed_source_keys={"source"},
        wall_clock_seconds=1,
        now=lambda: NOW,
        run_source=_run(),
    )

    assert result.deadline_reached is True
    assert result.sources_claimed == 0
    assert result.source_results[0].outcome == "deadline"
    engine.dispose()


def test_lost_lease_cannot_be_completed_by_stale_worker(tmp_path):
    sessions, engine = _session_factory(tmp_path)
    row_id = _add_enrollment(sessions, organization_id="org", source_key="source")

    def steal_lease(db, source, **kwargs):
        row = db.get(OrganizationIngestionEnrollmentSource, row_id)
        row.lease_token = "replacement-worker"
        db.commit()
        return _run()(db, source, **kwargs)

    result = dispatch_enrolled_ingestion(
        session_factory=sessions,
        allowed_source_keys={"source"},
        now=lambda: NOW,
        run_source=steal_lease,
    )

    db = sessions()
    row = db.get(OrganizationIngestionEnrollmentSource, row_id)
    assert result.source_results[0].outcome == "lease_lost"
    assert row.lease_token == "replacement-worker"
    assert row.last_completed_at is None
    db.close()
    engine.dispose()


def test_stale_enrollment_manifest_is_blocked_before_claim(tmp_path):
    sessions, engine = _session_factory(tmp_path)
    row_id = _add_enrollment(sessions, organization_id="org", source_key="source")

    result = dispatch_enrolled_ingestion(
        session_factory=sessions,
        allowed_source_keys={"source"},
        catalog_manifest_digest="b" * 64,
        now=lambda: NOW,
        run_source=_run(),
    )

    db = sessions()
    row = db.get(OrganizationIngestionEnrollmentSource, row_id)
    enrollment = db.get(OrganizationIngestionEnrollment, "org")
    assert result.sources_failed == 1
    assert result.sources_claimed == 0
    assert row.lease_token is None
    assert "manifest" in enrollment.last_error
    db.close()
    engine.dispose()
