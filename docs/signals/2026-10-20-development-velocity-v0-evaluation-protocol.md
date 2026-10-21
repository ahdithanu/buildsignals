# Development Velocity v0 — Predeclared Evaluation Protocol (P2.2)

Status: **predeclared / provisional**. Date: 2026-10-20. Author: ahdi@uaconsulting.co.
Method: `development-velocity-v0` (score sub-method `development-velocity-score-v0`).
Market: **City of Columbus, OH** (issuing jurisdiction only).
Machine-readable twin: `eval/replay/fixtures/dv_v0_evaluation_protocol.json`.

This document **predeclares** the evaluation protocol for Development Velocity v0
**before any evaluation, backtest, or metric has been run or seen**, per the
institutional roadmap P2.2 (`docs/institutional-intelligence-roadmap.md`:
"Predeclare outcomes/horizons, simple baselines, sample requirements, holdout
periods/markets, false-positive tolerance and lead-time comparator before tuning")
and P2.3 ("thresholds cannot be chosen after seeing results … inconclusive
evidence means hold").

Nothing here runs an evaluation. It fixes the rules so that when the P0.8 corpus
and the P2 harness are ready, the outcome is judged against targets that were set
in advance and are detectably un-tunable afterward.

## 0. Non-negotiable honesty statements

- **The 0-100 score stays UNVALIDATED.** This protocol is a prerequisite gate, not
  a validation. `score_is_validated` remains `False`. The score has no empirical
  calibration, no mapping to an investment outcome, and is not comparable across
  markets (see `app/services/development_velocity.py`, design doc
  `docs/signals/2026-10-18-development-velocity-v0-design.md` §4).
- **This protocol is predeclared and provisional.** Every threshold below was
  chosen before any result was observed.
- **Thresholds must not change after results are seen.** Both this file and the
  JSON twin are hashed/pinned (the JSON is intended to pin exactly like the
  existing `fixtures/thresholds.devvelocity-v0.json`, whose hash already flows into
  `ReplayManifest.thresholds_id` and `run_fingerprint`). A post-hoc edit changes
  the hash and the run identity, so tuning is detectable, not silent.
- **Inconclusive => HOLD.** If the sample floors are not met, or any predeclared
  target is missed, or the result is otherwise inconclusive, the decision is HOLD —
  never a predictive claim (roadmap P2.3).
- **A real run additionally requires the P0.8 corpus, which is NOT yet available.**
  Evaluation needs a qualified, rights-cleared historical Columbus corpus with
  reproducible dates/units/stages/dedupe/gaps and honest
  `first_observed_at`/`recorded_at`. Until P0.8 is accepted, this protocol can be
  declared but not executed as a validation. Offline fixtures and the reference
  method exercise the harness only; they are not qualification.

## 1. Outcome definition and horizon H

**Outcome: `sustained_elevated_activity`. Horizon H = 3 monthly (30-day) windows
(90 days).**

For a signal that **fired** at cutoff `T` (known_then cutoffs only — see §6), the
outcome is **positive** iff, for the same pinned source and the same pinned
attribute (`permit.filed_at` **xor** `permit.issued_at` — never combined), the
observed per-window permit count is **>= the trailing baseline mean computed
as-of `T`** (`baseline_mean_observed_records` at `T`) in **each** of the next `H`
consecutive 30-day windows that fall **strictly after** `T`'s current window.
Otherwise the outcome is **negative** (activity reverted / was not sustained).

Per-source, never summed across sources (two feeds can describe the same project;
one project can have many permits — design §2/§4).

**Why it is cutoff-safe and leak-free:**

- The outcome windows are `w_k = [T + k·30d, T + (k+1)·30d)` for `k = 1..H`, which
  are **strictly after** `T`. The pre-`T` baseline mean is frozen at its `T` value.
- The outcome is read **only** through `activity_baseline()` / `observations_as_of`
  at a single evaluation cutoff `T_eval = T + (H·30) + reporting_lag_days`. That
  reader enforces `first_observed_at <= T_eval`, `recorded_at <= T_eval`,
  `received_at <= T_eval` and the latest interpretation known as-of `T_eval`
  (`docs/signals/2026-10-18-replay-backtest-scaffold-design.md`,
  `app/services/temporal_service.py`).
- Consequently the outcome uses only information that became available **after
  `T`**, and never applies a correction dated **after `T_eval`** — no future-leak,
  no survivorship, no retroactive restatement.
- A fired signal is **evaluable** only if all `H` post-`T` windows end within the
  qualified corpus. Signals whose outcome window is not fully observed are
  `not_yet_evaluable` and excluded from all rates.

H = 3 is a fixed integer set in advance; it is un-tunable post-hoc. v0 claims no
price, deal, or transaction outcome — only persistence of the measured count.

## 2. Simple baseline comparator

The comparator is the **`activity_baseline` trailing comparator** already in the
harness (`eval/replay/driver.py::baseline_run` / `_baseline_crossed`), run as-of
the **same** cutoffs through the same cutoff-safe driver. It "crosses" when a
source's current window `>= baseline_move · baseline_mean`, with the predeclared
**`baseline_move = 2.0`** (matches `fixtures/thresholds.devvelocity-v0.json`). This
is the naive lead-time reference the signal must beat or match; it is deliberately
the existing descriptive layer, not a new model.

## 3. Minimum sample requirements

Below **either** floor the evaluation **must** return
`inconclusive_insufficient_sample` and make **no** validation claim (HOLD):

- **`min_fired_signals = 5`** — at least five known_then, evaluable fired signals.
- **`min_evaluable_periods = 12`** — at least twelve known_then evaluable cutoffs
  (decision + fully observed `H`-window outcome both present).

**Justification (conservative but deliberately small).** Columbus is a single
market with **< 2 complete years** of qualified commercial history
(`docs/columbus-historical-intake.md`; design §3). A 6-window baseline warm-up
(~6 months) plus a 3-window outcome tail (~3 months) consumes most of the usable
span, and overlapping monthly windows are **autocorrelated**, so nominal counts
overstate the independent evidence. Twelve evaluable cutoffs is ~a year of
coverage; five fired signals prevents a claim resting on a handful of fires. These
floors are **necessary, not sufficient**: meeting them permits a measured result,
never an automatic pass.

## 4. Holdout

- **Temporal holdout (v0):** the **most recent contiguous 6 monthly windows** of
  the qualified Columbus corpus are **reserved** — used for out-of-sample reporting
  and excluded from any future threshold-setting or revision. Because every
  threshold here is predeclared (not fit to data), the holdout is the out-of-sample
  window metrics are reported on, and the window against which future tuning is
  forbidden.
- **Market (geography) holdout:** **not possible in v0** — Columbus is the only
  qualified market. Market holdouts are **future work**, required once >= 2 markets
  qualify under P0.8 (the other four markets). No cross-market generalization is
  claimed until then.

## 5. False-positive tolerance and lead-time comparator (fixed values)

- **False-positive definition:** a known_then, evaluable **fired** signal whose
  `sustained_elevated_activity` outcome is **negative** (reverted below the `T`
  baseline mean within `H`).
- **False-positive tolerance = 0.33 (provisional ceiling).** At most one third of
  evaluable fired signals may be false positives. Exceeding it, or an inconclusive
  sample, means HOLD. Un-calibrated; predeclared; not to be tuned afterward.
- **Lead-time comparator = `activity_baseline` trailing comparator** (`baseline_move
  = 2.0`). Lead time is the signed days between the first known_then cutoff at which
  the signal fires and the first cutoff at which the comparator crosses
  (`eval/replay/metrics.py::lead_time_vs_trailing_baseline`). **Predeclared
  acceptance floor: median lead >= 0 days** — the signal must not *lag* the naive
  comparator. This is a comparison only, not a significance claim.
- **Signal-frequency sanity ceiling = 0.5.** A signal that fires on more than half
  of eligible known_then cutoffs is too trigger-happy to be informative (matches
  the thresholds file). A sanity bound, not a validation target.

## 6. known_then vs reconstructed

Only **known_then** cutoffs count toward frequency, lead time, and outcome rates.
`reconstructed` cutoffs (eligible rows recorded in a backfill clustered near the
snapshot freeze, per the driver's `reconstruction_guard`) and `unavailable` /
`insufficient_history` cutoffs are reported separately with counts and never folded
into a denominator (`eval/replay/driver.py::_classify_mode`,
`metrics.py::signal_frequency`). A reconstructed cutoff is never presented as a
signal that was actually emitted at `T`.

## 7. Decision rule

The evaluation produces a **measured result only** and renders no automatic
keep/revise/kill (that is the independent P2.3 go/no-go). The decision is **HOLD**
unless **all** predeclared conditions pass:

1. Sample floors met (§3), else `inconclusive_insufficient_sample` → HOLD.
2. False-positive rate <= 0.33 (§5), else HOLD.
3. Median lead vs the trailing comparator >= 0 days (§5), else HOLD.
4. Result not otherwise inconclusive.

Thresholds cannot be chosen after seeing results; a pass here is still subject to
the independent P2.3 review before any product claim.

## 8. Predeclared values (summary)

| Field | Value |
| --- | --- |
| Outcome | `sustained_elevated_activity` (count >= `T` baseline mean in each of next H windows) |
| Horizon H | 3 windows / 90 days |
| Simple baseline comparator | `activity_baseline` trailing comparator, `baseline_move = 2.0` |
| Lead-time comparator | same; predeclared floor median lead >= 0 days |
| False-positive tolerance | 0.33 (provisional ceiling) |
| Min fired signals | 5 |
| Min evaluable periods | 12 |
| Temporal holdout | final 6 contiguous monthly windows (reserved) |
| Market holdout | none in v0 (single market); future work at >= 2 markets (P0.8) |
| Firing threshold | score >= 70 (provisional, unvalidated; matches thresholds file) |
| Signal-frequency sanity ceiling | 0.5 |
| Inconclusive | => HOLD |

## 9. Gates that remain (unchanged by this document)

This predeclaration is offline, read-only, and authorizes nothing: no ingestion, no
source activation, no worker, no migration, no deployment, no production scoring, no
paid calls. The `development-velocity-v0` score remains unvalidated. A real
evaluation still requires the **P0.8 qualified historical Columbus corpus (not yet
available)**, the frozen/pinned replay manifest (P2.1), and the independent P2.3
go/no-go. Keeping those gates is required by `AGENTS.md` and the roadmap.
