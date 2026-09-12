# Enterprise workflow completion

This is a local engineering acceptance record, not a production attestation.
The user requested continued build work before production configuration. This
branch does not provision secrets, activate feeds, access customer records, or
deploy the changes below.

## Buyer workflow

| Item | Implementation | Verification | Production evidence |
| --- | --- | --- | --- |
| Multiple affected entities | Up to 50 independently described implications; explicit cited evidence per entity | Composer regressions and real local browser round trip | Pending deployment and an authorized real-data walkthrough |
| Source integrity | Every implication's evidence must involve that entity; current UI supplies bounded source-version preconditions | Changed evidence returns 409; PostgreSQL locks sources through revision commit | Pending |
| Event date | Optional explicit UTC timestamp, separate from revision creation and source observation | Stored timestamp round trip; unknown remains unknown | Pending |
| Revision, review and publication history | Bounded 20-row pages with one look-ahead row; stable backend ordering | Page boundaries, errors, retries, identity changes and history tests | Pending |
| Publication actions | Latest status/version queried independently from the history page being browsed | Old-page actions use latest version; stale refresh hides actions | Pending |
| Citation provenance | Saved source reference, observation time, relationship verification time and historical/current status | Snapshot labels and safe relationship/source links | Pending |
| Settings | Actual account/workspace details and existing account, team, source-health and authorized audit routes | Role/loading/error tests; mobile/tablet/desktop browser checks | Pending |
| Route loading | Workspace screens load on demand; visible loading and reload recovery | Built login stays below 180 KiB gzip JavaScript at three widths; failed page-chunk recovery exercised | Pending |
| Authenticator management | Manual enrollment, confirmation and password/code-protected disable; encrypted storage and secret-free readiness | Full local browser flows at all three widths; atomic state/audit and contention tests | Managed production keys and backfill pending |

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

The final route-split build reduced the entry JavaScript from approximately
418 kB gzip to 113 kB gzip, using Vite's decimal units. These are build artifact sizes, not a measured
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
- Synchronous organization exports have global 10,000-row and 20 MiB caps.
  Overflow fails without a partial download. The September 11 extension adds
  explicit graph metadata/evidence and assessment revision/review/publication
  tables, tenant-reference checks and a schema-versioned manifest. It is still
  not a full account export or backup; raw ingestion and other unlisted data are
  excluded. See [organization export](organization-export.md).
- MFA transitions reload a locked user row and commit with their audit record.
  Code attempts share an account-keyed budget across verify/disable endpoints.
  The September 11 extension makes required authentication limits fail closed,
  adds shared Redis account locks and non-resettable admission budgets, and
  removes raw forwarded-header trust. Ordinary traffic limits still fail open.
  Local counters remain development-only. See
  [authentication protection](auth-abuse-protection.md).

## September 10 Acceptance

Final combined schema: `20260910_0001`, following the two MFA/RLS migrations.

- Backend suite: 1,185 passed, 54 skipped. PostgreSQL-specific cases are skipped
  without their explicitly configured isolated test target; this is not a blanket
  statement that every skipped optional integration ran elsewhere.
- Restricted-role PostgreSQL rerun: 46 passed, comprising 15 enterprise mutation
  cases, 7 browser-family cases, 2 source-evidence locking cases and 22 MFA
  transaction cases. Disposable database removed and cluster stopped afterward.
- Frontend suite: 278 passed; typecheck passed. Lint has zero errors and 20
  existing warnings. Production frontend build passed.
- Full Chromium workflow suite: 9 passed, including three MFA widths and the
  three-width assessment lifecycle. The actual refreshed local preview passed
  the same assessment workflow at 390px, 768px and 1440px.
- Cookie ordering: all 12 positive cases passed independently in Chromium and
  WebKit. Cross-tab identity changes retire private state; original-identity
  mutations cannot be replayed under a new account/workspace. Logout hides
  private data immediately but does not finish its loading boundary before
  revocation settles. See `e2e/auth-cookie-races/README.md` for protocol limits.
- Final built browser-policy gate passed, including strict trial CSP, the login
  JavaScript budget, no overflow and failed page-download recovery.
- Migration round trips and refusal to discard MFA ciphertext or populated
  browser revocation history passed. OpenAPI was regenerated from the combined app.

These results use synthetic data and current desktop browser engines, not physical
phone testing, external penetration testing, hosted CI execution or production
traffic. The refreshed preview is `http://127.0.0.1:4191/login`; it uses a local
test database and ephemeral keys, not production credentials or durable MFA setup.
The draft release incorporates the gated security branch; neither is deployed.

## September 11 Extension

No database migration is added by the authentication/export extension.

- Combined backend/real-Redis suite: 1,313 passed, 54 skipped. This run includes
  all 23 real-Redis cases. Optional PostgreSQL and other gated cases still skip
  without their explicitly configured targets; no production evidence is implied.
- Explicit graph/assessment export inventory and corruption/isolation controls:
  82 focused tests passed, including 49 new cases. Unknown snapshot structures
  fail closed; historical missing evidence and oversized workspaces still need
  a separate archival/background-export solution.
- Real Redis scripts: 23 tests passed against an owned, temporary Redis 7.2.16
  process, including concurrent admission, TTLs, shared locks, wrong-type keys,
  outages and cleanup. No production cache was contacted. Details and verified
  binary provenance are in [the Redis test record](auth-abuse-redis-test.md).
- Independent review found and fixed the template's eviction policy, missing
  explicit proxy configuration and incomplete readiness permission checks.
  Render/Docker/Procfile now use `app.server`; production requires reviewed proxy peers
  or explicit direct-listener mode. The Redis template uses `noeviction`.
- Final authentication/proxy/rollout follow-up tests: 71 passed, after adding
  the Procfile guard and two collective-CIDR cases to the combined-run tree.
  The dependency probe
  now exercises synthetic writes, reads and deletes without customer counters.
- Frontend: 278 tests passed, typecheck and production build passed. All nine
  Chromium workflow cases passed, including 390px/768px/1440px assessment and
  authenticator flows. No frontend layout was changed in this extension.
- Python lint and whitespace checks passed; frontend lint remains zero errors
  with 20 existing warnings. OpenAPI includes 111 paths. Hosted
  CI now enables the owned-process Redis tests; hosted execution remains pending.

The preview already running on port 4191 was not restarted during this backend
extension, preserving its in-memory demo keys and sessions. The new backend
behavior was exercised in disposable test servers, not production or that
existing preview process. Prior PostgreSQL/WebKit evidence above is dated to
the preceding build and was not rerun for this extension.

## Operator-only production gates

1. Provision independently managed MFA keys, apply the compatible migrations,
   backfill encrypted secrets, disable legacy plaintext reads and test enrolled
   sign-in. The PR #112 controls remain gated inside this combined draft too.
   Coordinate the API/frontend release: old clients without the new browser
   protocol cannot refresh and must reload/sign in again. Do not silently roll
   back across populated browser-session revocation history.
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
7. Configure and verify shared Redis persistence/HA/capacity and `noeviction`,
   plus the actual proxy trust boundary. Missing production Redis blocks
   sensitive authentication with 503; missing launcher proxy configuration
   refuses startup. `/health/auth-protection` must report `shared` using the
   real application role. Template changes have not been applied to providers.

These gates are independent of the longer-term SSO/SCIM, organization API-key,
usage-billing and portfolio-exposure roadmap. None of those capabilities should
be advertised as implemented. Source licensing, verified for-sale inventory,
customer contracts, independent penetration testing and compliance attestations
also require evidence beyond application tests.
