# Public API

Build Signals exposes tenant-scoped read endpoints for customer exports and partner integrations.
Organization admins create and revoke API keys from Settings. Secrets are shown once, stored only as hashes,
and can be passed with either header:

```bash
Authorization: Bearer bs_live_...
X-API-Key: bs_live_...
```

## Endpoints

- `GET /v1/public/deals`
- `GET /v1/public/deals/{deal_id}`
- `GET /v1/public/signals`

All public responses are scoped to the API key's organization. A key with `write` or `admin` scope can read;
keys without read-compatible scope receive `403`.

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

Successful calls are recorded with endpoint, status, item count, latency, and timestamp. Admins can see total
calls and last-used information in Settings, which gives customer success and implementation teams a quick way
to debug integrations without exposing key secrets.

## Example

```bash
curl -sS "https://buildsignals.ai/v1/public/signals?deal_id=deal_123&limit=25" \
  -H "X-API-Key: $BUILD_SIGNALS_API_KEY"
```

The response body is a JSON array of signals. Missing evidence or private tenant data is never returned across
organization boundaries.
