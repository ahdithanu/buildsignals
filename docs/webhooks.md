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

The first release intentionally queues delivery records but does not perform outbound HTTP calls inside product
request handlers. This preserves user-facing latency and avoids turning customer endpoint downtime into application
failures.

## Admin API

- `GET /v1/organizations/{org_id}/webhook-subscriptions`
- `POST /v1/organizations/{org_id}/webhook-subscriptions`
- `PATCH /v1/organizations/{org_id}/webhook-subscriptions/{subscription_id}`
- `GET /v1/organizations/{org_id}/webhook-deliveries`
- `POST /v1/organizations/{org_id}/webhook-test-events`

Only organization admins can manage subscriptions or inspect deliveries. All records are organization-scoped and
covered by Postgres row-level security in production.

## Delivery Queue

`webhook_deliveries` stores one queued row per matching active subscription. Each row includes:

- Event type and event id.
- Delivery payload.
- Pending, delivered, or failed status.
- Attempt count and next retry time.
- Last response code, response excerpt, and error message.

The queue is designed for a future worker that signs payloads using the configured secret reference, performs
bounded retries, and records success or failure without blocking the originating workflow.

## Scaling Path

For 1 million opportunities, webhook delivery should move to a dedicated worker pool backed by batched queue reads,
idempotency keys, exponential backoff, dead-letter retention, and per-customer concurrency limits. The current table
shape already supports those additions without changing customer-facing subscription APIs.
