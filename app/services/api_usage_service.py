from __future__ import annotations

from datetime import date, datetime, timezone
from time import perf_counter

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.api_key import OrganizationApiKey
from app.models.api_usage import OrganizationApiKeyUsageDailyRollup, OrganizationApiKeyUsageEvent
from app.schemas.organization import (
    ApiKeyUsageDailySummary,
    ApiKeyUsageEndpointSummary,
    ApiKeyUsageSummary,
)


def start_usage_timer() -> float:
    return perf_counter()


def record_api_key_usage(
    db: Session,
    *,
    api_key: OrganizationApiKey,
    method: str,
    path: str,
    status_code: int,
    started_at: float,
    response_items: int | None,
) -> OrganizationApiKeyUsageEvent:
    latency_ms = max(0, int((perf_counter() - started_at) * 1000))
    created_at = datetime.now(timezone.utc)
    event = OrganizationApiKeyUsageEvent(
        organization_id=api_key.organization_id,
        api_key_id=api_key.id,
        method=method.upper(),
        path=path[:240],
        status_code=status_code,
        response_items=response_items,
        latency_ms=latency_ms,
        created_at=created_at,
    )
    db.add(event)
    upsert_daily_usage_rollup(
        db,
        organization_id=api_key.organization_id,
        api_key_id=api_key.id,
        usage_date=_date_bucket(created_at),
        method=event.method,
        path=event.path,
        status_code=status_code,
        response_items=response_items or 0,
        latency_ms=latency_ms,
        last_called_at=created_at,
    )
    db.commit()
    return event


def _date_bucket(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).date()


def upsert_daily_usage_rollup(
    db: Session,
    *,
    organization_id: str,
    api_key_id: str,
    usage_date: date,
    method: str,
    path: str,
    status_code: int | None,
    response_items: int,
    latency_ms: int,
    last_called_at: datetime | None,
) -> OrganizationApiKeyUsageDailyRollup:
    rollup = (
        db.query(OrganizationApiKeyUsageDailyRollup)
        .filter(
            OrganizationApiKeyUsageDailyRollup.organization_id == organization_id,
            OrganizationApiKeyUsageDailyRollup.api_key_id == api_key_id,
            OrganizationApiKeyUsageDailyRollup.usage_date == usage_date,
            OrganizationApiKeyUsageDailyRollup.method == method.upper(),
            OrganizationApiKeyUsageDailyRollup.path == path[:240],
        )
        .first()
    )
    if rollup is None:
        rollup = OrganizationApiKeyUsageDailyRollup(
            organization_id=organization_id,
            api_key_id=api_key_id,
            usage_date=usage_date,
            method=method.upper(),
            path=path[:240],
            total_calls=0,
            total_items=0,
            total_latency_ms=0,
        )
        db.add(rollup)
    rollup.total_calls += 1
    rollup.total_items += response_items
    rollup.total_latency_ms += latency_ms
    rollup.last_status_code = status_code
    rollup.last_called_at = last_called_at
    rollup.updated_at = datetime.now(timezone.utc)
    return rollup


def get_api_key_usage_totals(db: Session, *, api_key_ids: list[str]) -> dict[str, tuple[int, datetime | None]]:
    if not api_key_ids:
        return {}
    rows = (
        db.query(
            OrganizationApiKeyUsageEvent.api_key_id,
            func.count(OrganizationApiKeyUsageEvent.id),
            func.max(OrganizationApiKeyUsageEvent.created_at),
        )
        .filter(OrganizationApiKeyUsageEvent.api_key_id.in_(api_key_ids))
        .group_by(OrganizationApiKeyUsageEvent.api_key_id)
        .all()
    )
    return {str(api_key_id): (int(total or 0), last_called_at) for api_key_id, total, last_called_at in rows}


def summarize_api_key_usage(
    db: Session,
    *,
    organization_id: str,
    api_key_id: str,
) -> ApiKeyUsageSummary:
    rows = (
        db.query(
            OrganizationApiKeyUsageEvent.path,
            OrganizationApiKeyUsageEvent.method,
            func.count(OrganizationApiKeyUsageEvent.id),
            func.coalesce(func.sum(OrganizationApiKeyUsageEvent.response_items), 0),
            func.max(OrganizationApiKeyUsageEvent.created_at),
        )
        .filter(
            OrganizationApiKeyUsageEvent.organization_id == organization_id,
            OrganizationApiKeyUsageEvent.api_key_id == api_key_id,
        )
        .group_by(OrganizationApiKeyUsageEvent.path, OrganizationApiKeyUsageEvent.method)
        .order_by(func.count(OrganizationApiKeyUsageEvent.id).desc())
        .all()
    )
    endpoints = [
        ApiKeyUsageEndpointSummary(
            path=path,
            method=method,
            total_calls=int(total or 0),
            total_items=int(total_items or 0),
            last_called_at=last_called_at,
        )
        for path, method, total, total_items, last_called_at in rows
    ]
    daily_rows = (
        db.query(
            OrganizationApiKeyUsageDailyRollup.usage_date,
            func.sum(OrganizationApiKeyUsageDailyRollup.total_calls),
            func.coalesce(func.sum(OrganizationApiKeyUsageDailyRollup.total_items), 0),
            func.coalesce(func.sum(OrganizationApiKeyUsageDailyRollup.total_latency_ms), 0),
        )
        .filter(
            OrganizationApiKeyUsageDailyRollup.organization_id == organization_id,
            OrganizationApiKeyUsageDailyRollup.api_key_id == api_key_id,
        )
        .group_by(OrganizationApiKeyUsageDailyRollup.usage_date)
        .order_by(OrganizationApiKeyUsageDailyRollup.usage_date.desc())
        .all()
    )
    daily = [
        ApiKeyUsageDailySummary(
            usage_date=usage_date,
            total_calls=int(total_calls or 0),
            total_items=int(total_items or 0),
            average_latency_ms=int((total_latency_ms or 0) / total_calls) if total_calls else 0,
        )
        for usage_date, total_calls, total_items, total_latency_ms in daily_rows
    ]
    return ApiKeyUsageSummary(
        api_key_id=api_key_id,
        total_calls=sum(endpoint.total_calls for endpoint in endpoints),
        total_items=sum(endpoint.total_items for endpoint in endpoints),
        last_called_at=max(
            (endpoint.last_called_at for endpoint in endpoints if endpoint.last_called_at),
            default=None,
        ),
        endpoints=endpoints,
        daily=daily,
    )


def rebuild_api_key_usage_rollups(
    db: Session,
    *,
    organization_id: str,
    api_key_id: str | None = None,
) -> int:
    query = db.query(OrganizationApiKeyUsageEvent).filter(
        OrganizationApiKeyUsageEvent.organization_id == organization_id,
    )
    if api_key_id:
        query = query.filter(OrganizationApiKeyUsageEvent.api_key_id == api_key_id)

    delete_query = db.query(OrganizationApiKeyUsageDailyRollup).filter(
        OrganizationApiKeyUsageDailyRollup.organization_id == organization_id,
    )
    if api_key_id:
        delete_query = delete_query.filter(OrganizationApiKeyUsageDailyRollup.api_key_id == api_key_id)
    delete_query.delete(synchronize_session=False)

    rebuilt = 0
    for event in query.order_by(OrganizationApiKeyUsageEvent.created_at.asc()).all():
        upsert_daily_usage_rollup(
            db,
            organization_id=event.organization_id,
            api_key_id=event.api_key_id,
            usage_date=_date_bucket(event.created_at),
            method=event.method,
            path=event.path,
            status_code=event.status_code,
            response_items=event.response_items or 0,
            latency_ms=event.latency_ms,
            last_called_at=event.created_at,
        )
        rebuilt += 1
    db.commit()
    return rebuilt
