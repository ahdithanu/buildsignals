# Enterprise workflow completion

This is a local engineering acceptance record, not a production attestation.
The user requested continued build work before production configuration. This
branch does not provision secrets, activate feeds, access customer records, or
deploy the changes below.

## Buyer workflow

| Item | Implementation | Verification | Production evidence |
| --- | --- | --- | --- |
| Multiple affected entities | Up to 50 independently described implications; explicit cited evidence per entity | Composer regressions and real local browser round trip | Pending deployment and an authorized real-data walkthrough |
| Event date | Optional explicit UTC timestamp, separate from revision creation and source observation | Stored timestamp round trip; unknown remains unknown | Pending |
| Revision, review and publication history | Bounded 20-row pages with one look-ahead row; stable backend ordering | Page boundaries, errors, retries, identity changes and history tests | Pending |
| Publication actions | Latest status/version queried independently from the history page being browsed | Old-page actions use latest version; stale refresh hides actions | Pending |
| Citation provenance | Saved source reference, observation time, relationship verification time and historical/current status | Snapshot labels and safe relationship/source links | Pending |
| Settings | Actual account/workspace details and existing account, team, source-health and authorized audit routes | Role/loading/error tests; mobile/tablet/desktop browser checks | Pending |
| Route loading | Workspace screens load on demand; visible loading and reload recovery | Built login stays below 180 KiB gzip JavaScript at three widths; failed page-chunk recovery exercised | Pending |

`scripts/verify_assessment_workflow.cjs` creates explicitly labeled synthetic
accounts, entities and evidence in an isolated local backend. It exercises real
login/cookie hydration, two-entity draft authoring, independent review,
publication, withdrawal, reload, revision pagination and settings at 390px,
768px and 1440px. It rejects non-loopback hosts. Use only a disposable database;
the loopback hostname alone cannot prove its database is isolated. The CI wrapper
is `e2e/tests/assessment-workflow.spec.ts`.

UI pagination uses offsets, not an immutable historical cursor. A concurrent new
revision can shift a later page; the system does not promise a point-in-time
snapshot across separately requested pages. Every selected row retains its
immutable revision ID. Publication uses a server-checked version, not its page
position.

The initial route-split build reduced the entry JavaScript from approximately
418 KiB gzip to 111 KiB gzip. These are build artifact sizes, not a measured
production page-load SLA. `scripts/verify_browser_policy.cjs` counts the actual
local login's script requests, applies a 180 KiB gzip budget, rejects eager
workspace-screen downloads and tests a failed Settings chunk followed by reload.

## Authorization and export controls

- A shared dependency verifies current user, active organization, current
  membership and token version on every non-public business route. A signed JWT
  alone is not sufficient for read access. Explicit anonymous local-demo mode
  remains supported only without an Authorization header.
- Logout-all and password-reset token-version changes invalidate old access
  tokens on their next business request, not only on refresh.
- Authenticated and authentication responses use `Cache-Control: no-store`.
  This prevents HTTP caching, not screenshots or authorized manual copying.
- Membership changes serialize on the parent organization, check the remaining
  active admins, and commit audit records with the mutation.
- Account deletion uses the same parent-first locking order and rejects leaving
  a workspace without an active admin. Out-of-band maintenance must honor this
  invariant too.
- Audit records inherit request scope when no explicit organization is supplied.
  Historical incorrectly scoped rows are not moved automatically.
- Audit profile joins resolve only current members of the audited tenant;
  historical actor identifiers are retained without disclosing another tenant's
  current profile. CSV cells are neutralized against spreadsheet formulas.

## In-progress release gates

- Persisted browser-session revocation and coordinated cross-tab identity.
  The diagnostic in `e2e/auth-cookie-races` confirmed that in-memory generation
  guards alone do not control HttpOnly Set-Cookie ordering. Its safety gate must
  pass before this batch is considered ready for release.
- Final isolated PostgreSQL rerun after the session migration. Fifteen restricted-
  role PostgreSQL tests passed four repeated runs before that migration, covering
  concurrent member departures, account deletion and publication transitions.
- Final integrated suite after the session and source-precondition changes.

## Operator-only production gates

1. Provision independently managed MFA keys, apply the compatible migrations,
   backfill encrypted secrets, disable legacy plaintext reads and test enrolled
   sign-in. PR #112 remains gated; do not bypass it to make a checkbox green.
2. Verify the real PostgreSQL application role and forced-RLS metadata, including
   the four ingestion/planning tables addressed in PR #112.
3. Restore a provider backup into an isolated copy. Record backup identity,
   recency, restore elapsed time, measured RPO/RTO and reviewer. A local synthetic
   database test does not establish production recoverability.
4. Run measured inventory for the intended customer organization and marketed
   markets. Record imported counts, unknown geography, source dates and collection
   freshness. Configured feeds and observed states are not complete coverage.
5. Audit historical default-workspace memberships. The signup fix prevents new
   implicit joins; it neither establishes a breach nor removes existing members.
6. Observe authenticated production flows before enforcing the strict
   script/network CSP. The existing baseline CSP is enforced; strict CSP remains
   report-only.

These gates are independent of the longer-term SSO/SCIM, organization API-key,
usage-billing and portfolio-exposure roadmap. None of those capabilities should
be advertised as implemented. Source licensing, verified for-sale inventory,
customer contracts, independent penetration testing and compliance attestations
also require evidence beyond application tests.
