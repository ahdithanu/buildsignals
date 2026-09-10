# Browser and Session Protection

This release isolates public registration and protects browser sessions. It does
not deploy the MFA encryption or RLS migrations in PR #112, and requires no new
backend secrets or schema changes.

## Public Registration

Public signup must create a separate organization, including when the optional
organization name is omitted. It must never join the shared default organization
or an existing organization implicitly. New workspace creators are administrators
of their own workspace; existing-team access requires an explicit authorized
membership workflow.

This fixes an unsafe default-organization join path, not evidence of an actual
breach. Existing memberships are not automatically removed or moved: review
default-organization signup audit records and legitimate memberships before any
remediation. Deploy the backend code as well as the frontend to close this path.

For an authorized operator, the following PostgreSQL read-only audit returns only
aggregate counts and event dates, not names, emails, credentials or record contents.
Set the psql variable `default_org` to the deployed `DEFAULT_ORG_ID` first. Use an
approved connection with the same organization-scoped visibility as the service.

```sql
BEGIN READ ONLY;
SELECT set_config('app.current_org', :'default_org', true);
SELECT role, count(*) AS current_members
FROM organization_memberships
WHERE organization_id = :'default_org'
GROUP BY role;

SELECT count(DISTINCT a.entity_id) AS registered_users_in_audit,
       count(DISTINCT m.user_id) AS still_members,
       min(a.created_at) AS first_recorded_signup,
       max(a.created_at) AS last_recorded_signup
FROM audit_logs a
LEFT JOIN organization_memberships m
  ON m.user_id = a.entity_id AND m.organization_id = a.organization_id
WHERE a.organization_id = :'default_org'
  AND a.entity_type = 'user' AND a.action = 'register';
ROLLBACK;
```

Audit retention or incomplete visibility can produce incomplete results. Zero
matching events is not proof that no implicit memberships were ever created.
Review any affected memberships with the owner before revocation or data movement.

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
- Confirm backend registration isolation and review historical default-organization
  self-signups using authorized production audit access.
- Observe real authenticated workflows before strict CSP enforcement.
- Provision separate managed MFA keys before the encryption backend release.
- Perform an approved isolated production-backup restore and application-role
  isolation test. Local tests are not production recovery evidence.
- Query authorized live data before making measured geographic coverage claims.
