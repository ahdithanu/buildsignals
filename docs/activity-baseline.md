# Permit Activity Baseline

This is a descriptive historical-data qualification tool, not the validated
Development Velocity signal in the institutional PRD. It does not establish
citywide coverage, forecast development, or recommend an investment.

## API

`POST /v1/temporal/activity-baseline` is an authenticated, read-only query. The
request body pins a city, state, event attribute, and exactly one normalization
methodology per source. Source IDs and methodology versions can be obtained from
the tenant's temporal observations. A source from another tenant and an unknown
source both return the same 404. Clients cannot set the organization.

Example body (replace the example source ID and method with observed values):

```json
{
  "as_of": "2026-09-19T00:00:00Z",
  "city": "Columbus",
  "state": "OH",
  "attribute": "permit.filed_at",
  "sources": [
    {
      "source_id": "SOURCE_ID_FROM_OBSERVATIONS",
      "methodology_version": "EXACT_VERSION_FROM_OBSERVATIONS"
    }
  ],
  "period_days": 30,
  "baseline_periods": 6,
  "reporting_lag_days": 7,
  "minimum_baseline_records": 20
}
```

The same endpoint supports `permit.issued_at`. Filings and issuances are never
combined. Sources are reported separately: two providers can describe the same
permit, and multiple permits can describe one development project.

## Counting Contract

- The cutoff must be timezone-aware and cannot be in the future.
- Raw receipt, observation receipt and interpretation time must all be at or
  before the cutoff. Historical data imported today is not treated as known last year.
- The service chooses the latest interpretation per source and external record
  ID within the pinned methodology. Graph identity changes cannot double-count
  that source record.
- Latest selection precedes date and geography filtering. Correcting a date,
  clearing it, or moving a project outside the chosen city removes its old count.
- Tied latest timestamps are ambiguous, not ordered by random UUID to choose a
  winner. Those records are excluded and flagged for review.
- Dates must be timezone-aware strings consistent with the observation's
  effective time. Unknown, cleared and invalid dates are diagnosed separately.
- Geography uses whitespace/case-normalized city/state labels, not a spatial
  boundary. Missing geography is not imputed. This is not metropolitan coverage.
- Equal-length half-open windows end at UTC midnight before the current day,
  minus the reporting lag. The lag is not a measured provider-latency guarantee.
- Zero observations are a count, not proof that nothing happened or that a feed
  is complete. The sample threshold is not a completeness test.
- Records never projected into temporal observations are outside this query.
  Missing-date diagnostics describe observed history, not every missing date in
  the underlying provider feed or canonical inventory.

## Output And Limits

Each source returns chronological windows, counts, an arithmetic historical
mean, at most five observation IDs per window, exclusion diagnostics, and an
evidence fingerprint. Evidence IDs resolve through
`GET /v1/temporal/observations?observation_id=...&as_of=...` with authentication
and the same cutoff. The request fingerprint includes the tenant, canonical request and baseline
method version; the evidence fingerprint identifies the selected immutable rows.

Every response with counts has `status=coverage_unverified` and `score=null`.
Sources may report `insufficient_observed_sample`, `needs_coverage_review`, or
`ambiguous_latest_observation`. A positive count in every window does not qualify
the source. No growth percentage, acceleration score or causal claim is returned.

Requests allow 1-10 sources, 7-90 days per period, 3-12 baseline periods, and
0-60 days of reporting lag. If the source cohort exceeds 50,000 historical rows
or 20,000 latest rows, the result is `bounded_query_exceeded` with no partial
baseline. History input is capped before window ranking, and the overflow count
is evaluated in the same SQL statement. These are source-wide bounds applied
before date/geography filtering so corrections cannot be missed. Narrowing the
city or date window does not bypass a source-wide limit. A
tenant/source/attribute/method/time index supports candidate selection. Larger
histories need query-plan/load testing and likely incremental materialization
before raising the bound. There is no background refresh or external fetch here.

Pinned methods deliberately ignore later reinterpretations under other mapping
versions. Comparing a new method requires a new explicitly reviewed cohort;
these results are not a silently mixed latest-method view. Raw source removals
are not tombstones yet, so disappearance alone does not retract a historical
filing. Temporal records themselves are append-only, subject to tenant erasure.

## Qualification Before A Signal

1. Audit source meaning, retention limits, filters, timezone and version history.
2. Reconcile historical provider totals against ingested records by period;
   retain manifests, missing-page checks, duplicate counts and exceptions.
3. Estimate reporting delay and revisions from repeated captures. Freeze the
   source cohort and document geographic scope and overlapping records.
4. Complete live PostgreSQL isolation, migration, and performance verification.
5. Backtest the proposed Development Velocity methodology, including false
   positives, seasonality and source-policy changes, before exposing a score.

Configured feeds and this endpoint alone satisfy none of those qualification
gates. The first release remains diagnostic only.
