from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.webhook import WebhookDelivery, WebhookSubscription
from app.schemas.webhook import WebhookSubscriptionCreate, WebhookSubscriptionUpdate
from app.services.audit_service import log_change

WEBHOOK_USER_AGENT = "BuildSignals-Webhooks/1.0"
MAX_RESPONSE_EXCERPT = 2000


@dataclass(frozen=True)
class WebhookTransportResponse:
    status_code: int
    body: str


@dataclass(frozen=True)
class WebhookBatchResult:
    attempted: int
    delivered: int
    pending: int
    failed: int
    delivery_ids: list[str]


@dataclass(frozen=True)
class WebhookDeliverySummary:
    organization_id: str
    total: int
    pending: int
    delivered: int
    failed: int
    dead_lettered: int
    subscriptions_active: int
    subscriptions_disabled: int
    failure_rate: float
    latest_attempted_at: datetime | None
    latest_created_at: datetime | None
    last_error_message: str | None


def resolve_secret_reference(secret_reference: str | None) -> str | None:
    if not secret_reference:
        return None
    if ":" not in secret_reference:
        return None
    provider, name = secret_reference.split(":", 1)
    if provider.strip().lower() not in {"env", "vercel"}:
        return None
    return os.environ.get(name.strip())


def canonical_webhook_body(delivery: WebhookDelivery) -> str:
    return json.dumps(
        {
            "event_id": delivery.event_id,
            "event_type": delivery.event_type,
            "delivery_id": delivery.id,
            "organization_id": delivery.organization_id,
            "payload": delivery.payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def webhook_signature(*, secret: str, timestamp: str, body: str) -> str:
    signed = f"{timestamp}.{body}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"v1={digest}"


def build_delivery_headers(delivery: WebhookDelivery, *, secret: str | None, timestamp: str, body: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": WEBHOOK_USER_AGENT,
        "X-Build-Signals-Delivery": delivery.id,
        "X-Build-Signals-Event": delivery.event_type,
        "X-Build-Signals-Timestamp": timestamp,
    }
    if secret:
        headers["X-Build-Signals-Signature"] = webhook_signature(
            secret=secret,
            timestamp=timestamp,
            body=body,
        )
    return headers


def urllib_webhook_transport(url: str, *, body: str, headers: dict[str, str], timeout_seconds: int) -> WebhookTransportResponse:
    request = Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return WebhookTransportResponse(
                status_code=response.status,
                body=response.read(MAX_RESPONSE_EXCERPT).decode("utf-8", errors="replace"),
            )
    except HTTPError as exc:
        return WebhookTransportResponse(
            status_code=exc.code,
            body=exc.read(MAX_RESPONSE_EXCERPT).decode("utf-8", errors="replace"),
        )
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def create_subscription(
    db: Session,
    *,
    organization_id: str,
    payload: WebhookSubscriptionCreate,
    actor_id: str,
) -> WebhookSubscription:
    row = WebhookSubscription(
        organization_id=organization_id,
        name=payload.name,
        target_url=str(payload.target_url),
        event_types=payload.event_types,
        secret_reference=payload.secret_reference,
        created_by=actor_id,
    )
    db.add(row)
    db.flush()
    log_change(
        db,
        "webhook_subscription",
        row.id,
        "create",
        actor_id=actor_id,
        organization_id=organization_id,
        new_values={
            "name": row.name,
            "target_url": row.target_url,
            "event_types": row.event_types,
            "secret_reference": row.secret_reference,
        },
    )
    db.commit()
    db.refresh(row)
    return row


def update_subscription(
    db: Session,
    *,
    organization_id: str,
    subscription_id: str,
    payload: WebhookSubscriptionUpdate,
    actor_id: str,
) -> WebhookSubscription:
    row = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.organization_id == organization_id,
            WebhookSubscription.id == subscription_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")
    old_values = {
        "name": row.name,
        "target_url": row.target_url,
        "event_types": row.event_types,
        "status": row.status,
        "secret_reference": row.secret_reference,
    }
    updates = payload.model_dump(exclude_unset=True)
    if "target_url" in updates and updates["target_url"] is not None:
        updates["target_url"] = str(updates["target_url"])
    if updates.get("status") == "disabled" and row.status != "disabled":
        row.disabled_at = datetime.now(timezone.utc)
    if updates.get("status") == "active" and row.status == "disabled":
        row.disabled_at = None
    for key, value in updates.items():
        setattr(row, key, value)
    db.flush()
    log_change(
        db,
        "webhook_subscription",
        row.id,
        "update",
        actor_id=actor_id,
        organization_id=organization_id,
        old_values=old_values,
        new_values={
            "name": row.name,
            "target_url": row.target_url,
            "event_types": row.event_types,
            "status": row.status,
            "secret_reference": row.secret_reference,
        },
    )
    db.commit()
    db.refresh(row)
    return row


def enqueue_webhook_event(
    db: Session,
    *,
    organization_id: str,
    event_type: str,
    event_id: str | None = None,
    payload: dict,
    subscription_id: str | None = None,
) -> list[WebhookDelivery]:
    query = db.query(WebhookSubscription).filter(
        WebhookSubscription.organization_id == organization_id,
        WebhookSubscription.status == "active",
    )
    if subscription_id:
        query = query.filter(WebhookSubscription.id == subscription_id)
    subscriptions = query.all()
    normalized_event_type = event_type.strip().lower()
    deliveries: list[WebhookDelivery] = []
    delivery_event_id = event_id or str(uuid4())
    for subscription in subscriptions:
        if normalized_event_type not in subscription.event_types:
            continue
        delivery = WebhookDelivery(
            organization_id=organization_id,
            subscription_id=subscription.id,
            event_type=normalized_event_type,
            event_id=delivery_event_id,
            payload=payload,
            status="pending",
        )
        db.add(delivery)
        deliveries.append(delivery)
    db.flush()
    return deliveries


def mark_delivery_attempt(
    delivery: WebhookDelivery,
    *,
    status: str,
    response_status_code: int | None = None,
    response_body_excerpt: str | None = None,
    error_message: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    delivery.status = status
    delivery.attempt_count += 1
    delivery.last_attempted_at = now
    delivery.updated_at = now
    delivery.response_status_code = response_status_code
    delivery.response_body_excerpt = (
        response_body_excerpt[:MAX_RESPONSE_EXCERPT] if response_body_excerpt is not None else None
    )
    delivery.error_message = error_message[:MAX_RESPONSE_EXCERPT] if error_message is not None else None
    if status == "pending":
        delay_seconds = min(60 * (2 ** max(delivery.attempt_count - 1, 0)), 3600)
        delivery.next_attempt_at = datetime.fromtimestamp(now.timestamp() + delay_seconds, tz=timezone.utc)
    else:
        delivery.next_attempt_at = None


def attempt_webhook_delivery(
    db: Session,
    *,
    delivery_id: str,
    transport=None,
    timeout_seconds: int = 10,
) -> WebhookDelivery:
    delivery = db.get(WebhookDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail="Webhook delivery not found")
    if delivery.status == "delivered":
        return delivery
    subscription = delivery.subscription
    if subscription is None or subscription.status != "active":
        mark_delivery_attempt(
            delivery,
            status="failed",
            error_message="Webhook subscription is not active",
        )
        db.commit()
        db.refresh(delivery)
        return delivery
    body = canonical_webhook_body(delivery)
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    secret = resolve_secret_reference(subscription.secret_reference)
    headers = build_delivery_headers(delivery, secret=secret, timestamp=timestamp, body=body)
    sender = transport or urllib_webhook_transport
    try:
        response = sender(subscription.target_url, body=body, headers=headers, timeout_seconds=timeout_seconds)
    except Exception as exc:
        mark_delivery_attempt(delivery, status="pending", error_message=str(exc))
    else:
        if 200 <= response.status_code < 300:
            mark_delivery_attempt(
                delivery,
                status="delivered",
                response_status_code=response.status_code,
                response_body_excerpt=response.body,
            )
        else:
            mark_delivery_attempt(
                delivery,
                status="pending",
                response_status_code=response.status_code,
                response_body_excerpt=response.body,
                error_message=f"Webhook target returned HTTP {response.status_code}",
            )
    db.commit()
    db.refresh(delivery)
    return delivery


def fail_delivery_if_attempts_exhausted(
    db: Session,
    delivery: WebhookDelivery,
    *,
    max_attempts: int,
) -> WebhookDelivery:
    if delivery.status == "pending" and delivery.attempt_count >= max_attempts:
        delivery.status = "failed"
        delivery.next_attempt_at = None
        delivery.updated_at = datetime.now(timezone.utc)
        if not delivery.error_message:
            delivery.error_message = "Webhook delivery exhausted retry attempts"
        db.commit()
        db.refresh(delivery)
    return delivery


def process_due_webhook_deliveries(
    db: Session,
    *,
    organization_id: str,
    limit: int = 25,
    max_attempts: int = 8,
    timeout_seconds: int = 10,
    transport=None,
) -> WebhookBatchResult:
    if limit < 1 or limit > 250:
        raise ValueError("limit must be between 1 and 250")
    if max_attempts < 1 or max_attempts > 25:
        raise ValueError("max_attempts must be between 1 and 25")
    if timeout_seconds < 1 or timeout_seconds > 60:
        raise ValueError("timeout_seconds must be between 1 and 60")

    now = datetime.now(timezone.utc)
    deliveries = (
        db.query(WebhookDelivery)
        .filter(
            WebhookDelivery.organization_id == organization_id,
            WebhookDelivery.status == "pending",
            WebhookDelivery.attempt_count < max_attempts,
            or_(WebhookDelivery.next_attempt_at.is_(None), WebhookDelivery.next_attempt_at <= now),
        )
        .order_by(WebhookDelivery.created_at.asc())
        .limit(limit)
        .all()
    )

    statuses: list[str] = []
    delivery_ids: list[str] = []
    for delivery in deliveries:
        attempted = attempt_webhook_delivery(
            db,
            delivery_id=delivery.id,
            transport=transport,
            timeout_seconds=timeout_seconds,
        )
        attempted = fail_delivery_if_attempts_exhausted(db, attempted, max_attempts=max_attempts)
        statuses.append(attempted.status)
        delivery_ids.append(attempted.id)

    return WebhookBatchResult(
        attempted=len(delivery_ids),
        delivered=sum(1 for status in statuses if status == "delivered"),
        pending=sum(1 for status in statuses if status == "pending"),
        failed=sum(1 for status in statuses if status == "failed"),
        delivery_ids=delivery_ids,
    )


def summarize_webhook_deliveries(db: Session, *, organization_id: str) -> WebhookDeliverySummary:
    deliveries = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.organization_id == organization_id)
        .order_by(WebhookDelivery.created_at.desc())
        .all()
    )
    subscriptions = (
        db.query(WebhookSubscription.status)
        .filter(WebhookSubscription.organization_id == organization_id)
        .all()
    )
    total = len(deliveries)
    pending = sum(1 for delivery in deliveries if delivery.status == "pending")
    delivered = sum(1 for delivery in deliveries if delivery.status == "delivered")
    failed = sum(1 for delivery in deliveries if delivery.status == "failed")
    attempted = delivered + failed + sum(
        1 for delivery in deliveries if delivery.status == "pending" and delivery.attempt_count > 0
    )
    latest_attempted_at = max(
        (delivery.last_attempted_at for delivery in deliveries if delivery.last_attempted_at is not None),
        default=None,
    )
    latest_created_at = max((delivery.created_at for delivery in deliveries), default=None)
    last_error_message = next(
        (delivery.error_message for delivery in deliveries if delivery.error_message),
        None,
    )
    return WebhookDeliverySummary(
        organization_id=organization_id,
        total=total,
        pending=pending,
        delivered=delivered,
        failed=failed,
        dead_lettered=failed,
        subscriptions_active=sum(1 for (status,) in subscriptions if status == "active"),
        subscriptions_disabled=sum(1 for (status,) in subscriptions if status == "disabled"),
        failure_rate=round(failed / attempted, 4) if attempted else 0.0,
        latest_attempted_at=latest_attempted_at,
        latest_created_at=latest_created_at,
        last_error_message=last_error_message,
    )


def replay_webhook_delivery(
    db: Session,
    *,
    organization_id: str,
    delivery_id: str,
) -> WebhookDelivery:
    delivery = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.organization_id == organization_id, WebhookDelivery.id == delivery_id)
        .first()
    )
    if delivery is None:
        raise HTTPException(status_code=404, detail="Webhook delivery not found")
    if delivery.status == "delivered":
        raise HTTPException(status_code=409, detail="Delivered webhooks cannot be replayed")
    now = datetime.now(timezone.utc)
    delivery.status = "pending"
    delivery.next_attempt_at = None
    delivery.response_status_code = None
    delivery.response_body_excerpt = None
    delivery.error_message = None
    delivery.updated_at = now
    db.commit()
    db.refresh(delivery)
    return delivery


def list_dead_letter_webhook_deliveries(
    db: Session,
    *,
    organization_id: str,
    limit: int = 50,
    skip: int = 0,
) -> list[WebhookDelivery]:
    return (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.organization_id == organization_id, WebhookDelivery.status == "failed")
        .order_by(WebhookDelivery.updated_at.desc(), WebhookDelivery.id.desc())
        .offset(max(skip, 0))
        .limit(min(max(limit, 1), 100))
        .all()
    )


def get_failed_webhook_delivery(
    db: Session,
    *,
    organization_id: str,
    delivery_id: str,
) -> WebhookDelivery:
    delivery = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.organization_id == organization_id, WebhookDelivery.id == delivery_id)
        .first()
    )
    if delivery is None:
        raise HTTPException(status_code=404, detail="Webhook delivery not found")
    if delivery.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed webhook deliveries can be acknowledged")
    return delivery
