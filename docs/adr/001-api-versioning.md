# ADR 001: Versioned API prefix with transparent unversioned rewrite

**Status:** Accepted  
**Date:** 2026-07-29

## Context

DealSignal started with unversioned routes (`/deals`, `/auth/login`). As the
API surface grew, we needed a stable contract for enterprise integrations
without breaking existing clients.

## Decision

1. Mount all business routes under `/v1` via `CURRENT_API_PREFIX`.
2. Keep `/health` and `/openapi.json` unversioned for probes and tooling.
3. Add `ApiVersioningMiddleware` that rewrites unversioned inbound paths to
   `/v1/*` and emits `Deprecation` + `Sunset` headers on responses.
4. Scope refresh cookies to `/v1/auth` so they align with versioned auth endpoints.

## Consequences

**Positive:**
- New integrations can target `/v1` explicitly.
- Existing clients continue working during deprecation window.
- Cookie path matches actual auth route prefix.

**Negative:**
- Two path forms exist during transition; docs and smoke tests must use `/v1`.
- Deploying cookie path changes requires users to re-login once.

## Alternatives considered

- **Breaking v2-only cutover:** rejected — too disruptive for pilot users.
- **Header-based versioning (`Accept-Version`):** rejected — harder for browser clients and curl debugging.
