# Webhooks

Build Signals supports an event-delivery foundation for customer integrations that need push-based updates instead
of polling the Public API.

## Current Capability

Organization admins can configure webhook subscriptions with:

- A customer-owned HTTPS target URL.
- A validated event type allowlist.
- An optional secret reference, such as `vercel:BUILD_SIGNALS_WEBHOOK_SECRET`.
- Active or disabled status.

Supported event types:

- `deal.created`
- `deal.updated`
- `signal.created`
- `assessment.revision.created`
- `assessment.review.created`
- `assessment.publication.created`
- `eval.run.completed`
- `eval.run.failed`

Product request handlers only queue delivery records. Outbound HTTP delivery runs through an explicit worker path,
which preserves user-facing latency and avoids turning customer endpoint downtime into application failures.

## Admin API

- `GET /v1/organizations/{org_id}/webhook-subscriptions`
- `POST /v1/organizations/{org_id}/webhook-subscriptions`
- `PATCH /v1/organizations/{org_id}/webhook-subscriptions/{subscription_id}`
- `GET /v1/organizations/{org_id}/webhook-deliveries`
- `GET /v1/organizations/{org_id}/webhook-delivery-summary`
- `GET /v1/organizations/{org_id}/webhook-dead-letters`
- `POST /v1/organizations/{org_id}/webhook-test-events`
- `POST /v1/organizations/{org_id}/webhook-deliveries/{delivery_id}/attempt`
- `POST /v1/organizations/{org_id}/webhook-deliveries/{delivery_id}/replay`
- `POST /v1/organizations/{org_id}/webhook-dead-letters/{delivery_id}/acknowledge`

Only organization admins can manage subscriptions or inspect deliveries. All records are organization-scoped and
covered by Postgres row-level security in production.

## Delivery Queue

`webhook_deliveries` stores one queued row per matching active subscription. Each row includes:

- Event type and event id.
- Delivery payload.
- Pending, delivered, or failed status.
- Attempt count and next retry time.
- Last response code, response excerpt, and error message.

The queue is processed by a tenant-scoped worker that signs payloads using the configured secret reference, performs
bounded retries, and records success or failure without blocking the originating workflow.

`GET /v1/organizations/{org_id}/webhook-delivery-summary` provides an admin health rollup with total, pending,
delivered, failed, and dead-lettered deliveries, active/disabled subscription counts, failure rate, latest timestamps,
and the most recent error message. Use it as the dashboard source before drilling into individual delivery rows.
The Settings console can also filter recent deliveries by subscription so operators can verify a specific customer
endpoint after sending a test event or troubleshooting a failure.

## Delivery Attempts

The delivery service posts a canonical JSON body containing `event_id`, `event_type`, `delivery_id`,
`organization_id`, and the event `payload`. Delivery attempts send:

- `X-Build-Signals-Delivery`
- `X-Build-Signals-Event`
- `X-Build-Signals-Timestamp`
- `X-Build-Signals-Signature` when the subscription has a resolvable secret reference

The signature is `v1=` plus an HMAC-SHA256 digest over `{timestamp}.{canonical_body}`. Secret references are
resolved from deployment environment variables when they use `env:NAME` or `vercel:NAME`; raw signing secrets are
not stored in the subscription row.

2xx responses mark a delivery as `delivered`. Non-2xx responses and network errors leave the row `pending` with a
bounded response excerpt, error message, incremented attempt count, and an exponential retry timestamp. Disabled
subscriptions fail pending deliveries instead of posting to stale customer endpoints.

Admins can replay a failed or pending delivery after the customer fixes their receiving endpoint. Replay clears the
current response/error fields and makes the row immediately eligible for the worker while preserving the original
payload and attempt count. Delivered webhooks cannot be replayed.

## Test Events

Admins can queue a synthetic test payload from the Settings console or by calling
`POST /v1/organizations/{org_id}/webhook-test-events`. The request accepts an event type, event id, and arbitrary
payload. Build Signals creates one pending delivery for each active subscription that includes the requested event
type, then records an audit event with the queued delivery count.

Use test events immediately after creating a customer endpoint to validate routing, signing headers, receiver
availability, and downstream observability before relying on production events. A zero-delivery response means no
active endpoint currently subscribes to that event type.

## Dead Letters

Failed deliveries are the webhook dead-letter queue. Admins can list them with
`GET /v1/organizations/{org_id}/webhook-dead-letters` and acknowledge triage with
`POST /v1/organizations/{org_id}/webhook-dead-letters/{delivery_id}/acknowledge`. Acknowledgement writes an audit log
with an optional note; it does not mutate the delivery payload, status, response excerpt, or error evidence. Replay is
the recovery action when the customer receiver is ready for another attempt.

## Worker Runner

Run due deliveries for one organization with:

```bash
python scripts/process_webhooks.py --organization-id <org-id> --limit 25 --max-attempts 8 --timeout-seconds 10
```

The runner prints a JSON summary:

```json
{"attempted": 3, "delivered": 2, "delivery_ids": ["..."], "failed": 0, "pending": 1}
```

The worker is intentionally organization-scoped because production Postgres row-level security is tenant scoped.
Schedulers should run it per enrolled customer workspace. Safe defaults:

- `--limit` accepts 1 to 250 deliveries per run.
- `--max-attempts` accepts 1 to 25 attempts before a still-pending delivery is marked failed.
- `--timeout-seconds` accepts 1 to 60 seconds per target request.

For Vercel Cron or another scheduler, store signing material in deployment secrets, point subscription
`secret_reference` values at those names, and invoke the runner on the desired cadence.

## Scaling Path

For 1 million opportunities, webhook delivery should move from the tenant-scoped runner to a dedicated worker pool
backed by leased queue reads, idempotency keys, dead-letter retention, and per-customer concurrency limits. The
current table shape already supports those additions without changing customer-facing subscription APIs.
