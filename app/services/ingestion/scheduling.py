from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Iterable, Mapping

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ingestion import IngestionRun, IngestionSource
from app.services.ingestion.service import resolve_stale_run_after
from app.utils.org_scope import active_query

TERMINAL_RUN_STATUSES = ("completed", "partial", "failed", "partial_with_errors")
RETRYABLE_RUN_STATUSES = ("failed", "partial_with_errors")
DEFAULT_MAX_PAGES = 10
DEFAULT_PRIORITY = 50


@dataclass(frozen=True)
class SourceSchedulePolicy:
    interval_minutes: int
    retry_interval_minutes: int
    collection_sla_hours: float
    max_pages_per_run: int
    priority: int
    schedule_mode: str


@dataclass(frozen=True)
class SourceSchedulePlanItem:
    source_id: str
    source_key: str
    source_name: str
    jurisdiction: str | None
    due: bool
    due_reason: str
    interval_minutes: int
    retry_interval_minutes: int
    collection_sla_hours: float
    max_pages_per_run: int
    priority: int
    schedule_mode: str
    shard_index: int
    active_run: bool
    stale_run: bool
    latest_status: str | None
    last_terminal_at: datetime | None
    due_at: datetime | None
    overdue_minutes: int


@dataclass(frozen=True)
class SourceSchedulePlan:
    as_of: datetime
    shard_count: int
    shard_index: int
    total_source_count: int
    catalog_source_count: int
    unsynced_source_count: int
    unsynced_source_keys: list[str]
    catalog_synced: bool
    shard_source_count: int
    automatic_source_count: int
    due_source_count: int
    active_source_count: int
    items: list[SourceSchedulePlanItem]


def source_schedule_policy(source: IngestionSource) -> SourceSchedulePolicy:
    settings = source.settings or {}
    interval_minutes = _bounded_int(
        settings.get("collection_interval_minutes"),
        name=f"{source.key}.collection_interval_minutes",
        minimum=15,
        maximum=365 * 24 * 60,
    )
    retry_interval_minutes = _bounded_int(
        settings.get("retry_interval_minutes"),
        name=f"{source.key}.retry_interval_minutes",
        minimum=5,
        maximum=7 * 24 * 60,
    )
    collection_sla_hours = _bounded_number(
        settings.get("collection_sla_hours"),
        name=f"{source.key}.collection_sla_hours",
        minimum=interval_minutes / 60,
        maximum=2 * 365 * 24,
    )
    max_pages = _bounded_int(
        settings.get("max_pages_per_run", DEFAULT_MAX_PAGES),
        name=f"{source.key}.max_pages_per_run",
        minimum=1,
        maximum=100,
    )
    priority = _bounded_int(
        settings.get("collection_priority", DEFAULT_PRIORITY),
        name=f"{source.key}.collection_priority",
        minimum=0,
        maximum=100,
    )
    schedule_mode = str(settings.get("schedule_mode") or "automatic")
    if schedule_mode not in {"automatic", "manual"}:
        raise ValueError(
            f"{source.key}.schedule_mode must be 'automatic' or 'manual'"
        )
    return SourceSchedulePolicy(
        interval_minutes=interval_minutes,
        retry_interval_minutes=retry_interval_minutes,
        collection_sla_hours=collection_sla_hours,
        max_pages_per_run=max_pages,
        priority=priority,
        schedule_mode=schedule_mode,
    )


def source_shard(source_key: str, shard_count: int) -> int:
    if shard_count < 1:
        raise ValueError("shard_count must be at least 1")
    digest = sha256(source_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % shard_count


def build_schedule_plan(
    db: Session,
    sources: Iterable[IngestionSource],
    *,
    as_of: datetime | None = None,
    shard_count: int = 1,
    shard_index: int = 0,
    policies_by_key: Mapping[str, SourceSchedulePolicy] | None = None,
    catalog_source_count: int | None = None,
    unsynced_source_keys: Iterable[str] = (),
) -> SourceSchedulePlan:
    if shard_count < 1 or shard_count > 128:
        raise ValueError("shard_count must be between 1 and 128")
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError("shard_index must be between 0 and shard_count - 1")
    as_of = _utc(as_of or datetime.now(timezone.utc))
    source_list = sorted(sources, key=lambda source: source.key)
    source_ids = [source.id for source in source_list]
    latest_terminal = _latest_runs_by_source(db, source_ids, TERMINAL_RUN_STATUSES)
    running = _latest_runs_by_source(db, source_ids, ("running",))

    items: list[SourceSchedulePlanItem] = []
    for source in source_list:
        assigned_shard = source_shard(source.key, shard_count)
        if assigned_shard != shard_index:
            continue
        policy = (
            policies_by_key.get(source.key)
            if policies_by_key is not None
            else None
        ) or source_schedule_policy(source)
        last_run = latest_terminal.get(source.id)
        running_run = running.get(source.id)
        stale_after = resolve_stale_run_after(source.settings)
        fresh_active = bool(
            running_run
            and as_of - _utc(running_run.heartbeat_at) <= stale_after
        )
        stale_run = bool(running_run and not fresh_active)
        last_terminal_at = (
            _utc(last_run.completed_at or last_run.started_at)
            if last_run
            else None
        )
        due_at = None
        latest_status = last_run.status if last_run else None

        if policy.schedule_mode == "manual":
            due = False
            due_reason = "manual"
            overdue_minutes = 0
        elif fresh_active:
            due = False
            due_reason = "active_run"
            overdue_minutes = 0
        elif stale_run:
            due = True
            due_reason = "stale_run"
            overdue_minutes = 0
        elif last_run is None:
            due = True
            due_reason = "never_run"
            overdue_minutes = 0
        else:
            if last_run.status == "partial":
                due = True
                due_reason = "continue_checkpoint"
                due_at = last_terminal_at
            else:
                wait_minutes = (
                    policy.retry_interval_minutes
                    if last_run.status in RETRYABLE_RUN_STATUSES
                    else policy.interval_minutes
                )
                due_at = last_terminal_at + timedelta(minutes=wait_minutes)
                due = as_of >= due_at
                due_reason = (
                    "retry_backoff_elapsed"
                    if due and last_run.status in RETRYABLE_RUN_STATUSES
                    else "interval_elapsed"
                    if due
                    else "retry_backoff"
                    if last_run.status in RETRYABLE_RUN_STATUSES
                    else "not_due"
                )
            overdue_minutes = max(0, int((as_of - due_at).total_seconds() // 60))

        items.append(
            SourceSchedulePlanItem(
                source_id=source.id,
                source_key=source.key,
                source_name=source.name,
                jurisdiction=source.jurisdiction,
                due=due,
                due_reason=due_reason,
                interval_minutes=policy.interval_minutes,
                retry_interval_minutes=policy.retry_interval_minutes,
                collection_sla_hours=policy.collection_sla_hours,
                max_pages_per_run=policy.max_pages_per_run,
                priority=policy.priority,
                schedule_mode=policy.schedule_mode,
                shard_index=assigned_shard,
                active_run=fresh_active,
                stale_run=stale_run,
                latest_status=latest_status,
                last_terminal_at=last_terminal_at,
                due_at=due_at,
                overdue_minutes=overdue_minutes,
            )
        )
    items.sort(
        key=lambda item: (
            not item.due,
            -item.priority,
            -item.overdue_minutes,
            item.source_key,
        )
    )
    unsynced = sorted(set(unsynced_source_keys))
    return SourceSchedulePlan(
        as_of=as_of,
        shard_count=shard_count,
        shard_index=shard_index,
        total_source_count=len(source_list),
        catalog_source_count=(
            len(source_list) if catalog_source_count is None else catalog_source_count
        ),
        unsynced_source_count=len(unsynced),
        unsynced_source_keys=unsynced,
        catalog_synced=not unsynced,
        shard_source_count=len(items),
        automatic_source_count=sum(
            1 for item in items if item.schedule_mode == "automatic"
        ),
        due_source_count=sum(1 for item in items if item.due),
        active_source_count=sum(1 for item in items if item.active_run),
        items=items,
    )


def _latest_runs_by_source(
    db: Session,
    source_ids: list[str],
    statuses: tuple[str, ...],
) -> dict[str, IngestionRun]:
    if not source_ids:
        return {}
    ranked = active_query(
        db.query(
            IngestionRun.id.label("run_id"),
            func.row_number().over(
                partition_by=IngestionRun.source_id,
                order_by=(IngestionRun.started_at.desc(), IngestionRun.id.desc()),
            ).label("rank"),
        ),
        IngestionRun,
    ).filter(
        IngestionRun.source_id.in_(source_ids),
        IngestionRun.trigger != "canary",
        IngestionRun.status.in_(statuses),
    ).subquery()
    latest_ids = db.query(ranked.c.run_id).filter(ranked.c.rank == 1)
    runs = active_query(db.query(IngestionRun), IngestionRun).filter(
        IngestionRun.id.in_(latest_ids)
    ).all()
    return {run.source_id: run for run in runs}


def _bounded_int(value: object, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _bounded_number(
    value: object,
    *,
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be a number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return parsed


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
