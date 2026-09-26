# Demo readiness, September 9, 2026

Deployment is on hold by request. Local completion is not a claim that the public
website or production ingestion has been updated.

## Verified locally

- Evidence-backed assessment authoring, saved snapshots, independent review.
- Explicit admin publication/withdrawal with rationale, version checks, audit.
- Authenticated registration/login/API workflow through save, second-user review,
  publish, viewer denial, and withdrawal.
- Tenant-scoped reference resolution and hidden cross-tenant revisions.
- Stored signal metadata, bounded pagination, working loaded-page search/type
  filtering, and opportunity graph navigation.
- Removed hardcoded signal companies, confidence/priority scores, milestone dates,
  source counts, global freshness numbers, and inert signal action buttons.
- Full backend suite: 921 passed, 6 skipped. Parcel-focused backend suite:
  33 passed. Frontend suite after parcel fixes: 110 passed. Production frontend
  build passes with the existing large-bundle warning.
- Isolated SQLite upgrade, downgrade, and re-upgrade of the publication migration.
- Desktop/mobile browser checks with explicitly mocked local test records.
- Parcel detail renders at 1440px and 390px without horizontal overflow.
- Real local browser login, cookie refresh after navigation, graph evidence
  selection, draft save, second-account review, publication, withdrawal, and
  reload persistence against an isolated backend.
- CORS on early authentication errors, preserving allowed-origin browser refresh
  without granting untrusted origins access. Authentication requests and silent refresh
  have 30-second deadlines rather than unbounded sign-in loading.
- Sign-in no longer advertises fabricated coverage, unsupported SOC 2/SAML,
  or nonfunctional session controls. Registration and password reset remain.

## Still required before claiming demo-ready end to end

- Verify the intended demo organization's real ingested records and graph evidence.
  Do not pass test fixtures off as live opportunities.
- Review other demo routes for placeholder content; cleanup above covers Signals
  the login page, and the global header, not every page in the application.
- PostgreSQL RLS/concurrency acceptance for publication transitions.
- Confirm authentication rollout changes, backend migrations, and frontend API
  configuration together when deployment is authorized.
- Production freshness, backup/restore, and live ingestion activation remain
  separate operational acceptance checks, not proven by UI tests.

## Follow-on functionality

- Multi-entity assessment authoring and event-date input.
- Revision, review, and publication-history UI pagination.
- Source version comparisons and durable change identity.
- Verified portfolio/exposure linkage and analyst evaluation metrics.

## Parcel acceptance

The existing parcel workflows cover bounded 0.25-5 mile searches, buyer-lens
ranking, ownership/fact evidence, boundaries, split/merge lineage, shortlisting,
assignment, outreach/follow-up, explicit opportunity promotion, and reviewed
policy-controlled CSV exports. Dedicated backend tests exercise those behaviors.

Additional fixes preserve the saved search's anchor, radius, and persona while
new controls are edited; reset invalidated anchor selection; retain the true
closest distance independently of the highest score; and reject unsafe source
URL schemes in parcel facts, lineage, and nearby-result evidence links.

These are acquisition candidates, not verified for-sale listings. Actual sale
availability requires an authorized listing/broker source or explicit current
owner evidence. Source licensing and live parcel coverage are not established by
passing workflow tests. Those input and production checks remain open.

## Demo sequence

1. Sign in to the intended organization with an author account.
2. Open Signals, select a stored record, and inspect its source and opportunity.
3. Open the opportunity graph and inspect relationship evidence.
4. Save an assessment citing stored evidence and recording uncertainty.
5. Use a separate admin to record an independent review.
6. Explicitly publish with a rationale; verify history and author separation.
7. Withdraw, confirm the retained history, and record a revised review.

Publication here releases a revision within the organization. It does not deploy
the application, publish a public web page, or send a recommendation externally.

## Repeat the local browser check

`node scripts/verify_assessment_workflow.cjs` uses the installed Playwright
Chromium browser. It requires an isolated, migrated backend on 127.0.0.1:8191
and a frontend on 127.0.0.1:4189 configured to use that backend. Allow that
frontend origin in local CORS and use insecure refresh cookies only for local
HTTP. The script rejects non-loopback target hosts. Optional overrides are
`ASSESSMENT_TEST_API` (including `/v1`) and `ASSESSMENT_TEST_WEB`.

It creates uniquely named synthetic users, organizations, and records clearly
labeled LOCAL TEST, and leaves them in the isolated test database. Do not point
the test backend at production or an actual demo organization's database. The
script does not supply evidence for actual investment opportunities.
