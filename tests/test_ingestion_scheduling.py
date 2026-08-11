from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.ingestion import IngestionRun, IngestionSource
from app.services.ingestion.catalog import load_catalog
from app.services.ingestion.scheduling import (
    build_schedule_plan,
    source_schedule_policy,
    source_shard,
)

NOW = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)


def _source(
    db,
    key: str,
    *,
    refresh_frequency: str = "daily",
    settings: dict | None = None,
) -> IngestionSource:
    source_settings = {"refresh_frequency": refresh_frequency}
    source_settings.update({
        "collection_interval_minutes": 24 * 60,
        "retry_interval_minutes": 60,
        "schedule_mode": "automatic",
    })
    source_settings.update(settings or {})
    source_settings.setdefault(
        "collection_sla_hours",
        source_settings["collection_interval_minutes"] / 60,
    )
    source = IngestionSource(
        organization_id="default-org",
        key=key,
        name=key.replace("_", " ").title(),
        adapter="csv",
        record_type="permit",
        settings=source_settings,
        is_active=True,
    )
    db.add(source)
    db.flush()
    return source


def _run(
    db,
    source: IngestionSource,
    *,
    started_at: datetime,
    status: str = "completed",
    trigger: str = "scheduled",
) -> IngestionRun:
    run = IngestionRun(
        organization_id="default-org",
        source_id=source.id,
        status=status,
        trigger=trigger,
        started_at=started_at,
        heartbeat_at=started_at,
        completed_at=started_at + timedelta(minutes=5) if status != "running" else None,
    )
    db.add(run)
    db.flush()
    return run


def test_never_run_source_is_due_and_uses_policy_overrides(db):
    source = _source(
        db,
        "never_run",
        settings={
            "collection_interval_minutes": 90,
            "max_pages_per_run": 4,
            "collection_priority": 80,
        },
    )

    plan = build_schedule_plan(db, [source], as_of=NOW)

    assert plan.due_source_count == 1
    item = plan.items[0]
    assert item.due is True
    assert item.due_reason == "never_run"
    assert item.interval_minutes == 90
    assert item.max_pages_per_run == 4
    assert item.priority == 80
    assert item.schedule_mode == "automatic"


def test_due_boundary_uses_latest_non_canary_terminal_run(db):
    source = _source(db, "daily_source")
    _run(db, source, started_at=NOW - timedelta(days=3))
    _run(
        db,
        source,
        started_at=NOW - timedelta(hours=2),
        status="failed",
        trigger="canary",
    )
    latest = _run(db, source, started_at=NOW - timedelta(days=1, minutes=5))

    before = build_schedule_plan(
        db,
        [source],
        as_of=latest.completed_at + timedelta(days=1) - timedelta(seconds=1),
    )
    at_boundary = build_schedule_plan(
        db,
        [source],
        as_of=latest.completed_at + timedelta(days=1),
    )

    assert before.items[0].due is False
    assert before.items[0].due_reason == "not_due"
    assert at_boundary.items[0].due is True
    assert at_boundary.items[0].due_reason == "interval_elapsed"


def test_monthly_source_is_not_collected_daily(db):
    source = _source(
        db,
        "monthly_source",
        refresh_frequency="monthly",
        settings={"collection_interval_minutes": 30 * 24 * 60},
    )
    latest = _run(db, source, started_at=NOW - timedelta(days=2))

    plan = build_schedule_plan(db, [source], as_of=NOW)

    assert plan.items[0].interval_minutes == 30 * 24 * 60
    assert plan.items[0].last_terminal_at == latest.completed_at
    assert plan.items[0].due is False


def test_fresh_active_run_is_visible_and_skipped(db):
    source = _source(db, "active_source")
    _run(db, source, started_at=NOW - timedelta(minutes=2), status="running")

    item = build_schedule_plan(db, [source], as_of=NOW).items[0]

    assert item.active_run is True
    assert item.stale_run is False
    assert item.due is False
    assert item.due_reason == "active_run"


def test_source_specific_stale_threshold_matches_run_claim_policy(db):
    source = _source(
        db,
        "long_lease_source",
        settings={"stale_run_after_seconds": 15 * 60},
    )
    _run(db, source, started_at=NOW - timedelta(minutes=10), status="running")

    item = build_schedule_plan(db, [source], as_of=NOW).items[0]

    assert item.active_run is True
    assert item.stale_run is False
    assert item.due is False


def test_stale_active_run_remains_due_for_atomic_reclaim(db):
    source = _source(db, "stale_source")
    _run(db, source, started_at=NOW - timedelta(minutes=10), status="running")

    item = build_schedule_plan(db, [source], as_of=NOW).items[0]

    assert item.active_run is False
    assert item.stale_run is True
    assert item.due is True
    assert item.due_reason == "stale_run"


def test_stale_active_run_is_due_even_after_recent_completion(db):
    source = _source(db, "stale_after_success")
    completed = _run(
        db, source, started_at=NOW - timedelta(hours=1), status="completed"
    )
    _run(db, source, started_at=NOW - timedelta(minutes=10), status="running")

    item = build_schedule_plan(db, [source], as_of=NOW).items[0]

    assert item.due is True
    assert item.due_reason == "stale_run"
    assert item.last_terminal_at == completed.completed_at


def test_partial_run_continues_immediately(db):
    source = _source(db, "partial_source")
    latest = _run(db, source, started_at=NOW - timedelta(minutes=1), status="partial")

    item = build_schedule_plan(db, [source], as_of=NOW).items[0]

    assert item.due is True
    assert item.due_reason == "continue_checkpoint"
    assert item.due_at == latest.completed_at


def test_failed_run_uses_retry_backoff_instead_of_collection_interval(db):
    source = _source(
        db,
        "annual_source",
        settings={
            "collection_interval_minutes": 365 * 24 * 60,
            "retry_interval_minutes": 60,
        },
    )
    latest = _run(db, source, started_at=NOW - timedelta(minutes=35), status="failed")

    waiting = build_schedule_plan(db, [source], as_of=NOW).items[0]
    due = build_schedule_plan(
        db,
        [source],
        as_of=latest.completed_at + timedelta(minutes=60),
    ).items[0]

    assert waiting.due is False
    assert waiting.due_reason == "retry_backoff"
    assert due.due is True
    assert due.due_reason == "retry_backoff_elapsed"


def test_manual_source_is_never_automatically_due(db):
    source = _source(db, "manual_source", settings={"schedule_mode": "manual"})

    item = build_schedule_plan(db, [source], as_of=NOW).items[0]

    assert item.due is False
    assert item.due_reason == "manual"


def test_shards_are_stable_complete_and_non_overlapping(db):
    sources = [_source(db, f"source_{index}") for index in range(25)]

    plans = [
        build_schedule_plan(
            db,
            sources,
            as_of=NOW,
            shard_count=4,
            shard_index=index,
        )
        for index in range(4)
    ]
    key_sets = [{item.source_key for item in plan.items} for plan in plans]

    assert set().union(*key_sets) == {source.key for source in sources}
    assert sum(len(keys) for keys in key_sets) == len(sources)
    assert all(
        not left.intersection(right)
        for index, left in enumerate(key_sets)
        for right in key_sets[index + 1 :]
    )
    assert all(
        source_shard(item.source_key, 4) == item.shard_index
        for plan in plans
        for item in plan.items
    )


def test_due_items_sort_by_priority_then_overdue_age(db):
    low = _source(db, "low", settings={"collection_priority": 10})
    high_new = _source(db, "high_new", settings={"collection_priority": 90})
    high_old = _source(db, "high_old", settings={"collection_priority": 90})
    _run(db, high_new, started_at=NOW - timedelta(days=2))
    _run(db, high_old, started_at=NOW - timedelta(days=4))

    plan = build_schedule_plan(db, [low, high_new, high_old], as_of=NOW)

    assert [item.source_key for item in plan.items] == ["high_old", "high_new", "low"]


def test_every_production_catalog_cadence_has_a_schedule_policy():
    policies = [source_schedule_policy(entry) for entry in load_catalog()]

    assert len(policies) == len(load_catalog())
    assert all(policy.interval_minutes > 0 for policy in policies)


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"collection_interval_minutes": 0}, "collection_interval_minutes"),
        ({"max_pages_per_run": 101}, "max_pages_per_run"),
        ({"collection_priority": -1}, "collection_priority"),
    ],
)
def test_policy_rejects_invalid_overrides(db, settings, message):
    source = _source(db, "invalid_policy", settings=settings)

    with pytest.raises(ValueError, match=message):
        source_schedule_policy(source)


def test_schedule_plan_endpoint_filters_state_and_catalog_boundary(
    client, db, monkeypatch
):
    texas = _source(db, "texas_source")
    texas.jurisdiction = "Austin, TX"
    california = _source(db, "california_source")
    california.jurisdiction = "Sacramento, CA"
    runtime_only = _source(db, "runtime_only")
    runtime_only.jurisdiction = "Dallas, TX"
    db.commit()
    monkeypatch.setattr(
        "app.routes.ingestion.load_catalog",
        lambda: [
            SimpleNamespace(
                key="texas_source", jurisdiction="Austin, TX",
                settings={
                    "collection_interval_minutes": 1440,
                    "collection_sla_hours": 24,
                    "retry_interval_minutes": 60,
                    "schedule_mode": "automatic",
                },
            ),
            SimpleNamespace(
                key="california_source", jurisdiction="Sacramento, CA",
                settings={
                    "collection_interval_minutes": 1440,
                    "collection_sla_hours": 24,
                    "retry_interval_minutes": 60,
                    "schedule_mode": "automatic",
                },
            ),
        ],
    )

    response = client.get(
        "/ingestion/schedule-plan",
        params={"state": "TX", "as_of": NOW.isoformat()},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_source_count"] == 1
    assert body["due_source_count"] == 1
    assert body["catalog_synced"] is True
    assert [item["source_key"] for item in body["items"]] == ["texas_source"]


def test_schedule_plan_endpoint_rejects_out_of_range_shard(client):
    response = client.get(
        "/ingestion/schedule-plan",
        params={"shard_count": 2, "shard_index": 2},
    )

    assert response.status_code == 422


def test_schedule_plan_endpoint_rejects_invalid_state(client):
    response = client.get("/ingestion/schedule-plan", params={"state": "not-a-state"})

    assert response.status_code == 422


def test_schedule_plan_endpoint_reports_unsynced_catalog_sources(
    client, monkeypatch
):
    monkeypatch.setattr(
        "app.routes.ingestion.load_catalog",
        lambda: [
            SimpleNamespace(
                key="not_yet_synced", jurisdiction="Austin, TX",
                settings={
                    "collection_interval_minutes": 1440,
                    "collection_sla_hours": 24,
                    "retry_interval_minutes": 60,
                    "schedule_mode": "automatic",
                },
            )
        ],
    )

    response = client.get("/ingestion/schedule-plan", params={"state": "TX"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["catalog_source_count"] == 1
    assert body["total_source_count"] == 0
    assert body["catalog_synced"] is False
    assert body["unsynced_source_keys"] == ["not_yet_synced"]
