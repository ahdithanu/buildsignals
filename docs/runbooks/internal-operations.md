# Internal Operations Access

Connector inventories, raw measured source reports, ingestion runs, schedules,
onboarding and ingestion observability are internal operations, not customer
workspace administration. The owner approved access for their account only.

## Server Configuration

`INTERNAL_OPERATIONS_USER_IDS` is a comma-separated allowlist of verified user
UUIDs. Empty or unset denies everyone. Configure it on the API server only; do
not commit real account identifiers or put this value in Vite configuration.
The production allowlist must contain exactly the verified owner account.

Every internal request requires a valid session, an active user, current admin
membership in the session organization, and an allowlisted account. Roles are
read from the database on each request. Customer admins, editors, viewers,
anonymous callers and demo identities cannot grant themselves this access.
Allowlisting does not grant cross-organization data access or bypass RLS.

The API supplies `is_internal_operator` on authentication/profile responses.
Navigation and query guards use this server-derived value; they are not the
security boundary. Revoking membership or removing the server allowlist entry
denies subsequent internal API calls, including with an older access token.
Changing the environment requires the normal API service configuration rollout.
Acceptance tools that read the restricted ingestion APIs now need an authorized
operator session too; an ordinary customer-admin token is not sufficient.
Scheduled workers use their existing direct ingestion path and are unchanged.

## Customer Surfaces

Customers retain geographic inventory, map readiness, nearby-parcel workflows,
and honest missing-data states. Customer source selection uses opaque IDs and
generic public-record labels. Coverage summaries return only organization-scoped
record/geocode totals and a measurement timestamp. Internal reports require the
operator dependency even when requested directly rather than through the UI.

The Dashboard national parcel gap matrix and connector targets are internal,
including `/v1/ingestion/coverage/national-parcels`. Ordinary customer admins,
editors, viewers and demo sessions receive403; unauthorized requests do not
compute the report. The component itself fails closed, both Dashboard branches
hide it, and its query is disabled for nonoperators with permission-scoped keys.
Source Health keeps its existing internal UI and API guards. Customer measured
coverage summaries and full geographic inventory/map endpoints are unchanged.

This follow-up is locally implemented/tested, not merged or production-verified.
The browser regression uses a disposable operator then a newly registered
customer at desktop/mobile sizes, checks zero diagnostic requests after signout,
reloads the guarded route and verifies customer map access. Run it with
`node node_modules/@playwright/test/cli.js test -c e2e/coverage-privacy.playwright.config.ts`.
CI runs this dedicated offline journey separately from the default suite.

Investment-area provenance is projected as Public records, period and capture
date. Full publisher URLs, hashes and original capture timestamps remain in the
backend reference artifact. Do not erase lineage or required publisher/license
attribution, including map credits. Public repository code and history can
still disclose sources; this feature is access control, not source secrecy.

## Acceptance

Use disposable local accounts to test an ordinary customer admin (403), an
explicitly allowlisted admin (200), and a demo session (403) on internal APIs.
Verify that non-operator coverage/maps still load, that direct console URLs
redirect safely, and that session/organization changes discard operator caches.
Silent refresh with a changed or missing user/organization/role fails closed
before installing the refreshed token or retrying the request. A fresh sign-in
is required after an identity-scope change; first-mount cookie hydration remains
supported. Same-identity operator revocation clears the diagnostic cache.
The browser fixture's synthetic operator exists only in disposable SQLite and
does not activate or call any ingestion source. Production verification uses
the owner's existing session, not a newly created customer account.

See `docs/releases/2026-11-10-investment-areas.md` for dated execution receipts.
