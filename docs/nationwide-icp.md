# Nationwide ICP + coverage (Phase 1)

Goal: one iterating product where the investment-area **model** and its **coverage**
grow together, not as separate silos. The chain we are building toward:

  nationwide growth signal (ICP)  ->  historical "why a tenant is converging here"
  ->  (later, validated) appreciation projection

This worktree (`codex/nationwide-icp`, off `main` 175fba6) owns Phase 1.

## What was already true (verified)

- `metro-research-v0.3` ranks metros by `0.7 * price-momentum percentile +
  0.3 * supply-surge percentile` (FHFA HPI + Census BPS units). Research-only.
- The committed reference snapshot (`app/data/investment-reference-2025.json`)
  already holds **360 ranked metros + 387 context metros** nationwide.
- The gap was product surface: the panel exposed **2 hardcoded metros** and local
  evidence was mapped only for Ocala (36100). The engine ranked 360; users saw 2.

So "nationwide coverage" is a surfacing problem, not a data-assembly problem.

## Increment 1 (this change) — surface the nationwide ranking

Backend:
- `investment_areas.ranked_markets(snapshot, query, limit, offset)` returns the full
  ordered cohort the model already computes, each row flagged `has_local_evidence`
  from the coverage registry (`metro_coverage()` = metros with a declared local
  permit source). Public snapshot only — identical for every workspace, no tenant
  data, scrubbed of internal source/provenance detail.
- `GET /investment-areas/ranked?q=&limit=&offset=` (role-gated, `no-store`,
  clean retryable 503 on input failure).

Frontend:
- `investmentAreasApi.ranked(...)` + `RankedMarket`/`RankedMarketsResponse`.
- The metro picker is now driven by the ranked cohort (searchable), replacing the
  2-option dropdown. A caption shows "N metros ranked nationwide · ◆ M with local
  permit evidence." Selecting a metro drives the existing detail view unchanged.

Not behind a flag: this extends the already-live research panel additively and keeps
every honesty gate (relative research rank, `investment_quality = insufficient_data`,
no expected-return claim). `has_local_evidence` never influences the score.

Tests: `tests/test_investment_ranked.py` (5) + panel tests (8, incl. 2 new);
full investment suite 119 passed; typecheck clean.

## Coverage registry = the anti-silo backbone

`metro_coverage()` + `has_local_evidence` is the seed of the shared registry: adding
a local permit source for a metro lights it up in the same list the model ranks.
Model growth and coverage growth are one surface.

## Next increments (Phase 1 cont. / Phase 2)

- Explicit ICP tiering (e.g. Strong / Emerging / Stable) layered on the score +
  demand context, clearly research-framed — not just a bare percentile.
- Port the gated **frontier hotspots** layer (the "why BJ's is converging here")
  onto this branch, keyed by CBSA so every covered metro gets it.
- Appreciation projection stays last and gated until backtested against realized
  outcomes.

Not pushed / not merged / not deployed. No source activation or migration.
