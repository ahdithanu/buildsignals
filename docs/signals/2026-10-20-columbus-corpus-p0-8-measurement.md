# Columbus Corpus Depth Measurement vs P2.2 Readiness (roadmap P0.8)

Date: **2026-10-20**. Author: ahdi@uaconsulting.co. Scope: honest, read-only
measurement of how much historical Columbus data **actually exists** today and
whether it can support the predeclared P2.2 Development Velocity v0 evaluation
(`docs/signals/2026-10-20-development-velocity-v0-evaluation-protocol.md`). This
document only measures and specifies; it activates nothing and authorizes nothing.
It is not source qualification, not commercial-reuse clearance, and not P0.8
acceptance.

## 0. Non-negotiable honesty statements

- **Collection recency is not filing depth.** A month appearing in the activity
  rollup because records were *collected* recently says nothing about how many
  months of *filing-dated* history exist.
- **recorded_at depth — not event-date depth — bounds cutoff-safe backtesting.**
  Publisher event dates reaching back to 2019 (site) / 2010 (building) do **not**
  make those months evaluable. A known_then backtest needs trusted
  `first_observed_at`/`recorded_at`/`received_at` **<= cutoff**
  (`app/services/temporal_service.py`; replay design
  `docs/signals/2026-10-18-replay-backtest-scaffold-design.md`). A 2019 event first
  captured in 2026 is a retrospective archive, not a 2019 known_then observation
  (`docs/columbus-historical-intake.md` "Historical Availability Contract").
- This measures stored demo-cohort inventory and documented source depth. It is
  **not** the authenticated production/customer workspace, which is not measurable
  locally (see §5).

## 1. Live demo API measurement (read-only)

Unauthenticated demo token from `POST /v1/auth/demo`, then bearer `GET`.
Fetched **2026-10-20** against `https://www.buildsignals.ai`.

`/v1/demo/summary` (snapshot `captured_at` = 2026-10-20T21:51:46Z):

| Field | Value |
| --- | ---: |
| `permit_records` | 2,108 |
| `graph_entities` | 5,056 |
| `relationships` | 8,418 |
| `parcel_references` | 1,091 |
| `parcel_records` | 0 |
| `mapped_permits` | 938 |
| `derived_geocoded_permits` | 938 |
| `mapped_filing_locations` | 420 |
| `mapped_parcels` | 0 |

`/v1/demo/activity` — stages: `approved` 2,053, `pre_approval` 55;
`records_considered` 2,108. Months rolled up (the time depth the endpoint exposes):

| Month | `filed` | `issued` |
| --- | ---: | ---: |
| 2024-01 | 72 | 587 |
| 2024-02 | 70 | 589 |
| 2024-03 | 66 | 665 |
| 2026-09 | 27 | 0 |
| 2026-10 | 32 | 0 |

**Read of the time depth.** Only **5 months** surface, and they are **not
contiguous** — three in Q1 2024 and two in late 2026, with an ~29-month hole
(2024-04 … 2026-08). The three 2024 months carry populated filings *and*
issuances; these correspond to the bounded Jan–Mar 2024 local qualification intake
(`docs/columbus-historical-intake.md`: 208 site filings + 1,841 commercial issuances
= 2,049 source records). The two 2026 months carry **`filed` only, `issued` = 0** —
consistent with recent collection recency, not filing-outcome depth.

**Source-update-date completeness: not determinable from the demo.** The demo
exposes neither per-record `source_updated_at` nor min/max event dates. Its
`captured_at` is assembly time, not publication/change time. The coverage contract
(`docs/measured-coverage.md`, `app/services/ingestion/measured_coverage.py`)
separates collection recency (`last_seen_at`) from source update date
(`RawSourceRecord.source_updated_at`) and flags unknown/future source dates
explicitly; none of that distribution is visible here. The intake audit also
recorded a **future-date anomaly** (max commercial `LAST_STATUS_DT`
2026-10-23/2026-10-30, beyond the audit date) that must be quarantined before any
freshness/baseline use.

## 2. Documented Columbus depth and stages

From the local docs (source-evidence review only; no production inspection):

- **Site engineering** (`columbus_oh_site_engineering_applications`): filing date
  `B1_FILE_DD -> filed_at`. Public source event dates **from 2019**; exact-catalog
  rows **3,499** (earliest 2019-01-03, latest 2026-09-16). But annual filings are
  **sparse** — 47 (2019), 34 (2020), 41 (2021), 225 (2022), 792 (2023), 858 (2024),
  890 (2025), 612 (2026 partial). Status mapping still lacks a verified city
  lifecycle dictionary.
- **Commercial building permits** (`columbus_oh_commercial_building_permits`):
  `ISSUED_DT -> issued_at`, **no filing-date mapping**. Production predicate
  `ISSUED_YEAR >= 2025` deliberately keeps **< 2 complete years** (11,862 rows,
  2025-01-02 … 2026-09-17). This series therefore cannot supply `permit.filed_at`
  depth at all; P2.2 pins one attribute (`filed_at` **xor** `issued_at`, never
  combined — protocol §1).
- **Attestation** (`docs/releases/2026-10-17-columbus-coverage-attestation.md`): the
  public demo cohort holds ~5 months of activity rollup; dated extent of the cohort
  itself is an explicit unknown; parcels 0; production/customer coverage NOT
  attested.
- **P2.2 minimums** (protocol §1, §3, §4): outcome `sustained_elevated_activity`,
  **H = 3** 30-day windows (90-day fully-observed outcome tail per fired signal);
  **min_fired_signals = 5**; **min_evaluable_periods = 12**; ~**6-window baseline
  warm-up**; **final 6 contiguous monthly windows reserved** as temporal holdout.
  Below either floor → `inconclusive_insufficient_sample` → HOLD.
- The committed P2.2 run already returned **`insufficient_sample` → HOLD** on the
  synthetic fixture (1 fired, 0 decidable outcomes); the missing ingredient is a
  qualified **P0.8** corpus
  (`docs/signals/2026-10-20-development-velocity-v0-evaluation-report.md`).

## 3. P2.2-readiness computation (honest)

**Span required (contiguous monthly, 30-day windows):**

```
  6 months  trailing baseline warm-up (before the first evaluable cutoff)
+12 months  evaluable cutoffs (each = decision + fully-observed H outcome)
+ 3 months  H=3 (90-day) outcome tail after the last cutoff
---------
 21 months  bare arithmetic minimum of clean contiguous monthly history
```

Reserving a **separate final 6-window holdout** out of threshold-setting (§4), and
because overlapping monthly windows are **autocorrelated** (protocol §3 — nominal
counts overstate independent evidence), the realistic floor is **≈ 24 consecutive
clean monthly periods** with populated filing dates. (The intake audit's own
first-market gate proposes an even higher **36-consecutive-complete-month** floor;
the current commercial filter cannot pass it.)

**What actually exists (demo cohort / documented ingested history):**

- Contiguous clean months with populated **filing** dates actually ingested: **3**
  (2024-01…2024-03, site filings 72/70/66).
- Total distinct activity months surfaced: **5**, but non-contiguous (the two 2026
  months are `filed`-only collection recency, not an evaluable continuation).
- Commercial series contributes **0** filing-dated months (issued-only).

**Quantified GAP:**

| Dimension | Required (P2.2) | Actually present | Gap |
| --- | ---: | ---: | ---: |
| Clean contiguous monthly history (filing-dated) | ≈ 24 months (21 bare min) | 3 months | **≈ 21 months** (≥ 18 vs bare min) |
| Evaluable periods | 12 | 0 | **12** |
| Fired signals w/ fully-observed 90-day outcome | 5 | 0 | **5** |

**Deeper bound (the decisive one): known_then `recorded_at` depth ≈ 0.** Even the 3
contiguous 2024 months are **present-day retrospective snapshots captured in 2026**
(`columbus-...-202401-live` runs; "Capture timestamps reflect now, not 2024"), so
they do not supply `recorded_at <= cutoff` observation history for 2024 cutoffs. The
earliest genuine known_then observation history begins only with 2026 collection.
Therefore the number of **cutoff-safe, known_then evaluable monthly periods today is
effectively 0**, regardless of how far publisher event dates reach. **Verdict:
P2.2 is almost certainly insufficient — HOLD stands.**

## 4. What closing the gap requires (rights-gated historical intake)

- A bounded, **rights-cleared** historical intake (roadmap **P0.8**) admitting
  ≈ 24+ consecutive complete monthly periods for a single pinned attribute
  (`filed_at` xor `issued_at`) in the City of Columbus issuing jurisdiction, with
  reproducible dates/units/stages/dedupe/gaps and honest
  `first_observed_at`/`recorded_at` that are **not backdated** from publisher event
  dates.
- For a `filed_at` evaluation, the **commercial `ISSUED_YEAR >= 2025` predicate must
  be widened** under a separately approved older-history scope (it has no filing
  mapping and < 2 complete years today), or the **site filing series** used — whose
  pre-2022 years are too sparse to fill contiguous months.
- Resolve the intake audit's open **first-market gates**: verified stage dictionary,
  Approved/closed/expired/issued/completed disposition, future-date anomaly
  quarantine, timezone/year consistency, correct freshness semantics, and measured
  null/blank/duplicate rates — none of which the demo can establish.
- Then re-run the **predeclared** protocol unchanged (hash-pinned; no threshold
  tuning) and submit to the independent **P2.3** go/no-go. The 0–100 score stays
  **UNVALIDATED** until then.

## 5. Production-audit specification (spec only — NOT run here)

The production/customer-workspace Columbus depth is **not measurable locally** and
was not measured. A production run would execute the following **read-only,
authenticated, org-scoped** audit against the production org only (tenant-scoped,
RLS-enforced; `GET /v1/ingestion/coverage/measured` is the product surface, but the
depth question needs per-month event-date/`recorded_at` rollups). Illustrative SQL
over `permit_records`, `planning_records`, `temporal_observations`:

```sql
-- 0) Pin the production org and scope EVERY query by it (RLS + explicit filter).
--    :org_id = the production organization id. Read-only; no writes, no DDL.

-- 1) Per-month EVENT-DATE counts (filing depth), per source + attribute.
--    Run once with event_col = filed_at, once with issued_at — never combined.
SELECT source_key,
       date_trunc('month', filed_at) AS event_month,
       count(*)                      AS n_records,
       count(filed_at)               AS n_dated
FROM permit_records
WHERE organization_id = :org_id
  AND jurisdiction_city = 'Columbus'          -- issuing jurisdiction only
  AND is_active                               -- exclude inactive rows
GROUP BY source_key, event_month
ORDER BY source_key, event_month;

-- 2) recorded_at depth (bounds cutoff-safe backtesting) per source.
SELECT source_key,
       min(recorded_at)  AS min_recorded_at,
       max(recorded_at)  AS max_recorded_at,
       min(first_observed_at) AS min_first_observed_at,
       count(*) FILTER (WHERE recorded_at IS NULL) AS n_null_recorded
FROM temporal_observations
WHERE organization_id = :org_id
  AND jurisdiction_city = 'Columbus'
GROUP BY source_key;

-- 3) source_updated_at completeness / unknown / future-dated rates.
SELECT source_key,
       count(*)                                           AS n,
       count(source_updated_at)                           AS n_source_dated,
       count(*) FILTER (WHERE source_updated_at IS NULL)  AS n_unknown_source_date,
       count(*) FILTER (WHERE source_updated_at > now())  AS n_future_source_date
FROM permit_records
WHERE organization_id = :org_id AND jurisdiction_city = 'Columbus' AND is_active
GROUP BY source_key;

-- 4) Repeat (1)-(3) for planning_records (planning signal depth), same org scope.
```

The audit would then compute, per source and pinned attribute: the count of
**contiguous complete monthly periods** that have both populated event dates **and**
`recorded_at <= period_end` (known_then), apply the ≈24-month / 12-evaluable /
5-fired floors, and report unavailable periods as **unknown, never zero**. Capture
the timestamp, record type, source pages, and freshness window with the result.
Running it requires production authentication/authorization that is **not held
here**; this section is a specification, not an executed measurement.

## Honesty note

Measured demo-cohort inventory (2026-10-20) and documented source depth only. These
are not distinct projects, not for-sale inventory, and not production coverage.
P2.2 readiness is **insufficient** today: the gap is ≈ 21 months of clean
contiguous filing-dated history, 12 evaluable periods, and 5 fired signals with
observed outcomes — and, decisively, ≈ 0 known_then `recorded_at` depth. Decision
stays **HOLD** until a rights-cleared P0.8 corpus exists and the predeclared
protocol is re-run unchanged under P2.3.

Evidence: `/v1/demo/{summary,activity}` (live, 2026-10-20);
`docs/releases/2026-10-17-columbus-coverage-attestation.md`;
`docs/columbus-historical-intake.md`; `docs/measured-coverage.md`;
`docs/signals/2026-10-20-development-velocity-v0-evaluation-{protocol,report}.md`;
`docs/institutional-intelligence-roadmap.md` (P0.8, line 146).
