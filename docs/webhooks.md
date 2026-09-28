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
- `POST /v1/organizations/{org_id}/webhook-deliveries/{delivery_id}/attempt`

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

## Scaling Path

For 1 million opportunities, webhook delivery should move from the manual attempt endpoint to a dedicated worker
pool backed by batched queue reads, idempotency keys, exponential backoff, dead-letter retention, and per-customer
concurrency limits. The current table shape already supports those additions without changing customer-facing
subscription APIs.
