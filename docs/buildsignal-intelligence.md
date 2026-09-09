# Institutional intelligence direction

BuildSignals answers: what changed, why might it matter, and where should an
investor investigate capital exposure? The initial product covers land,
development, permits, and infrastructure for institutional real estate teams.

## First increment: assessment preview

`POST /v1/signals/{signal_id}/assessment-preview` resolves an analyst-authored
draft against existing, organization-scoped signals, graph entities, and graph
relationship evidence. Admins and editors may use it. It does not publish or
persist an assessment and does not generate a thesis automatically.

The version 1 contract separates:

- Observed change and optional event date from assessment generation time.
- Investment thesis from source facts.
- Change confidence from thesis confidence, each with an explanation.
- Supporting, contradicting, and contextual citations, classified per claim.
- Affected entities, proposed economic mechanism, direction, and horizon.
- Investigation questions and outstanding review flags.

Citation excerpts, URLs, source identities, and relationship verification dates
come from stored evidence, not the submitted draft. All references must belong
to the current organization. An implication requires included citations, but
reference integrity alone does not establish causation or exposure. An analyst
must review that link. Missing counterevidence means unreviewed, not disproven.
Confidence labels are analyst judgments, not calibrated probabilities or returns.

## Next increments

1. Verify publication concurrency and organization RLS on PostgreSQL, and add
   release-history pagination and external distribution only when required.
2. Build source snapshot comparisons with event time, first-seen time,
   corrections, and idempotent change identity. Preserve approved and pending
   development stages separately.
3. Extend assessment authoring to multiple affected entities and event dates.
4. Link direct asset exposures before inferring second-order nearby effects.
   Separate nearby parcel candidates from verified sale availability.
5. Add licensed debt, securities, and portfolio identifiers and time-bounded
   ownership/exposure edges. These are not supported by the current graph enum.
6. Evaluate precision, freshness, detection lead time, and analyst acceptance
   using historical examples. Claims of mispricing require separate validation.

Use the existing relational graph and ingestion boundaries initially. Keep
domain-specific extraction in connectors; keep assessment and evidence contracts
independent of permit schemas. Broader utilities, demographics, corporate, and
capital-market adapters can then feed the same review workflow.

## Saved revisions and review

Authenticated editors and admins can POST the draft contract to
`/v1/signals/{signal_id}/assessment-revisions`. Each call saves a new snapshot
of the resolved evidence with author and creation time. GET on that path lists
revisions with bounded limit/skip pagination. No update or delete API is exposed.
Snapshots are append-only through the application, not tamper-proof against
database administrators. Organization deletion and signal deletion cascade.

Admins can POST `{decision, rationale}` to
`/v1/assessment-revisions/{revision_id}/reviews`. Decisions are approved,
changes_requested, or rejected; self-review is rejected. GET returns the review
history. Each decision applies only to its specified revision. Approval does
not publish the signal or change the original snapshot's draft status.
Both writes include an audit event in the same transaction. Both tables use
organization-scoped queries and PostgreSQL forced row-level security.

Automatic change detection remains a future increment. Saved revisions and
recorded reviews implement persistence and review history.

## Analyst workspace

The Market Signals detail panel displays saved assessments, evidence excerpts,
safe HTTP(S) source links, graph entity links, confidence rationales,
counterevidence, investigation questions, and revision-specific review history.
Independent admins can record a decision; authors cannot review their own work.
The panel separates review decisions from explicit publication status.

Editors and admins can create a draft in the same panel. The initial composer
supports one affected entity per draft and selects citations from that entity's
stored relationship evidence. It supports distinct stances for change and thesis,
requires change-supporting evidence, and rejects duplicate source/claim pairs.
Confidence defaults to unassessed, not a synthetic score. All included citations
are attached to the single affected-entity implication; backend reference
resolution remains authoritative. Investment causality still requires review.
The API supports multiple implications; the composer does not yet expose that
capability or event-date entry. Missing event dates remain explicitly flagged.

Draft content survives save failures in the mounted form but is not autosaved.
Cancel, navigation, or reload discards unsaved input. Revision and review lists
currently show the first API page (up to 50 records); UI pagination is pending.
Changing the affected entity clears citation selections to prevent stale links.
Read-only viewers do not receive authoring or review controls.

The Market Signals screen now uses stored source, description, creation time,
severity, and opportunity references. It no longer invents priority, confidence,
company relationships, lifecycle milestones, or source counts. Linked opportunities
use the existing graph panel. Search and type filtering apply to the loaded page;
next/previous controls request bounded 50-record API pages. The global header
links to source health instead of claiming a fixed freshness percentage.

## Publication and withdrawal

Authenticated organization members can GET
`/v1/assessment-revisions/{revision_id}/publication` to inspect the latest-first
event history with bounded limit/skip pagination. Admins can POST an action
(`published` or `withdrawn`), rationale, and `expected_version` (0 initially).
Publication requires the latest review to be approved by an identifiable user
other than the identifiable author. A deleted author/reviewer cannot qualify.
Withdrawing a revision preserves its snapshot and all review/release history.

This is an internal, tenant-scoped release state, not anonymous public access,
external distribution, or an application deployment. It applies to a specific
revision; multiple revisions of a signal may be released. A published revision
must be withdrawn before recording another review. Re-publishing checks the
latest approval again. Draft snapshot content is never rewritten as published.

Review and release writes lock the same revision row on PostgreSQL. Publication
events carry a unique per-revision version, and stale clients receive HTTP 409.
Events and audit records commit together. The new table uses forced tenant RLS.
SQLite tests validate transition behavior and migration reversibility but do not
prove PostgreSQL concurrency/RLS behavior; those require PostgreSQL acceptance.
UI history currently displays the first 50 events. No auto-release or external
notifications occur. These tables are application-append-only, not tamper-proof
against database administrators, and parent deletions cascade.

## Production dependencies

This increment does not resolve the outstanding authentication deployment,
backup restore verification, scheduled ingestion activation, or live coverage
measurement. Those remain launch requirements alongside the intelligence work.
