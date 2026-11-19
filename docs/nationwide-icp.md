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

## Increment 3 (this change) — frontier hotspots (ported, gated dark)

The "why a tenant is converging *here*" layer: within a metro, *where* permit
filing is recent and accelerating. Ported from the stranded research work
(`76bc59a`) onto this branch's privacy-hardened endpoint/panel, keyed by CBSA so
every covered metro gets it through the same coverage registry.

- `frontier_hotspots.rank_hotspots(records, …)` is pure (no DB, no network, no
  clock unless `reference_year` is omitted): it bins the tenant's own geocoded,
  dated permit evidence into ~1 km cells and scores each by ignition —
  `recent · min(acceleration, 5) · (1 + 0.5·dev_share)`, where acceleration is the
  recent-window count over the cell's own prior window. `metro_hotspots(db, cbsa,
  source_keys)` runs it org-scoped and read-only over the metro's declared local
  sources; it returns `insufficient_data` (never fabricated) when the tenant has
  no aligned geocoded evidence.
- `investment_areas.frontier(db, cbsa)` wraps it and is **gated off by default**
  via `FRONTIER_HOTSPOTS_ENABLED` — it ships dark, returning `status: "disabled"`
  with only the honest parcel preview until a workspace opts in. The
  single-metro `investment_area` response carries a `frontier` block.
- The ranked-buyable-parcel + for-sale step stays an explicit
  `research_preview`: it needs external county parcel GIS plus a licensed
  listings feed, is computed offline, and is **not served live** here.
- Honesty gates: a hotspot is a research signal of where land is converting, not
  a verified project/parcel/listing; coverage is partial; acceleration against a
  sparse prior can mislead; it is not calibrated to appreciation.

Frontend: a flagged "Frontier hotspots — Research locator" panel section appears
only when the block is not `disabled`.

Tests: `tests/test_frontier_hotspots.py` (5: scoring/min-recent, malformed-row +
clockless, disabled-by-default, enabled org-scoped ranking, cross-tenant
isolation), panel (+1: enabled shows hotspots/preview, disabled hides section).

## Increment 4 (this change) — appreciation layer as a backtest gate (Phase 3 start)

The last and most gated layer. A metro's rank/tier is a **relative growth
signal**; an appreciation projection requires proof the signal predicted realized
forward price change **out of sample**. This increment ships that proof gate, not
a forecast.

- `appreciation.backtest(observations, …)` is pure: it groups
  `(signal, realized_return, horizon_years)` observations by horizon and reports
  per-horizon rank correlation + top/bottom tercile lift. `status` is
  `calibrated` only when at least `MIN_HORIZONS` horizons each clear
  `MIN_OBSERVATIONS_PER_HORIZON` and `MIN_RANK_CORRELATION` — a conservative floor
  for showing *any* projection, never a performance claim.
- `appreciation.observations_from_snapshot(snapshot)` forms **disjoint** windows:
  for HPI vintages `t0 < t1 < t2`, the signal is the momentum known at `t1`
  (`hpi[t1]/hpi[t0]-1`) and the realized return is the strictly-later
  `hpi[t2]/hpi[t1]-1`. The packaged 2025 reference holds a **single** vintage pair
  (2023 & 2025) — that pair *is* the momentum signal — so it yields **zero**
  observations and the gate stays `insufficient_history`. No appreciation number
  is produced; emitting one would be a predicted return, which this product never
  makes.
- `investment_areas.appreciation(db, cbsa)` wraps it and is **gated off by
  default** via `APPRECIATION_OUTLOOK_ENABLED` — ships dark, returning
  `status: "disabled"` with only an honest withheld-projection preview. Even
  enabled it currently returns `insufficient_history` on the real reference.
- Frontend: an "Appreciation outlook — Not yet backtested" section appears only
  when the block is not `disabled`, and renders **no return figure**.

Tests: `tests/test_appreciation.py` (rank correlation, calibrated-only-with-skill,
three-vintage requirement, insufficient on single vintage, disabled-by-default,
enabled-withholds-projection), panel (+1: gate shown enabled / hidden disabled).

## Coverage registry = the anti-silo backbone

`metro_coverage()` + `has_local_evidence` is the seed of the shared registry: adding
a local permit source for a metro lights it up in the same list the model ranks.
Model growth and coverage growth are one surface.

## Next increments (Phase 1 cont. / Phase 2)

- ✅ Explicit ICP tiering (Strong / Emerging / Stable) — increment 2 above.
- ✅ Gated **frontier hotspots** layer (the "why BJ's is converging here"),
  keyed by CBSA — increment 3 above. Ships dark behind `FRONTIER_HOTSPOTS_ENABLED`.
- ✅ **Appreciation layer as a backtest gate** — increment 4 above. The gate is
  built and ships dark behind `APPRECIATION_OUTLOOK_ENABLED`; it withholds any
  projection and reports `insufficient_history` until multi-vintage HPI history
  clears the skill bar. No projection is served from the single-vintage reference.
- Next: package multi-vintage HPI history so the backtest has disjoint windows,
  then (only if it calibrates) render the realized forward-return distribution for
  a signal band — never a single predicted return.

Not pushed / not merged / not deployed. No source activation or migration.
