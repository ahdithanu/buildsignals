# Security and Coverage Evidence Release

## Scope and Status

Implemented on the security-evidence branch; not a production attestation.
Production changes require migration and separately provisioned MFA keys.

PR #113 merged as `8e536ad26e0ba0f3aff87861b214943f7d60d292` after all checks
passed. On 2026-09-10 UTC, the canonical `https://www.buildsignals.ai/login`
returned both the enforced baseline CSP and strict report-only header. The public
backend schema now describes isolated signup, confirming the updated API contract
is deployed. No production account was created for this check. The measured
coverage endpoint was not yet present in that deployed schema; it remains in this
gated release alongside MFA encryption and the RLS migrations.

| Control | Implemented | Verified | Production gap |
| --- | --- | --- | --- |
| MFA encryption | Authenticated, randomized ciphertext bound to user ID; versioned separate key ring; no new plaintext writes | Enrollment/login/disable, tampering, missing key, legacy gate, atomic backfill and rotation tests | Provision managed secrets, backfill, disable legacy reads, validate recovery keys |
| Tenant isolation | Forced RLS added to four previously unprotected tables | PostgreSQL restricted-role read/write tests on all four; 46 tenant tables checked for forced RLS metadata | Apply migration and verify real application role |
| Recovery | Rollback-only restricted-role probe and explicit restored-copy CLI | Local PostgreSQL dump/restore into a second database; probe passed | Actual provider snapshot, approved restore access, measured RPO/RTO and recovery evidence |
| Browser policy | Enforced baseline plus strict report-only CSP in Vercel configuration | Built login and measured inventory at 390px, 768px and 1440px with strict policy enforced; code submission, no overflow, injected inline script blocked | Observe all authenticated production flows before enforcing strict script/network policy |
| Browser cache isolation | Separate query client and remounted page state per user, organization and role | Account, organization, role, logout, unchanged identity and late-response regressions | Supplements but does not replace backend isolation verification |
| Coverage | Authenticated database aggregation plus paginated ingestion inventory UI | Tenant isolation, zero rows, unknown dates, old-source/recent-collection distinction, filters, pagination and unavailable states | Run against live authorized tenant database; no live counts claimed |

The four corrected tables are `ingestion_candidate_canary_attempts`,
`planning_records`, `planning_company_matches`, and `record_external_references`.
Their prior migrations did not enable RLS. This finding is not evidence of a breach.
The audit also found organization user exports used a password-only denylist,
which could include legacy MFA secrets. Exports now allow only explicit profile
fields, excluding both MFA storage columns and credential-revocation state.
Backoffice MFA reset now clears ciphertext as well as legacy plaintext.
The recovery probe tests deal-table behavior and metadata for all tenant tables;
the broader regression suite separately tests the four newly protected tables.
Here, the metadata inventory means mapped `OrgMixin` business tables. It does
not include organization-scoped authentication/audit tables such as
`organization_memberships` and `audit_logs`, which need separate authorization
review. A passing probe is not a complete database-security attestation.

## MFA Rollout

1. In the backend secret manager, provision `MFA_ENCRYPTION_KEYS` as a JSON object
   mapping a short key ID to a fresh Fernet key. Set `MFA_ACTIVE_KEY_ID` to that ID.
   Use independent random key material, never the JWT `SECRET_KEY`. Restrict who
   can read these values; do not put them in Git, tickets, logs, browser variables,
   database rows, or frontend hosting configuration. Runtime injection of a
   managed secret is supported; direct KMS integration is not implemented.
2. Apply schema migrations through `20260909_0002`, then deploy compatible backend
   code. The additive ciphertext column leaves old rows intact. New enrollment
   returns 503 if the key ring is missing or invalid, never a plaintext fallback.
3. Run `python scripts/migrate_mfa_secrets.py` for validation. Then run with
   `--apply` during an approved maintenance window. The rewrite locks rows, checks
   ciphertext ownership, and commits atomically; a failed rewrite rolls back.
   Output contains only counts. Large installations need a bounded maintenance
   window because locks persist until commit.
4. Repeat validation: legacy count must be zero. Set
   `MFA_ALLOW_LEGACY_PLAINTEXT=false` and verify an enrolled test user's login.
   Legacy reads default to true ONLY for transition compatibility; the storage
   issue is not closed while plaintext rows or legacy reads remain.
5. Verify disable/re-enroll, missing-code denial, invalid-code denial, and user
   access after a restart. Enrollment responses use `Cache-Control: no-store`.

Rotation: retain old keys, add a fresh ID, make it active, run validation then
`--apply`, and verify no old-key rows remain before retiring keys. Old encrypted
backups still need their original keys under a separately controlled retention
and recovery process. Losing all keys prevents MFA verification. Do not disable
MFA to mask missing keys. A compromised application process can still decrypt
secrets; this control protects a database-only disclosure, not a server compromise.

Rollback: after encrypted enrollments exist, keep compatible application code
and keys. The schema downgrade refuses to discard stored ciphertext. Never
restore plaintext just to enable an old build.

Cryptography uses the maintained
[Fernet recipe](https://cryptography.io/en/latest/fernet/); the user identity is
inside the authenticated payload to prevent swapping ciphertext between users.

## Browser Policy Rollout

The enforced baseline blocks framing, object embeds, base URL replacement, and
cross-origin form submission. The stricter policy is report-only pending full
workflow observation; it is NOT yet an enforced script-injection defense.
It uses the current public API origin, existing Google font hosts, and restricted
analytics/error-collection origins. Inline styles remain necessary for the UI.
Report-only violations are available in browser diagnostics; no centralized
collector is claimed. Do not send raw violation URLs containing tokens to logs.

Build with the production API origin, then run
`node scripts/verify_browser_policy.cjs`. This serves the built frontend locally
under the strict trial policy. Auth responses are synthetic; it does not prove
production account authentication or all screens work under strict CSP.
The browser test also exercises a protected-page login redirect, measured
inventory pagination and filters, and unavailable/retry states at three widths.

## Recovery Verification

Restore an approved provider backup to an isolated database first. Set
`RESTORE_DATABASE_URL` securely to that copy using its restricted application
role, then run:

```sh
python scripts/verify_postgres_recovery.py --isolated-restored-copy
```

The probe rejects superuser/BYPASSRLS roles and SQLite, checks forced RLS metadata,
and rolls back all synthetic inserts. It never commits customer-data changes.
It cannot prove the supplied URL is really a restored copy; the operator must
verify its identity. Record snapshot ID/time, restored database identity, migration
revision, elapsed restore time, recovered data recency, and reviewer separately.
Do not run this against production. Do not label the local synthetic drill as a
successful production recovery test.

## Measured Coverage

Authenticated `GET /v1/ingestion/coverage/measured` accepts `record_type` (parcel,
permit, planning), `limit` (up to 100 sources), `offset`, and `freshness_hours`.
Follow `has_more` for subsequent source pages. Zero-record configured sources
remain visible as zero. Inactive parcel/permit rows are excluded. Counts are
source-scoped identities, not globally deduplicated parcels. The state field uses
recognized US abbreviations (including DC); missing/unrecognized values remain
unknown rather than being inferred from the configured jurisdiction.
The ingestion screen now labels its existing registry totals as configured,
not live. The measured inventory panel on `/source-health` lists 25 sources per
page, with permit/parcel/planning and freshness-window controls. All summary
counts are explicitly current-page measurements, not national totals. The panel
is organization-wide even when another part of the operations page is filtered
to a configured state. Unknown state values are not attributed to that filter.
Changing record type or freshness resets pagination. Failed measurements hide
old totals rather than presenting them as current. A missing older-backend
endpoint produces an unavailable state, never catalog-derived fallback counts.

The API query is disabled without an authenticated organization, and its cache
key includes organization and all filter parameters. The application query
client is additionally recreated on user, organization or role changes; page
state is remounted and prior queries/mutations are cleared. This prevents a
previous identity's cached or late result appearing in the next identity's UI.
It does not cancel already accepted server-side mutation work or replace server
authorization. No persistent browser cache of business records was found.

`recently_seen_records` measures collection recency. `recent_source_date_records`
uses the latest stored raw version's source timestamp. Unknown and future source
dates are separate counts. An old source can be collected today. Neither an
observed state nor a jurisdiction count proves geographic completeness, uptime,
rights to redistribute, verified sale availability, or a statewide parcel total.

## Additional Audit Finding

Public registration without an organization name was found to join the shared
default organization. A separate no-migration security release (PR #113) changes
public signup to provision an isolated workspace and adds session-response guards.
Existing default-organization memberships need an authorized production audit;
do not infer a breach or automatically remove legitimate members.

The browser-session guards do not resolve out-of-order HttpOnly `Set-Cookie`
headers from overlapping auth requests. This remains a separate protocol-level
audit item requiring real-browser cookie-race verification.

A local `alembic check` reports pre-existing model/migration drift: legacy
nullability and index differences plus PostGIS-owned objects. No destructive
autogenerated repair was applied. This needs a reviewed baseline before claiming
drift-free schema checks; successful migration execution is a separate result.
