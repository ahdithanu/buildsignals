# P0.8 — Columbus Historical Corpus Qualification (NOT QUALIFIED → HOLD)

Date: 2026-10-20. Offline, deterministic. This qualifies the historical Columbus
corpus against the predeclared P2.2 Development Velocity requirements. **Verdict:
NOT QUALIFIED — insufficient depth. Development Velocity stays HOLD; the 0–100
score remains UNVALIDATED.** This is an honest measurement, not a failure of the
signal: there is not yet enough cutoff-safe history to evaluate it at all.

## The qualification harness (built + tested)

`app/services/corpus_qualification.py` — `qualify_corpus(db, request)`, method
`corpus-qualification-v0`: a pure, offline, cutoff-safe measurement of a pinned
Columbus cohort (reads only via `observations_as_of`, enforcing
`first_observed_at`/`recorded_at <= as_of`; future `as_of` rejected; cross-tenant
rejected). It reports time depth, **recorded-time depth** (the span over which
cutoff-safe replay is even possible), complete 30-day windows, evaluable monthly
periods (`complete_windows − horizon − baseline`), per-stage counts, filing-date
completeness (vs collection-only), duplicate-project rate, and month gaps — and a
verdict `ready` | `insufficient_depth` | `insufficient_completeness` with the exact
shortfall. 10 deterministic tests; depth is gated before completeness.

## What the available Columbus corpus actually is

From the live demo API + the intake/coverage docs
(`docs/signals/2026-10-20-columbus-corpus-p0-8-measurement.md`):

- ~2,108 permit records, overwhelmingly `approved` stage; the activity rollup
  shows only **~5 months, and they are non-contiguous** — filing-dated 2024-01/02/03
  then collection-only 2026-09/10 (issued-date recency, not filing depth).
- Documented site-series filing dates reach back to 2019 but are sparse; the
  commercial catalog is issued-only (no filing-date mapping). Fewer than 2 complete
  filing-dated years exist on any single pinned attribute.

Running the harness on the committed Columbus replay fixture returns
**`insufficient_depth`**: `0 evaluable periods vs 12 required`, `0 max possible
fired signals vs 5 required` (recorded span 27 days → 0 complete monthly windows).

## Why it is decisively insufficient (the known-then point)

P2.2 needs roughly **≥24 contiguous clean filing-dated months** (≈6-window
warm-up + 12 evaluable + 3-window outcome tail, plus a 6-window holdout and margin
for autocorrelation), **≥12 evaluable periods**, and **≥5 fired signals** each with
a fully-observed 90-day outcome. Actual contiguous filing-dated history ≈ **3
months** (Jan–Mar 2024): a gap of ≈ **21 months / 12 evaluable periods / 5 fired
signals**.

The decisive constraint is temporal, not volumetric: that 2024 history was
**captured in 2026** (retrospective intake), so its `recorded_at` knowledge-time is
~now. A cutoff-safe replay only admits observations whose receipt AND recording
times precede the cutoff T, so **the number of cutoff-safe (known-then) evaluable
periods today ≈ 0** — we cannot honestly replay "as known in 2024" because the
system did not know it then. Backfilled archives are labeled retrospective and
cannot be backdated into a known-then timeline.

## What is required to close the gap (none done here)

1. A **rights-cleared P0.8 historical intake** of ≥24 contiguous complete months on
   one pinned Columbus attribute (widen the commercial predicate or use denser
   site filings), with reproducible dates/units/stages/dedup/gaps and **honest,
   non-backdated `recorded_at`** — i.e. going forward, knowledge accrues as it is
   actually received; retrospective archives stay labeled as such.
2. Re-run `qualify_corpus` until it returns `ready`, then re-run the hash-pinned
   P2.2 protocol unchanged (no tuning) under P2.3.
3. Only then can Development Velocity be validated; until then it is HOLD.

## Production audit (specified, not run)

The customer/production workspace Columbus depth is not measurable locally. The
measurement doc specifies a read-only, org-scoped audit over
`permit_records`/`planning_records`/`temporal_observations` — per-month event-date
counts, min/max `recorded_at` and `first_observed_at`, and `source_updated_at`
completeness — to compute the contiguous-complete-known-then month count against
the floors. Running it needs authorization; it does not change this verdict for
the locally measurable corpus.

## Verification

`OPENROUTER_API_KEY= python -m pytest tests/test_corpus_qualification.py -q` (10
deterministic cases; a run over the committed Columbus fixture is locked as
`insufficient_depth`). Synthetic fixtures are not a qualified corpus.
