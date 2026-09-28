from app.models.audit_log import AuditLog
from app.models.webhook import WebhookDelivery, WebhookSubscription
from app.services.webhook_service import enqueue_webhook_event

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
