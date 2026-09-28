from datetime import datetime, timedelta, timezone

from app.models.audit_log import AuditLog
from app.models.webhook import WebhookDelivery, WebhookSubscription
from app.services.webhook_service import (
    WebhookTransportResponse,
    attempt_webhook_delivery,
    build_delivery_headers,
    canonical_webhook_body,
    enqueue_webhook_event,
    process_due_webhook_deliveries,
    webhook_signature,
)

STRONG_PW = "CorrectHorseBattery42"


def _register(client, *, email: str, org_name: str) -> dict:
    response = client.post("/auth/register", json={
        "email": email,
        "password": STRONG_PW,
        "full_name": email.split("@")[0].title(),
        "organization_name": org_name,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _headers(identity: dict) -> dict:
    return {"Authorization": f"Bearer {identity['access_token']}"}


def test_admin_can_manage_webhook_subscription_and_queue_test_event(client, db):
    identity = _register(client, email="webhook-admin@example.com", org_name="Webhook Admin")
    headers = _headers(identity)
    org_id = identity["organization_id"]

    created = client.post(
        f"/organizations/{org_id}/webhook-subscriptions",
        headers=headers,
        json={
            "name": "Warehouse sync",
            "target_url": "https://warehouse.example.test/build-signals",
            "event_types": ["Deal.Created", "assessment.review.created"],
            "secret_reference": "vercel:BUILD_SIGNALS_WEBHOOK_SECRET",
        },
    )
    assert created.status_code == 201, created.text
    subscription = created.json()
    assert subscription["event_types"] == ["assessment.review.created", "deal.created"]
    assert subscription["status"] == "active"

    listed = client.get(f"/organizations/{org_id}/webhook-subscriptions", headers=headers)
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [subscription["id"]]

    deliveries = client.post(
        f"/organizations/{org_id}/webhook-test-events",
        headers=headers,
        json={
            "event_type": "deal.created",
            "event_id": "deal-created-1",
            "payload": {"deal_id": "deal-1"},
        },
    )
    assert deliveries.status_code == 201, deliveries.text
    assert len(deliveries.json()) == 1
    assert deliveries.json()[0]["status"] == "pending"
    assert deliveries.json()[0]["payload"]["triggered_by"] == identity["user_id"]

    stored = client.get(f"/organizations/{org_id}/webhook-deliveries", headers=headers)
    assert stored.status_code == 200, stored.text
    assert [row["event_id"] for row in stored.json()] == ["deal-created-1"]

    disabled = client.patch(
        f"/organizations/{org_id}/webhook-subscriptions/{subscription['id']}",
        headers=headers,
        json={"status": "disabled"},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["disabled_at"]

    skipped = client.post(
        f"/organizations/{org_id}/webhook-test-events",
        headers=headers,
        json={"event_type": "deal.created", "event_id": "deal-created-2", "payload": {}},
    )
    assert skipped.status_code == 201, skipped.text
    assert skipped.json() == []
    assert db.query(WebhookDelivery).count() == 1
    assert db.query(AuditLog).filter_by(entity_type="webhook_subscription").count() == 2


def test_webhook_config_rejects_unknown_events_and_raw_secret_like_urls(client):
    identity = _register(client, email="webhook-validation@example.com", org_name="Webhook Validation")
    headers = _headers(identity)
    org_id = identity["organization_id"]

    unknown = client.post(
        f"/organizations/{org_id}/webhook-subscriptions",
        headers=headers,
        json={
            "name": "Bad events",
            "target_url": "https://warehouse.example.test/build-signals",
            "event_types": ["deal.deleted"],
        },
    )
    assert unknown.status_code == 422

    raw_secret = client.post(
        f"/organizations/{org_id}/webhook-subscriptions",
        headers=headers,
        json={
            "name": "Bad secret",
            "target_url": "https://warehouse.example.test/build-signals",
            "event_types": ["deal.created"],
            "secret_reference": "https://secret.example.test/value",
        },
    )
    assert raw_secret.status_code == 422


def test_webhook_subscriptions_are_tenant_scoped(client, db):
    first = _register(client, email="webhook-first@example.com", org_name="Webhook First")
    second = _register(client, email="webhook-second@example.com", org_name="Webhook Second")
    created = client.post(
        f"/organizations/{first['organization_id']}/webhook-subscriptions",
        headers=_headers(first),
        json={
            "name": "First tenant sync",
            "target_url": "https://warehouse.example.test/first",
            "event_types": ["eval.run.completed"],
        },
    )
    assert created.status_code == 201, created.text
    subscription_id = created.json()["id"]

    cross_org_list = client.get(
        f"/organizations/{first['organization_id']}/webhook-subscriptions",
        headers=_headers(second),
    )
    assert cross_org_list.status_code == 403

    cross_org_update = client.patch(
        f"/organizations/{second['organization_id']}/webhook-subscriptions/{subscription_id}",
        headers=_headers(second),
        json={"status": "disabled"},
    )
    assert cross_org_update.status_code == 404
    assert db.query(WebhookSubscription).filter_by(organization_id=first["organization_id"]).count() == 1


def test_enqueue_webhook_event_matches_active_subscriptions_only(db):
    active = WebhookSubscription(
        organization_id="org-webhook",
        name="Active",
        target_url="https://example.test/active",
        event_types=["deal.created", "signal.created"],
        status="active",
    )
    disabled = WebhookSubscription(
        organization_id="org-webhook",
        name="Disabled",
        target_url="https://example.test/disabled",
        event_types=["deal.created"],
        status="disabled",
    )
    unrelated = WebhookSubscription(
        organization_id="other-org",
        name="Other",
        target_url="https://example.test/other",
        event_types=["deal.created"],
        status="active",
    )
    db.add_all([active, disabled, unrelated])
    db.commit()

    deliveries = enqueue_webhook_event(
        db,
        organization_id="org-webhook",
        event_type="deal.created",
        event_id="deal-1",
        payload={"deal_id": "deal-1"},
    )
    db.commit()

    assert len(deliveries) == 1
    assert deliveries[0].subscription_id == active.id
    assert deliveries[0].status == "pending"
    assert db.query(WebhookDelivery).count() == 1


def test_webhook_signature_uses_timestamp_and_canonical_body(db, monkeypatch):
    monkeypatch.setenv("BUILD_SIGNALS_WEBHOOK_SECRET", "super-secret")
    subscription = WebhookSubscription(
        organization_id="org-signature",
        name="Signed",
        target_url="https://example.test/signed",
        event_types=["deal.created"],
        status="active",
        secret_reference="env:BUILD_SIGNALS_WEBHOOK_SECRET",
    )
    db.add(subscription)
    db.flush()
    delivery = WebhookDelivery(
        organization_id="org-signature",
        subscription_id=subscription.id,
        event_type="deal.created",
        event_id="deal-1",
        payload={"deal_id": "deal-1"},
    )
    db.add(delivery)
    db.commit()

    body = canonical_webhook_body(delivery)
    headers = build_delivery_headers(delivery, secret="super-secret", timestamp="123", body=body)

    assert headers["X-Build-Signals-Signature"] == webhook_signature(
        secret="super-secret",
        timestamp="123",
        body=body,
    )
    assert '"event_type":"deal.created"' in body
    assert '"payload":{"deal_id":"deal-1"}' in body


def test_attempt_webhook_delivery_marks_success_and_sends_headers(db, monkeypatch):
    monkeypatch.setenv("BUILD_SIGNALS_WEBHOOK_SECRET", "super-secret")
    subscription = WebhookSubscription(
        organization_id="org-delivery",
        name="Delivery",
        target_url="https://example.test/webhook",
        event_types=["deal.created"],
        status="active",
        secret_reference="env:BUILD_SIGNALS_WEBHOOK_SECRET",
    )
    db.add(subscription)
    db.flush()
    delivery = WebhookDelivery(
        organization_id="org-delivery",
        subscription_id=subscription.id,
        event_type="deal.created",
        event_id="deal-1",
        payload={"deal_id": "deal-1"},
    )
    db.add(delivery)
    db.commit()
    calls = []

    def transport(url, *, body, headers, timeout_seconds):
        calls.append((url, body, headers, timeout_seconds))
        return WebhookTransportResponse(status_code=204, body="accepted")

    result = attempt_webhook_delivery(db, delivery_id=delivery.id, transport=transport, timeout_seconds=3)

    assert result.status == "delivered"
    assert result.attempt_count == 1
    assert result.response_status_code == 204
    assert result.next_attempt_at is None
    assert calls[0][0] == "https://example.test/webhook"
    assert calls[0][2]["X-Build-Signals-Signature"].startswith("v1=")
    assert calls[0][3] == 3


def test_attempt_webhook_delivery_schedules_retry_on_http_error(db):
    subscription = WebhookSubscription(
        organization_id="org-retry",
        name="Retry",
        target_url="https://example.test/webhook",
        event_types=["deal.created"],
        status="active",
    )
    db.add(subscription)
    db.flush()
    delivery = WebhookDelivery(
        organization_id="org-retry",
        subscription_id=subscription.id,
        event_type="deal.created",
        event_id="deal-1",
        payload={"deal_id": "deal-1"},
    )
    db.add(delivery)
    db.commit()

    def transport(*_args, **_kwargs):
        return WebhookTransportResponse(status_code=503, body="try later")

    result = attempt_webhook_delivery(db, delivery_id=delivery.id, transport=transport)

    assert result.status == "pending"
    assert result.attempt_count == 1
    assert result.response_status_code == 503
    assert result.error_message == "Webhook target returned HTTP 503"
    assert result.next_attempt_at is not None
    assert result.next_attempt_at > result.last_attempted_at


def test_attempt_webhook_delivery_fails_disabled_subscription(db):
    subscription = WebhookSubscription(
        organization_id="org-disabled",
        name="Disabled",
        target_url="https://example.test/webhook",
        event_types=["deal.created"],
        status="disabled",
    )
    db.add(subscription)
    db.flush()
    delivery = WebhookDelivery(
        organization_id="org-disabled",
        subscription_id=subscription.id,
        event_type="deal.created",
        event_id="deal-1",
        payload={"deal_id": "deal-1"},
    )
    db.add(delivery)
    db.commit()

    result = attempt_webhook_delivery(db, delivery_id=delivery.id, transport=lambda *_args, **_kwargs: None)

    assert result.status == "failed"
    assert result.attempt_count == 1
    assert result.error_message == "Webhook subscription is not active"


def test_process_due_webhook_deliveries_attempts_ready_rows_only(db):
    subscription = WebhookSubscription(
        organization_id="org-worker",
        name="Worker",
        target_url="https://example.test/webhook",
        event_types=["deal.created"],
        status="active",
    )
    db.add(subscription)
    db.flush()
    due = WebhookDelivery(
        organization_id="org-worker",
        subscription_id=subscription.id,
        event_type="deal.created",
        event_id="due",
        payload={"deal_id": "due"},
    )
    future = WebhookDelivery(
        organization_id="org-worker",
        subscription_id=subscription.id,
        event_type="deal.created",
        event_id="future",
        payload={"deal_id": "future"},
        next_attempt_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    other_org = WebhookDelivery(
        organization_id="other-org",
        subscription_id=subscription.id,
        event_type="deal.created",
        event_id="other",
        payload={"deal_id": "other"},
    )
    db.add_all([due, future, other_org])
    db.commit()

    def transport(*_args, **_kwargs):
        return WebhookTransportResponse(status_code=204, body="")

    result = process_due_webhook_deliveries(
        db,
        organization_id="org-worker",
        limit=10,
        transport=transport,
    )

    assert result.attempted == 1
    assert result.delivered == 1
    assert result.pending == 0
    assert result.failed == 0
    assert result.delivery_ids == [due.id]
    assert db.get(WebhookDelivery, future.id).attempt_count == 0
    assert db.get(WebhookDelivery, other_org.id).attempt_count == 0


def test_process_due_webhook_deliveries_marks_exhausted_retry_failed(db):
    subscription = WebhookSubscription(
        organization_id="org-exhausted",
        name="Exhausted",
        target_url="https://example.test/webhook",
        event_types=["deal.created"],
        status="active",
    )
    db.add(subscription)
    db.flush()
    delivery = WebhookDelivery(
        organization_id="org-exhausted",
        subscription_id=subscription.id,
        event_type="deal.created",
        event_id="deal-1",
        payload={"deal_id": "deal-1"},
        attempt_count=1,
    )
    db.add(delivery)
    db.commit()

    def transport(*_args, **_kwargs):
        return WebhookTransportResponse(status_code=500, body="nope")

    result = process_due_webhook_deliveries(
        db,
        organization_id="org-exhausted",
        max_attempts=2,
        transport=transport,
    )

    refreshed = db.get(WebhookDelivery, delivery.id)
    assert result.attempted == 1
    assert result.failed == 1
    assert refreshed.status == "failed"
    assert refreshed.attempt_count == 2
    assert refreshed.next_attempt_at is None


def test_process_due_webhook_deliveries_validates_operational_bounds(db):
    try:
        process_due_webhook_deliveries(db, organization_id="org-worker", limit=0)
    except ValueError as exc:
        assert str(exc) == "limit must be between 1 and 250"
    else:
        raise AssertionError("Expected invalid limit to fail")
