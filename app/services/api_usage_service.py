from __future__ import annotations

from datetime import datetime
from time import perf_counter

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.api_key import OrganizationApiKey
from app.models.api_usage import OrganizationApiKeyUsageEvent
from app.schemas.organization import ApiKeyUsageEndpointSummary, ApiKeyUsageSummary


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
    event = OrganizationApiKeyUsageEvent(
        organization_id=api_key.organization_id,
        api_key_id=api_key.id,
        method=method.upper(),
        path=path[:240],
        status_code=status_code,
        response_items=response_items,
        latency_ms=max(0, int((perf_counter() - started_at) * 1000)),
    )
    db.add(event)
    db.commit()
    return event


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
    return ApiKeyUsageSummary(
        api_key_id=api_key_id,
        total_calls=sum(endpoint.total_calls for endpoint in endpoints),
        total_items=sum(endpoint.total_items for endpoint in endpoints),
        last_called_at=max(
            (endpoint.last_called_at for endpoint in endpoints if endpoint.last_called_at),
            default=None,
        ),
        endpoints=endpoints,
    )
