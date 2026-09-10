# Browser and Session Protection

This frontend-only release does not deploy the MFA encryption or RLS migrations
in PR #112. It requires no new backend secrets or schema changes.

## Browser Policy

Vercel enforces a baseline Content Security Policy prohibiting framing, object
embeds, base URL overrides, and cross-origin form submissions. Script and network
restrictions remain report-only pending observation of authenticated workflows.
Inline styles remain allowed for the existing UI. Google font hosts, the current
backend origin, and specific analytics/error-reporting origins are listed.
There is no centralized violation collector; raw URLs can contain sensitive
query parameters and must not be blindly logged.

`scripts/verify_browser_policy.cjs` serves the built frontend locally with the
strict trial policy enforced. It checks the login at mobile and desktop widths,
TOTP submission, no horizontal overflow, and rejection of injected inline script.
It uses synthetic API responses, not production credentials or account evidence.

## Session Caches

The query provider and its consumers have separate lifetimes for each user,
organization, and role. Identity changes create an empty query client, discard
prior queries and mutations, and remount local page state. An unchanged identity
refresh retains the cache. Tests include a late previous-organization response.
This supplements server-side authorization; it does not replace tenant filtering
or PostgreSQL row-level security.

The API client tracks explicit session changes separately from silent token
rotation. Old requests cannot overwrite or clear the new in-memory token or retry
under the new identity. The auth provider ignores superseded login/hydration
results and clears local state immediately on logout, even during a network delay.

Residual: JavaScript cannot undo a delayed server `Set-Cookie` header. Overlapping
login, logout and refresh responses can still change the HttpOnly refresh cookie
out of order. The in-memory session guards are not a complete cookie-ordering
solution. A backend/session-protocol fix and real-browser cookie-race tests remain
an open audit item.

## Remaining Gates

- Confirm deployed headers at the canonical production login URL.
- Observe real authenticated workflows before strict CSP enforcement.
- Provision separate managed MFA keys before the encryption backend release.
- Perform an approved isolated production-backup restore and application-role
  isolation test. Local tests are not production recovery evidence.
- Query authorized live data before making measured geographic coverage claims.
