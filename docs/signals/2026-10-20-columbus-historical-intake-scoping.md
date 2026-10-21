# P0.8 — Columbus Historical Intake Scoping (DV-validation blocker)

Date: 2026-10-20. Offline desk review; no source accessed, nothing activated.
This scopes what a **rights-cleared ≥24-month historical Columbus intake** would
have to be to let `qualify_corpus` return `ready` and unblock a real P2.2
evaluation of Development Velocity v0. It authorizes **no** collection, activation,
migration, or commercial reuse — those are gated steps requiring the authorizations
named in §5. Companion facts: the committed P0.8 measurement and qualification
reports and `docs/columbus-historical-intake.md`.

## 0. The headline finding (read this first)

Scoping surfaced a decisive constraint: **a historical archive pull alone cannot
validate Development Velocity.** DV is evaluated by cutoff-safe *known-then* replay,
which admits an observation only when both its receipt and its recording time
precede the cutoff T (`observations_as_of`). An archive of 2019–2024 filings
*captured in 2026* carries `recorded_at ≈ 2026` for every row, so its
`recorded_time_depth ≈ 0` and it yields **~0 known-then evaluable periods** no
matter how deep its event dates run. Honest options are therefore:

- **Track P (the real unblock): prospective collection going forward.** Begin
  capturing the pinned Columbus series now, so `recorded_at` accrues genuinely over
  time. ~24 months of real-time capture produces leakage-free known-then depth.
  This is the only path that honestly validates DV, and it starts the clock today.
- **Track R (descriptive only): the retrospective archive.** A rights-cleared
  historical pull, labeled "observed at capture time," supports descriptive
  baselines, seasonality context, and dense-fixture testing of the harness — but
  **not** cutoff-safe DV validation, and its event dates must never be backdated
  into `recorded_at`.

Recommendation: pursue both — Track P to actually unblock DV (and to make the
24-month wait productive), Track R to give baselines and the harness real depth now
— but set expectations that **validation is ~24 months of prospective capture away**
unless separately evidenced non-backdated historical receipt can be established.

## 1. Target series (pinned)

One series, never combined (the harness pins `permit.filed_at` XOR
`permit.issued_at`):

- **entity-type** `permit`, **attribute** `permit.filed_at`, **stage**
  `permit.approval_stage = "approved"`, **source**
  `columbus_oh_site_engineering_applications`.

Why this one: it is the **only** catalogued Columbus series with a genuine
filing-date mapping (`B1_FILE_DD → filed_at`, `historical_intake.py:30`). The
commercial-permit source (`columbus_oh_commercial_building_permits`) is
**issued-only** (`ISSUED_DT → issued_at`, no filing mapping) and capped to 2025+ by
its `ISSUED_YEAR >= 2025` predicate, so it contributes **zero** filing-dated months
and is out of scope for this series. Site-engineering filing density is adequate
from **2022 onward** (225 / 792 / 858 / 890 rows for 2022–2025; 47/34/41 in
2019–2021 — too sparse to fill contiguous months), so a window of roughly
**2023-01 forward** is the candidate span for ≥24 contiguous complete months.

## 2. Access path

- **Paged ArcGIS query API only.** Both sources use the `arcgis` adapter
  (`connectors/arcgis.py`). The site layer is
  `maps2.columbus.gov/arcgis/rest/services/Schemas/BuildingZoning/MapServer/22/query`.
  There is **no bulk-export or archive endpoint** in the repo — "bulk" means
  repeated keyset paging. Date-windowed historical pulls already follow
  `historical_intake.py` (≤31-day `WHERE` interval on `B1_FILE_DD`, bounded pages).
- **Harness paging bound:** `qualify_corpus` scans within `offset <= 10000`,
  `PAGE_SIZE=500`; a pinned cohort must stay inside it or it returns
  `bounded_query_exceeded`. A 24–36-month `approved` cohort (~1,800–2,600 rows) fits.
- Pre-2000 commercial lives in separate **uncatalogued "Historic" layers**
  (`FeatureServer/92`, `Historic_Building_Permits/FeatureServer/0`) whose rights,
  counts, date ranges and joinability are **unaudited** — out of scope until
  examined.

## 3. Record schema the intake must emit (per `qualify_corpus` contract)

Each record becomes one `TemporalObservation`. Required per record:

| Field | Requirement |
| --- | --- |
| `entity_id` | References a `permit` `GraphEntity`; this is the project / dedup unit. Distinct real projects → distinct `entity_id` (duplicates measured by `entity_id`). |
| attribute | exactly `permit.filed_at` (stage carried as parallel `permit.approval_stage` observations). |
| `value` / `effective_at` | tz-aware ISO-8601 datetime, equal to the filing date; naive/missing/mismatched → counts as collection-only against completeness. |
| source / method | a `SourceCohort` pin `{source_id, methodology_version}`, `source_type == "permit"`, one methodology version per source, 1–10 sources. |
| `first_observed_at` | from trusted raw `received_at`; must be `<= as_of`. |
| `recorded_at` | **honest ingest time; never backdated** to the filing date. Must be `<= as_of` and (for a real P2.2 run) spread across history so `recorded_span_days` is non-trivial. |
| geography | `{city: "Columbus", state: "OH"}` (casefolded); missing/mismatched drops the record. |

Dedup key (cutoff-safe latest interpretation):
`series_key = fingerprint([entity_id, source_id, external_record_id, attribute, methodology_version])`.

## 4. Acceptance checklist — advancing toward `ready`

**Important — `ready` is intentionally unreachable from timestamps alone.** The
harness verdict falls through `insufficient_depth` → `insufficient_completeness` →
**`insufficient_coverage`**, and `coverage_audited` is hardcoded `False` with no
code path that sets it (`corpus_qualification.py:285,340-343`). So a corpus that
satisfies every condition below still returns **`insufficient_coverage`**
("independently audited per-window source coverage and known-then availability are
required; timestamp span alone cannot qualify a corpus"). Clearing 1–8 is necessary
but NOT sufficient; an independent coverage audit (condition 9) is the final gate
and is deliberately a human/attested step, not something the intake can self-certify.

Conditions, all at the evaluation `as_of`:

1. **Event-date depth:** `complete_windows >= 21` (event-date span ≥ ~630 days) so
   the event-date bound `complete_windows − 9 >= 12` (also clears `min_fired_signals = 5`).
2. **No month gaps:** ≥1 eligible dated record in every 30-day window index
   `0..complete_windows−1` → `month_gaps == 0`.
3. **Completeness:** `event_date_completeness >= 0.95` (≤5% collection-only/invalid-date).
4. **Duplicates:** `duplicate_project_rate <= 0.10` (distinct `entity_id` per project).
5. **Geography / non-empty:** every counted record Columbus/OH; `cohort_records > 0`.
6. **Known-then depth:** `evaluable_periods = min(event-date bound, known_then
   bound)`, where the known-then bound derives from elapsed time since the
   **earliest** `recorded_at` (`corpus_qualification.py:247-254`). So besides 21
   event-windows you also need ~21 months of elapsed recording time since capture
   began — the gate Track R (archive captured ≈now) collapses to ~0, and Track P
   (prospective capture) accrues over real time.
7. **Honest recorded_at:** every record `first_observed_at <= as_of` and
   `recorded_at <= as_of`, never backdated to the event date.
8. **Scan bound:** cohort within the paging bound (`scan_overflow == False`).
9. **Independent coverage audit (final gate):** an external, attested per-window
   source-coverage + known-then-availability audit must certify the corpus; until
   then the verdict is `insufficient_coverage` by design. There is currently **no
   mechanism** in the harness to supply this attestation — adding one (an explicit,
   signed, dated coverage-audit input that sets `coverage_audited`, defaulting off)
   is an open design decision, not an assumed step.

Only once 1–9 hold does the verdict become `ready`; then re-run the **hash-pinned
P2.2 protocol unchanged** (no threshold tuning) under P2.3 for the go/no-go. `ready`
is a necessary P0.8 gate only — not source activation, commercial-reuse clearance,
or score validation.

## 5. Rights & authorization gates (preserve every hold)

- **No `legal_hold`/`technical_hold` tag to "clear":** neither Columbus source is a
  candidate-catalog entry; they are `catalog.json` rollout-wave entries (rollout
  membership ≠ activation).
- **License recorded and verified:** both are **CC0 1.0 Universal**,
  `attribution_required: true`, verified in the official ArcGIS item `licenseInfo`
  (not merely copied). CC0 supports reuse, but **operational admission is NOT
  cleared** — "CC0 metadata was verified; operational admission was not."
- **What must be obtained (authorization, not hold-clearing):**
  1. Written **P0.8 rights-cleared-intake authorization** + first-market "Rights and
     admission" sign-off (owner, method version, dated evidence, reviewer).
  2. Source/item-specific rights + attribution review with the publisher, **City of
     Columbus Department of Building & Zoning Services**; approved field set; PII
     suppression (applicant names/contacts/attachments/geometry already suppressed);
     a bounded collection plan.
  3. A **separate operational activation authorization** before any live run.
- **Parcel/land candidates** (Columbus CSIR, Franklin County Auditor) are
  **unknown — need written clearance**; "public download availability does not by
  itself qualify commercial redistribution, privacy scope, or coverage." No
  Columbus utility/infrastructure source is catalogued.

## 6. Known data hazards to handle before baseline use

- **Future-date anomaly** in the commercial layer (`LAST_STATUS_DT` up to
  2026-10-23/-30) must be quarantined before any freshness/baseline use.
- `source_updated_at` on the site source is a current-status timestamp
  (`LAST_STATUS_DT`), **not** a filing event — do not relabel it `filing_event_at`.
- Demo cohort dated extent, per-record `source_updated_at` completeness, and the
  authenticated **production/customer** workspace depth are **not measurable
  locally**; the production corpus audit (specified, unrun) needs authorization.

## 7. Suggested execution split (if co-developing with Codex)

See the handoff's "Parallel tracks" block. Clean, non-overlapping ownership so no
two agents write the same file:

- **Harness + acceptance + eval** (owner A): `app/services/corpus_qualification.py`,
  `tests/test_corpus_qualification.py`, `eval/replay/*`, this doc, `docs/agent-handoff.md`.
- **Connector + source intake** (owner B): the Columbus ArcGIS adapter path /
  `historical_intake.py` widening, `candidate_catalog.json` / `catalog.json`
  Columbus entries, intake fixtures, `docs/source-qualification/*`.

The record schema in §3 is the interface contract between the two tracks; once it is
fixed, the tracks do not touch each other's files. `catalog.json`,
`candidate_catalog.json`, migrations, `render.yaml` and this handoff each have a
single owner at a time (AGENTS.md Operating Mode). Neither track activates a source.

## Verification

No code changed by this scoping; `qualify_corpus` and its locked
`insufficient_depth` fixture test are unchanged. The verdict stands: **NOT
QUALIFIED → HOLD**, DV score UNVALIDATED, nothing activated.
