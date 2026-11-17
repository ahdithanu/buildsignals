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

## Increment 2 (this change) — explicit ICP tiering

The bare rank/score is now classified into an ICP tier so the growth signal reads
as a profile, not just a percentile:

- `investment_areas.icp_tier(row)` returns `(tier, rationale)` where tier is
  `strong` / `emerging` / `stable`. It lives in `investment_areas`, downstream of
  the snapshot, on purpose: the reference artifact's `code_version` binds the
  ranking/transform code (`investment_model.py` + `investment_inputs.py`), and the
  tier is a read-time classification that does not change the captured snapshot, so
  it is deliberately outside that binding. The tier is set **only** by the two
  scored, cohort-relative percentiles:
  - **strong** — price momentum ≥ P75 **and** supply surge ≥ P60 (both appreciation
    and development lead the cohort — the ideal investment-area profile).
  - **emerging** — blended score ≥ 0.60 but not strong (above-cohort growth, usually
    one dimension leading while the other catches up).
  - **stable** — around or below the cohort on both.
- Population growth / net migration appear in the rationale as **context only** and
  never change the tier — the same gate the score itself keeps.
- `ranked_markets` carries `icp_tier` + `icp_rationale` per row and a
  `tier_counts` distribution over the **full** cohort (stable across search/paging).
- `investment_area` (single metro) carries the selected metro's `icp_tier` +
  `icp_rationale`; `null` when the metro has insufficient aligned history.

Frontend: a tier badge + rationale on the detail header, and the nationwide tier
distribution in the caption ("N metros ranked · X strong · Y emerging · Z stable").
Honesty lines added to both endpoints: the tier is not a return forecast.

Tests: `test_investment_model.py` (+3 icp_tier unit tests), `test_investment_ranked.py`
(+1 cohort-distribution test), panel (+2: badge/rationale, distribution caption).

## Coverage registry = the anti-silo backbone

`metro_coverage()` + `has_local_evidence` is the seed of the shared registry: adding
a local permit source for a metro lights it up in the same list the model ranks.
Model growth and coverage growth are one surface.

## Next increments (Phase 1 cont. / Phase 2)

- ✅ Explicit ICP tiering (Strong / Emerging / Stable) — increment 2 above.
- Port the gated **frontier hotspots** layer (the "why BJ's is converging here")
  onto this branch, keyed by CBSA so every covered metro gets it.
- Appreciation projection stays last and gated until backtested against realized
  outcomes.

Not pushed / not merged / not deployed. No source activation or migration.
