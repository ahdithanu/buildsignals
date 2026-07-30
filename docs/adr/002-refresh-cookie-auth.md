# ADR 002: Refresh token in httpOnly cookie (not localStorage)

**Status:** Accepted
**Date:** 2026-07-29

## Context

SPAs traditionally stored JWTs in `localStorage`, which any XSS can exfiltrate.
DealSignal uses short-lived access tokens in memory and long-lived refresh
tokens in cookies.

## Decision

- Access token: returned in JSON, held in React state/memory only.
- Refresh token: `httpOnly`, `Secure` (prod), `SameSite=lax`, path `/v1/auth`.
- Frontend calls `POST /v1/auth/refresh` on 401; cookie sent automatically.

## Consequences

**Positive:** XSS cannot read refresh tokens.
**Negative:** Full-page navigation requires working cookie path + CORS credentials.
E2E and production must use same-site or correct CORS/cookie config.

## Related

- `app/config.py` — `REFRESH_COOKIE_*` settings
- `src/api/client.ts` — refresh interceptor
