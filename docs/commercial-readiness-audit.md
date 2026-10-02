# Commercial Readiness Audit - September 9, 2026

Implementation follow-up: [Security and coverage evidence release](security-evidence-release.md)
records local verification, newly discovered missing RLS policies, and the
remaining production gates. Findings below retain their original audit context,
with resolved items called out explicitly rather than silently removed.

This is a scoped code/configuration review and public-header check, not a
penetration test, certification, or guarantee of investment results.

## Release Evidence

PR 110 merged. GitHub reports its main-commit Vercel deployment completed.
The canonical public login returns HTTP 200. Authenticated production workflows,
backend migration completion, and live ingestion are not established by that.
Prior local suites: 928 backend passed / 6 skipped; 110 frontend passed.

## Prioritized Findings

| Priority | Gap and evidence | Acceptance gate |
| --- | --- | --- |
| P1 | Production MFA key provisioning and legacy-secret backfill are unverified | Provision managed `MFA_ENCRYPTION_KEYS`/`MFA_ACTIVE_KEY_ID`, run dry-run and apply backfill, set `MFA_ALLOW_LEGACY_PLAINTEXT=false`, verify enrolled login and document key recovery |
| P1 | Production restore and application-role isolation are unverified | Restore isolated PostgreSQL copy; record schema, isolation, measured RPO/RTO, reviewer and date |
| P1 | 41 configured parcel feeds are not verified live inventory | Measure unique parcels, failed imports, latest source dates and geographic extent for each marketed market |
| P1 | Enterprise checklist treats configuration as completion | Separate implemented, CI verified, production verified, and externally audited for each claim |
| P2 | Canonical live login has no CSP header; vercel.json has no CSP | Test report-only policy against real API/analytics/assets, then enforce without breaking auth or maps |
| P2 | SSO/SCIM and billing are recorded as unimplemented in roadmap | Qualify buyer requirements; do not advertise SSO. Use explicit pilot contract/invoicing until built |
| P2 | Mobile customer workflow is not fully verified | Test registration, MFA, alert, evidence, timeline, parcel selection, save and export at 390px and desktop |

Priority reflects launch triage, not a formal vulnerability severity rating.
The remaining MFA finding is a production evidence gap. Local code now protects
new MFA enrollments with application-level encrypted storage, but the deployed
environment still needs key provisioning, legacy backfill evidence, and
legacy-read disablement before the gate can be closed. Transport and disk
encryption do not replace separate protection of MFA secrets.

## Resolved Since Audit

| Original priority | Resolved item | Verification receipt |
| --- | --- | --- |
| P1 | Login submits optional TOTP codes and permits retry after rejection. Backend still rejects enrolled users without a valid code. | `tests/test_2fa.py` and `tests/test_mfa_secrets.py` pass 23 backend tests; `src/test/build-signals-wireframes.test.tsx` passes five frontend tests, including authenticator-code submission and retry. |
| P1 | New MFA enrollment no longer stores the shared secret as plaintext. Secrets are written as authenticated, user-bound ciphertext under a separately provisioned versioned key ring, and legacy plaintext is cleared on storage/backfill. | `tests/test_2fa.py` and `tests/test_mfa_secrets.py` pass 23 backend tests covering encrypted storage, randomized ciphertext, tamper rejection, missing-key failure, legacy-read gating, atomic backfill, rotation, disable cleanup, and export omission. |

## Buyer Acceptance

For a VP of Development: validate a buyer-selected market and acreage/use
criteria, show recent source-backed projects, explain parcel ranking and missing
zoning/access facts, identify ownership evidence, and save/export a shortlist.
Never label assessor inventory as verified for sale.

For an institutional real estate investor: reproduce what was known at a given
date, show corrections and contradictory evidence, explain company/subsidiary
matching confidence, and preserve analyst approval and export provenance.
Security review, permitted data use, retention/deletion, and support terms must
be explicit before accepting sensitive customer research or portfolios.

## Commercial Proof

Run a paid-pilot evaluation in agreed markets rather than promising nationwide
completeness. Record source freshness percentiles, manually labeled brand-match
precision, detection lead time versus a documented comparison date, qualified
opportunities, false positives, and buyer time saved. Agree evaluation thresholds
with each buyer in advance. Four-figure monthly pricing is a hypothesis to test
against this value; it is not established by feature count or passing tests.

Do not claim SOC 2, independent penetration testing, an SLA, or production
recovery guarantees without supporting evidence. Assign an accountable owner
and verification date to each unresolved gate before calling it complete.
