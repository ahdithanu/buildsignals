# Development Velocity v0 — Design

Status: **design only**. Method id: `development-velocity-v0`. Validation market:
**City of Columbus, OH**. This document specifies the first proprietary signal per
the institutional roadmap (`docs/institutional-intelligence-roadmap.md` P1.1
baselines/change-detection, P1.2 Development Velocity, P1.3 signal object) and the
temporal contract (`docs/temporal-foundation.md`). It authorizes no ingestion,
source activation, worker, migration, deployment, or production scoring. Nothing
here is a validated or predictive output; the 0–100 score is an **unvalidated
research output** until the P2 evaluation gate (P2.1/P2.2/P2.3) is passed.

Development Velocity v0 is a thin, pure computation **layered on top of the
existing descriptive counting layer** `app/services/activity_baseline.py`. That
service already produces cutoff-safe, correction-aware, de-duplicated per-window
permit counts for a pinned Columbus source cohort. v0 does not re-count anything:
it consumes those windows and adds a trailing-mean baseline, a normalized change
measure, an abstention rule, a research score, and a signal object. Reusing the
counting layer means v0 inherits its as-of safety, its latest-interpretation
selection, its ambiguity/overflow handling, and its evidence lineage unchanged.

## 1. Hard constraints (honored and enforced)

These are not aspirational; each maps to a concrete mechanism below.

- **Offline + deterministic — no network, no LLM.** v0 reads only rows already in
  `temporal_observations` through `activity_baseline()`. It calls no LLM client
  (unlike `scoring_service.py`, which has an LLM path) and performs no HTTP fetch.
  Given the same database rows and the same request it returns byte-identical
  output, including a reproducible `request_fingerprint` and `evidence_fingerprint`
  (same construction as `activity_baseline`, via `temporal_service.fingerprint`).
- **Cutoff-safe.** The only data path is `activity_baseline()`, which already
  requires `first_observed_at <= as_of`, `recorded_at <= as_of`, and
  `raw.received_at <= as_of` before a record is eligible, and chooses the latest
  interpretation *before* date/geography filtering. v0 adds no query that bypasses
  this. `as_of` must be timezone-aware and not in the future (enforced upstream).
- **No fabrication.** v0 never invents a count, a date, or a zero. Empty windows
  are counts, not "no activity". Missing baseline history, zero variance, and zero
  baseline are explicit abstention statuses, never coerced to 0 or ∞ (mirrors the
  `numeric_change` contract: `zero_baseline`, `non_numeric`, `numeric_overflow`).
- **Abstain below minimum sample.** Below the configured minimum observed baseline
  records and minimum populated baseline windows, v0 returns a status of
  `abstained_insufficient_sample` with `score = None` and `confidence = low`. It
  never emits a score it cannot support.
- **Confidence stated separately from the score.** The response carries `score`
  (0–100 or null) and, as an independent field, `confidence` (`low`/`medium`/
  `high`/`unassessed`) with a textual `confidence_rationale`. Confidence is derived
  from sample adequacy, coverage flags, and the per-source baseline status — never
  from the score's magnitude. This matches the roadmap's P1.3 requirement and the
  `ConfidenceAssessment` shape in `app/schemas/buildsignal.py`.
- **Unvalidated score.** Every response with a numeric score also carries
  `score_is_validated = False` and a `warnings` list whose first entry states the
  score is a research output pending P2 evaluation. The score is removed entirely
  (null) whenever v0 abstains.

## 2. Inputs, unit of analysis, time grain

### Unit of analysis and geography
- **Market = City of Columbus, OH.** Geography filter is exact
  (whitespace/case-normalized) `city = "Columbus"`, `state = "OH"`, matching
  `activity_baseline`. Per `docs/columbus-historical-intake.md`, the defensible
  pilot boundary is the issuing City of Columbus jurisdiction, **not** the metro or
  a utility service area. v0 inherits that limitation and surfaces it in warnings.
- **Sub-geography:** none in v0. The signal is market-level only. Sub-market
  (parcel cluster, submarket, utility territory) decomposition is explicitly out of
  scope and listed under "Future work".

### Time grain
- **Monthly, approximated as fixed 30-day half-open windows** (the window model
  `activity_baseline` already produces: equal-length, UTC, half-open, ending at
  midnight before the current day minus a reporting lag). v0 keeps `period_days`
  configurable (default 30) rather than true calendar months, because the counting
  layer windows by fixed duration. True calendar-month cohorting and seasonal
  comparability are a **documented v0 limitation** (see §3 seasonality), not
  silently claimed.

### Which observations/counts, over which trailing windows
- **Event unit:** exactly one per computation — `permit.filed_at` (default) **or**
  `permit.issued_at`. Filings and issuances are never combined (the roadmap and the
  intake doc both require this; `ISSUED_DT` is issuance, not filing). The chosen
  attribute is echoed in the output and in the method inputs.
- **Counts:** the per-window `observed_records` already computed by
  `activity_baseline` for each pinned source, de-duplicated by
  `(source_id, external_record_id)` latest interpretation.
- **Trailing windows:** `baseline_periods` trailing windows form the baseline, plus
  1 current window (the `activity_baseline` layout returns `baseline_periods + 1`
  windows, the last being `role="current"`). Default `baseline_periods = 6`
  (six trailing 30-day windows ≈ ~6 months of baseline). This is configurable
  within the counting layer's bounds (3–12).
- **Columbus source cohort (candidate, not accepted):**
  - `columbus_oh_commercial_building_permits` — `permit.issued_at` only (no filing
    date mapping; current production predicate `ISSUED_YEAR >= 2025`).
  - `columbus_oh_site_engineering_applications` — `permit.filed_at`.
  Because the two sources expose different event units, a single v0 computation
  pins **one attribute** and therefore one compatible source (or several sources
  that all expose that attribute). Sources are reported separately and never summed
  — two feeds can describe the same project, and one project can have many permits.

### Required vs optional inputs
- **Required:** `as_of` (aware, not future); `city`, `state`; `attribute`
  (`permit.filed_at` | `permit.issued_at`); `sources` (1–10 pinned
  `{source_id, methodology_version}` cohorts — a version pin per source, exactly as
  `ActivityBaselineRequest`); `period_days`; `baseline_periods`.
- **Optional (with defaults):** `reporting_lag_days` (default 7);
  `minimum_baseline_records` (default 20); `minimum_populated_baseline_windows`
  (new in v0, default 3); `seasonal_adjustment` (default `off`).
- The v0 request **reuses `ActivityBaselineRequest`** as an embedded field so the
  counting contract and its validation (unique sources, bounds, upper-cased state,
  attribute literal) are not duplicated or allowed to drift.

## 3. Baseline

Computed per source, over that source's `baseline_periods` trailing windows
(`windows[:-1]` from the counting layer; `windows[-1]` is the current window).

- **Trailing-N-period mean.** `baseline_mean = activity_baseline`'s
  `baseline_mean_observed_records` (arithmetic mean of the baseline windows'
  `observed_records`). Denominator is `baseline_periods`. Reused verbatim so the
  documented denominator and window definition stay identical across the two layers.
- **Dispersion for the normalized measure.** v0 additionally computes the **sample
  standard deviation** of the baseline windows' counts (Bessel-corrected, divisor
  `n - 1` where `n = baseline_periods`). This is a pure function of the same integer
  counts, so it is deterministic.
- **Documented window / denominator.** Each response echoes `period_days`,
  `baseline_periods`, `reporting_lag_days`, the explicit `[start, end)` of every
  window, and the role of each (`baseline` vs `current`). Nothing about the baseline
  is implicit.
- **Seasonal adjustment — only where sample supports it; off for Columbus in v0.**
  The intake doc establishes Columbus does not yet have comparable history (the
  commercial filter supplies < 2 complete years; proposed floor is 36 consecutive
  comparable months). v0 therefore ships with `seasonal_adjustment = "off"` and
  refuses to turn it on unless `baseline_periods` spans at least a configured
  comparability floor (`SEASONAL_MIN_MONTHS = 24`) of populated windows under one
  pinned method — which the current Columbus cohort cannot meet. When off, the
  response records `seasonal_adjustment_applied = False` and a warning that raw
  trailing comparison is not seasonally controlled. v0 never silently applies a
  seasonal factor it cannot justify.
- **Outages / onboarding / duplicates handled separately from real change.** These
  are already separated by the counting layer and surfaced, not folded into the
  mean:
  - duplicate/ambiguous latest records → excluded and counted in `diagnostics`
    (`ambiguous_latest_records`) with per-source status
    `ambiguous_latest_observation`;
  - missing/cleared/invalid dates, missing/out-of-area geography → `diagnostics`
    buckets, never counted as zero activity;
  - onboarding / thin history → `insufficient_observed_sample` per-source status
    and v0's abstention;
  - source-wide overflow → `bounded_query_exceeded` (no partial baseline).
  v0 treats any per-source status other than a clean baseline as a reason to lower
  confidence and, where the sample floor is not met, to abstain — it does not
  reinterpret a coverage artifact as economic acceleration.

## 4. Change detection

Per source, at cutoff `T`, using `current = windows[-1].observed_records` and the
baseline mean/std above.

- **Absolute delta:** `delta = current - baseline_mean`.
- **Percent change:** `100 * delta / baseline_mean` **only when
  `baseline_mean > 0`**; otherwise `None` with status `zero_baseline` (never divide
  by zero, never substitute ∞ — identical policy to `numeric_change`).
- **Normalized (z-like) measure:** `z = (current - baseline_mean) / baseline_std`
  **only when `baseline_std > 0`**. When `baseline_std == 0` (all baseline windows
  equal, including all-zero), `z = None` with status `zero_variance_baseline`. This
  is a descriptive standardized distance, **not** a probability, p-value, or
  significance claim, and is labeled as such.
- **Minimum-sample abstention rule (hard).** A source produces a numeric change
  only if **both**:
  1. `baseline_total_observed_records >= minimum_baseline_records` (default 20), and
  2. `populated_baseline_windows >= minimum_populated_baseline_windows`
     (default 3), where a window is "populated" if `observed_records > 0`.
  If either fails → per-source `status = abstained_insufficient_sample`, numeric
  fields `None`. This guards against a single spike over an empty history reading as
  a huge z.
- **Missing-history / zero-baseline / edge handling (explicit, never fabricated):**
  | Condition | Status | `delta` | `percent_change` | `z` |
  | --- | --- | --- | --- | --- |
  | Clean, sufficient | `calculated` | number | number \| null* | number \| null* |
  | `baseline_mean == 0` | `zero_baseline` | number | null | null |
  | `baseline_std == 0` (mean>0) | `zero_variance_baseline` | number | number | null |
  | baseline below sample floor | `abstained_insufficient_sample` | null | null | null |
  | source overflow upstream | `bounded_query_exceeded` | null | null | null |
  | ambiguous latest upstream | `ambiguous_latest_observation` | null | null | null |

  *`percent_change`/`z` independently null under their own zero conditions even when
  status is otherwise `calculated` for `delta`.
- **Market roll-up.** v0 reports **per source** and does not sum counts across
  sources. A market-level `score`/`confidence` is derived only from sources that
  reached `calculated`; if none did, the whole signal abstains
  (`status = abstained_insufficient_sample`, `score = None`).

### Research score (0–100, unvalidated)
A bounded, deterministic transform of the normalized measure, present only when at
least one source is `calculated`:

- Per calculated source: `s = 50 + 10 * clamp(z, -5, +5)`, clamped to `[0, 100]`.
  (50 = "at baseline"; each baseline standard deviation ≈ 10 points; clamp keeps it
  bounded and avoids runaway values.) When `z is None` (zero-variance) but `delta`
  is defined, the source contributes no score (it cannot be standardized) and is
  flagged.
- Market `score = round(mean(s_i), 1)` over calculated, standardizable sources.
- `score_is_validated = False` always. The score has **no** empirical calibration,
  no mapping to investment outcome, and is not comparable across markets. It exists
  so the P2 harness has a concrete versioned output to evaluate, nothing more.

## 5. Method id, versioning, and the signal object

### Versioned method id
`development-velocity-v0`. The score sub-method is `development-velocity-score-v0`
and the underlying counting method is the pinned per-source
`methodology_version` plus `activity_baseline`'s `permit-activity-baseline-v1`.
All three appear in the output so a result is fully reproducible and attributable.

### Signal-object fields produced (P1.3 / `buildsignal.py` aligned)
The v0 response is the signal object. It separates facts (counts, windows),
calculations (delta/z/score), and model conclusions (none beyond the labeled score),
and marks unavailable fields explicitly rather than omitting them.

- `method_id`: `"development-velocity-v0"`; `schema_version`: `"1"`.
- `as_of`, `city`, `state`, `attribute`, `period_days`, `baseline_periods`,
  `reporting_lag_days`.
- `status`: one of `calculated`, `abstained_insufficient_sample`,
  `coverage_unverified`, `bounded_query_exceeded`.
- `what_changed`: short deterministic templated string (no LLM), e.g.
  `"Columbus permit.filed_at current-window count 41 vs trailing 6-window mean 27.0 (delta +14.0, z +1.8); score 68.0 (unvalidated)."` Null when abstaining.
- `score`: float 0–100 or `null`. `score_is_validated`: always `False`.
- `confidence`: `low`|`medium`|`high`|`unassessed`; `confidence_rationale`: text.
  Derived from: fraction of sources `calculated`, baseline sample adequacy, presence
  of coverage/ambiguity diagnostics, seasonal-adjustment-off flag. Explicitly
  independent of `score`.
- `historical_comparison`: per source — the full `windows` (start/end/role/count/
  evidence ids), `baseline_mean`, `baseline_std`, `baseline_total`,
  `populated_baseline_windows`, `current`, `delta`, `percent_change`, `z`, per-source
  `status`.
- `cited_drivers`: the underlying records/counts with **evidence ids** — the
  `evidence_observation_ids` per window (resolve via
  `GET /v1/temporal/observations?observation_id=...&as_of=...`), plus each source's
  `evidence_fingerprint` and the `request_fingerprint`. No driver without an
  evidence id.
- `invalidation_conditions`: deterministic list of what would flip/void the signal,
  e.g. "a later correction clears or moves a current-window filing", "source cohort
  methodology re-pin", "baseline falls below minimum sample at a new cutoff",
  "ambiguous latest observation appears in the cohort", "reporting-lag revision
  moves the current window".
- `unavailable_fields`: explicit markers for anything not computed
  (e.g. `["percent_change (zero_baseline)", "z (zero_variance_baseline)",
  "seasonal_adjustment (insufficient comparable history)"]`).
- `warnings`: inherits all `activity_baseline` warnings plus v0's
  "score is an unvalidated research output pending P2 evaluation" and the
  Columbus-jurisdiction / no-seasonality notes.

Fields deliberately **not** produced in v0 (reserved for later, marked unavailable
if a consumer expects them): investment thesis, implications/exposures,
counterevidence search scope, related signals. v0 is the measurement layer; the
analyst-facing `BuildSignalAssessment` (`app/services/buildsignal_assessment.py`)
remains the place where a human attaches a thesis — v0 feeds it, does not replace it.

## 6. Concrete module/function layout for the implementer

Paths and signatures consistent with the existing codebase (mirrors
`activity_baseline.py` + `schemas/activity_baseline.py` + `routes/temporal.py`).

### `app/schemas/development_velocity.py`
```python
from app.schemas.activity_baseline import ActivityBaselineRequest  # reused, embedded

class DevelopmentVelocityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline: ActivityBaselineRequest                 # pins cohort, geography, windows, attribute
    minimum_populated_baseline_windows: int = Field(default=3, ge=1, le=12)
    seasonal_adjustment: Literal["off"] = "off"       # v0: only "off" is accepted

class SourceVelocity(BaseModel):
    source_id: str
    methodology_version: str
    status: Literal["calculated", "zero_baseline", "zero_variance_baseline",
                    "abstained_insufficient_sample", "ambiguous_latest_observation",
                    "needs_coverage_review"]
    windows: list[ActivityWindow]            # reuse schema from activity_baseline
    baseline_mean: float
    baseline_std: float | None
    baseline_total: int
    populated_baseline_windows: int
    current: int
    delta: float | None
    percent_change: float | None
    z: float | None
    source_score: float | None
    evidence_fingerprint: str

class DevelopmentVelocitySignal(BaseModel):
    method_id: Literal["development-velocity-v0"] = "development-velocity-v0"
    schema_version: Literal["1"] = "1"
    request_fingerprint: str
    as_of: datetime
    city: str
    state: str
    attribute: str
    period_days: int
    baseline_periods: int
    reporting_lag_days: int
    status: Literal["calculated", "abstained_insufficient_sample",
                    "coverage_unverified", "bounded_query_exceeded"]
    what_changed: str | None
    score: float | None = None
    score_is_validated: Literal[False] = False
    confidence: Literal["low", "medium", "high", "unassessed"]
    confidence_rationale: str
    seasonal_adjustment_applied: Literal[False] = False
    sources: list[SourceVelocity]
    cited_driver_observation_ids: list[str]
    invalidation_conditions: list[str]
    unavailable_fields: list[str]
    warnings: list[str]
```

### `app/services/development_velocity.py`
```python
METHOD_VERSION = "development-velocity-v0"
SCORE_METHOD_VERSION = "development-velocity-score-v0"
SEASONAL_MIN_MONTHS = 24
Z_CLAMP = 5.0
POINTS_PER_SD = 10.0

def develop_velocity(db: Session, request: DevelopmentVelocityRequest) -> dict:
    """Pure, cutoff-safe Development Velocity v0 over a pinned Columbus cohort.
    Calls activity_baseline() once; never fetches, never calls an LLM."""

# helpers (all pure given the baseline report):
def _baseline_stats(window_counts: list[int], baseline_periods: int) -> tuple[float, float | None, int, int]:
    """mean, sample std (n-1, None if <2 or zero variance handled by caller), total, populated count."""
def _change(current: int, mean: float, std: float | None,
            baseline_total: int, populated: int, request) -> dict:
    """delta / percent_change / z / per-source status, with all explicit edge states."""
def _source_score(z: float | None) -> float | None:
    """50 + POINTS_PER_SD * clamp(z, -Z_CLAMP, +Z_CLAMP), clamped to [0,100]; None if z is None."""
def _confidence(sources: list[dict], seasonal_off: bool) -> tuple[str, str]:
    """(level, rationale) from sample adequacy and coverage flags — never from score."""
def _what_changed(attribute, current, mean, delta, z, score) -> str
def _invalidation_conditions(sources: list[dict]) -> list[str]
```
`develop_velocity` flow: call `activity_baseline(db, request.baseline)`; if its
`status` is `bounded_query_exceeded`, pass that through with `score=None`,
`confidence="low"`; otherwise, for each source compute stats + change + source
score; roll up market score over `calculated` standardizable sources; derive
confidence; assemble the signal object; append warnings (inherit baseline's).
`request_fingerprint` built with `temporal_service.fingerprint` over
`[org_id, METHOD_VERSION, SCORE_METHOD_VERSION, canonical_request]` so it is
distinct from the baseline fingerprint and reproducible.

### `app/routes/temporal.py` (add one endpoint; no new router needed)
```python
@router.post("/development-velocity", response_model=DevelopmentVelocitySignal)
def get_development_velocity(payload: DevelopmentVelocityRequest, db: Session = Depends(get_db)):
    try:
        return develop_velocity(db, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc   # unknown/foreign source cohort
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc    # bad cutoff / bounds
```
Authentication and tenant scoping come from the existing router dependency
(`Depends(get_current_user)`) and `activity_baseline`'s org-scoped queries.

### Deterministic unit tests — `tests/test_development_velocity.py`
Reuse the `cohort` fixture pattern from `tests/test_activity_baseline.py`
(same `_cohort_factory`, `request_for`, monkeypatched `temporal._utcnow`,
fixed `AS_OF`/`END`). All tests are offline and deterministic. Cases:

1. **happy path** — seed baseline windows with known counts and a larger current
   window; assert `status == "calculated"`, exact `delta`, `baseline_mean`,
   `baseline_std`, a finite `z`, a bounded `score` in `[0,100]`,
   `score_is_validated is False`, and that `score` and `confidence` are reported
   as separate fields.
2. **abstain on thin baseline** — fewer than `minimum_baseline_records` /
   `minimum_populated_baseline_windows`; assert `abstained_insufficient_sample`,
   `score is None`, `confidence == "low"`, numeric fields null.
3. **zero baseline** — all baseline windows empty, nonzero current; assert
   `zero_baseline`, `percent_change is None`, `z is None`, no divide-by-zero, and
   `"percent_change (zero_baseline)"` in `unavailable_fields`.
4. **zero-variance baseline** — all baseline windows equal nonzero; assert
   `zero_variance_baseline`, `z is None`, `delta`/`percent_change` present.
5. **cutoff safety / no look-ahead** — late-received, late-interpreted, and
   future-effective records excluded exactly as in the baseline test; result at an
   earlier `as_of` abstains or shows the pre-change state.
6. **correction removes current-window count** — a latest correction clearing or
   moving the current-window filing lowers `current` and changes `delta`
   deterministically (reuses the baseline correction cases).
7. **determinism / reproducible fingerprint** — same request twice, and a
   reordered-sources / whitespace-city / shifted-timezone equivalent request, yield
   identical `request_fingerprint`, identical per-source numbers, and identical
   `score`.
8. **ambiguous latest observation** — tie in latest recorded times → source
   `ambiguous_latest_observation`, excluded from the market score, confidence
   lowered.
9. **overflow passthrough** — monkeypatch `activity_baseline.MAX_COHORT_ROWS = 1`;
   assert signal `status == "bounded_query_exceeded"`, `score is None`,
   `sources == []`.
10. **seasonal adjustment refused** — `seasonal_adjustment="off"` is the only
    accepted literal; `seasonal_adjustment_applied is False` and the
    no-seasonality warning is present.
11. **score bounds** — a very large current count clamps `z` to ±5 so `score`
    stays within `[0,100]` (no runaway).
12. **auth + cross-tenant** — unauthenticated `POST /v1/temporal/development-velocity`
    → 401; a foreign/unknown source cohort → 404; future `as_of` → 422 (mirrors the
    baseline endpoint test).

A `permit-activity-baseline` PostgreSQL companion
(`tests/test_development_velocity_postgres.py`) is optional and gated the same way
as `test_activity_baseline_postgres.py`; SQLite tests do not substitute for the
PostgreSQL RLS/restore drill (per the temporal release boundaries).

## 7. Explicit non-goals / future work (v0 boundaries)

- No calendar-month cohorting or seasonality (needs ≥ ~36 comparable Columbus
  months; not available).
- No sub-market / parcel / utility-territory decomposition.
- No cross-source project de-duplication or project-count claim (sources reported
  separately; counts are source records, not projects).
- No acceleration (second derivative), anomaly probability, or significance test.
- No persistence of the signal as a row, no publication, no alerting — v0 is a
  read-only computed object. Human theses and publication remain in the existing
  `buildsignal_assessment` / assessment-publication path.
- No score validation: calibration, backtesting, false-positive/lead-time
  measurement, and the independent go/no-go are the P2 gates and are prerequisites
  before the score is presented as anything but a research output.
