from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.ingestion import IngestionRun, IngestionSource
from app.services.ingestion.service import (
    ActiveRunConflict,
    RunLeaseLost,
    _claim_source_run,
    _commit_run_progress,
)


def test_two_sessions_cannot_claim_the_same_source(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'lease-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        source = IngestionSource(
            organization_id="default-org",
            key="lease_race",
            name="Lease race",
            adapter="csv",
            record_type="permit",
            is_active=True,
        )
        db.add(source)
        db.commit()
        source_id = source.id

    barrier = Barrier(2)

    def claim() -> str:
        with sessions() as db:
            barrier.wait()
            try:
                run = _claim_source_run(
                    db,
                    source_id,
                    checkpoint=None,
                    trigger="test",
                    parameters={"max_pages": 1},
                )
                return f"claimed:{run.id}"
            except ActiveRunConflict:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: claim(), range(2)))

    with sessions() as db:
        running = db.query(IngestionRun).filter(
            IngestionRun.source_id == source_id,
            IngestionRun.status == "running",
        ).all()

    assert sum(result.startswith("claimed:") for result in results) == 1
    assert results.count("conflict") == 1
    assert len(running) == 1
    engine.dispose()


def test_lost_lease_rolls_back_pending_worker_changes(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'lease-fence.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as setup:
        source = IngestionSource(
            organization_id="default-org",
            key="lease_fence",
            name="Original name",
            adapter="csv",
            record_type="permit",
            is_active=True,
        )
        setup.add(source)
        setup.commit()
        source_id = source.id

    with sessions() as worker:
        run = _claim_source_run(
            worker,
            source_id,
            checkpoint=None,
            trigger="test",
            parameters={"max_pages": 1},
        )
        with sessions() as reclaimer:
            reclaimed = reclaimer.get(IngestionRun, run.id)
            reclaimed.status = "failed"
            reclaimer.commit()

        worker_source = worker.get(IngestionSource, source_id)
        worker_source.name = "Must roll back"
        with pytest.raises(RunLeaseLost):
            _commit_run_progress(
                worker,
                run.id,
                checkpoint={"offset": 10},
                records_seen=1,
                records_inserted=1,
                records_updated=0,
                records_failed=0,
                error_message=None,
            )

    with sessions() as verify:
        assert verify.get(IngestionSource, source_id).name == "Original name"
    engine.dispose()


def test_claim_source_run_uses_configurable_stale_window(db):
    source = IngestionSource(
        organization_id="default-org",
        key="configurable_lease",
        name="Configurable lease",
        adapter="csv",
        record_type="permit",
        is_active=True,
    )
    db.add(source)
    db.flush()
    run = IngestionRun(
        organization_id="default-org",
        source_id=source.id,
        status="running",
        trigger="test",
        heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    db.add(run)
    db.commit()

    with pytest.raises(ActiveRunConflict):
        _claim_source_run(
            db,
            source.id,
            checkpoint=None,
            trigger="test",
            parameters={"max_pages": 1},
            stale_after=timedelta(minutes=5),
        )

    reclaimed = _claim_source_run(
        db,
        source.id,
        checkpoint=None,
        trigger="test",
        parameters={"max_pages": 1},
        stale_after=timedelta(minutes=1),
    )

    assert reclaimed.status == "running"
    assert db.get(IngestionRun, run.id).status == "failed"


def test_claim_source_run_rejects_non_positive_stale_window(db):
    source = IngestionSource(
        organization_id="default-org",
        key="bad_lease_window",
        name="Bad lease window",
        adapter="csv",
        record_type="permit",
        is_active=True,
    )
    db.add(source)
    db.flush()

    with pytest.raises(ValueError, match="stale_after must be positive"):
        _claim_source_run(
            db,
            source.id,
            checkpoint=None,
            trigger="test",
            parameters={"max_pages": 1},
            stale_after=timedelta(seconds=0),
        )
