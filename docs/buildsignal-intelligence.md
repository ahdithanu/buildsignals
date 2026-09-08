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

1. Persist immutable assessment revisions with author, review status, and audit
   history. Add organization RLS and explicit approval before publication.
2. Build source snapshot comparisons with event time, first-seen time,
   corrections, and idempotent change identity. Preserve approved and pending
   development stages separately.
3. Add analyst review and evidence navigation to the existing signals UI.
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

Publication, withdrawal, review UI, and automatic change detection remain future
increments. Saved revisions and recorded reviews implement the persistence and
review-record portion of step 1 above.

## Production dependencies

This increment does not resolve the outstanding authentication deployment,
backup restore verification, scheduled ingestion activation, or live coverage
measurement. Those remain launch requirements alongside the intelligence work.
