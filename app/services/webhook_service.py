from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.webhook import WebhookDelivery, WebhookSubscription
from app.schemas.webhook import WebhookSubscriptionCreate, WebhookSubscriptionUpdate
from app.services.audit_service import log_change


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
) -> list[WebhookDelivery]:
    subscriptions = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.organization_id == organization_id,
            WebhookSubscription.status == "active",
        )
        .all()
    )
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
