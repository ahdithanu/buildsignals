# Commercial Readiness Audit - September 9, 2026

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
| P1 | Login.tsx does not submit TOTP although auth.py requires it for enrolled users | Submit optional code; test enrolled and unenrolled sign-in, rejection, retry, and mobile layout |
| P1 | User.totp_secret is a plain string; twofa.py stores the shared secret directly | Encrypt with separately managed keys; migrate existing secrets; test rotation and recovery without logging secrets |
| P1 | Production restore and application-role isolation are unverified | Restore isolated PostgreSQL copy; record schema, isolation, measured RPO/RTO, reviewer and date |
| P1 | 41 configured parcel feeds are not verified live inventory | Measure unique parcels, failed imports, latest source dates and geographic extent for each marketed market |
| P1 | Enterprise checklist treats configuration as completion | Separate implemented, CI verified, production verified, and externally audited for each claim |
| P2 | Canonical live login has no CSP header; vercel.json has no CSP | Test report-only policy against real API/analytics/assets, then enforce without breaking auth or maps |
| P2 | SSO/SCIM and billing are recorded as unimplemented in roadmap | Qualify buyer requirements; do not advertise SSO. Use explicit pilot contract/invoicing until built |
| P2 | Mobile customer workflow is not fully verified | Test registration, MFA, alert, evidence, timeline, parcel selection, save and export at 390px and desktop |

Priority reflects launch triage, not a formal vulnerability severity rating.
TOTP storage finding does not establish that the database has been compromised.
Transport and disk encryption do not replace separate protection of MFA secrets.

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
