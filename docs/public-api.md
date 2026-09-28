# Public API

Build Signals exposes tenant-scoped read endpoints for customer exports and partner integrations.
Organization admins create and revoke API keys from Settings. Secrets are shown once, stored only as hashes,
expire by default after 90 days, and can be passed with either header:

```bash
Authorization: Bearer bs_live_...
X-API-Key: bs_live_...
```

## Endpoints

- `GET /v1/public/deals`
- `GET /v1/public/deals/{deal_id}`
- `GET /v1/public/deals/{deal_id}/graph-context`
- `GET /v1/public/deals/{deal_id}/workflow-history`
- `GET /v1/public/eval-runs`
- `GET /v1/public/eval-runs/{run_id}`
- `GET /v1/public/signals`
- `GET /v1/public/signals/{signal_id}/assessment-revisions`
- `GET /v1/public/assessment-revisions/{revision_id}/reviews`
- `GET /v1/public/assessment-revisions/{revision_id}/publication`

All public responses are scoped to the API key's organization. A key with `write` or `admin` scope can read;
keys without read-compatible scope receive `403`.

`/deals/{deal_id}/graph-context` returns connected developers, parcels, owners, contractors, architects,
engineers, permits, cities, lenders, brokers, and relationship evidence for one deal. It is read-only and never
builds graph state on demand, so missing graph coverage is returned as empty context rather than invented facts.

`/eval-runs` and `/eval-runs/{run_id}` export AI quality history for customer governance workflows. The list
endpoint returns run-level metadata, thresholds, summaries, gate status, model, and prompt version. The detail
endpoint includes case-level actual outputs, retrieved context, latency, token/cost metadata when captured, and
normalized metrics such as citation accuracy, hallucination risk, factual coverage, and quality.

`/deals/{deal_id}/workflow-history` exports the human-in-the-loop lifecycle for one opportunity. It includes each
source signal, assessment revision snapshot, review decision, and publication/export event. Related drill-down
endpoints expose signal-level assessment revisions plus revision-level reviews and publication events. These
endpoints are read-only for API keys so external integrations can audit status without bypassing reviewer controls
or mutating AI-generated content.

## Pagination

List endpoints keep the response body as an array and return pagination metadata in headers:

- `X-Total-Count`: total rows matching the filters.
- `X-Page-Skip`: current offset.
- `X-Page-Limit`: requested page size.
- `X-Next-Skip`: next offset, or an empty value when there is no next page.

Use `skip` and `limit` query parameters. `limit` is capped at 200.

```bash
curl -sS "https://buildsignals.ai/v1/public/deals?city=Austin&skip=0&limit=50" \
  -H "Authorization: Bearer $BUILD_SIGNALS_API_KEY" \
  -D headers.txt
```

If `headers.txt` includes `X-Next-Skip: 50`, request the next page with `skip=50`.

## Rate Limits And Usage

Public API keys have a per-key rate limit. Responses include:

- `X-API-Key-RateLimit-Limit`
- `X-API-Key-RateLimit-Remaining`
- `Retry-After` on `429` responses

Successful calls are recorded with endpoint, status, item count, latency, and timestamp. Build Signals also
maintains daily usage rollups per key, method, and endpoint so admins can inspect integration volume without
scanning every raw request event. Admins can see total calls, recent daily buckets, and last-used information in
Settings, which gives customer success and implementation teams a quick way to debug integrations without
exposing key secrets.

Admins can rebuild a key's daily rollups from raw usage events with:

- `POST /organizations/{org_id}/api-keys/{key_id}/usage/rebuild-rollups`

## Rotation

New keys default to a 90-day expiration unless an admin chooses a different future date. Expired keys are rejected
the same way as revoked keys. Settings flags keys as rotation due when they are within the rotation warning window,
so enterprise teams can issue a replacement key before an integration outage.

## Example

```bash
curl -sS "https://buildsignals.ai/v1/public/signals?deal_id=deal_123&limit=25" \
  -H "X-API-Key: $BUILD_SIGNALS_API_KEY"
```

The response body is a JSON array of signals. Missing evidence or private tenant data is never returned across
organization boundaries.

## Client Snippets

Copy-ready client examples are available for implementation teams that need to export deals, signals, and graph
context into internal tooling:

- [Python public API client](examples/public_api_client.py)
- [TypeScript public API client](examples/public_api_client.ts)

Both examples use the same tenant-scoped API key model as the curl examples, avoid storing secrets in code, and
show the common production path:

1. List accessible deals.
2. Fetch one deal detail.
3. Fetch its graph context with relationship evidence.
4. Fetch deal-level source signals.
5. Export recent evaluation runs for AI governance.
6. Export workflow history for downstream audit, warehouse, or CRM sync.

Use these snippets as integration scaffolding rather than a generated SDK. When the public API surface stabilizes,
Build Signals can generate versioned packages from `openapi.json`.
