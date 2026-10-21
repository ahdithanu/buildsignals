# Development Velocity v0 — P2.2 Evaluation Report (HOLD)

Date: 2026-10-20. Offline, deterministic, cutoff-safe. This records a P2.2
evaluation RUN of Development Velocity v0 against a **predeclared** protocol. The
0–100 score remains an **UNVALIDATED** research output; this report does not
change that. **Verdict: `insufficient_sample` → HOLD.**

## Protocol was predeclared before any result

The evaluation protocol was predeclared and committed before this run:
`docs/signals/2026-10-20-development-velocity-v0-evaluation-protocol.md` +
`eval/replay/fixtures/dv_v0_evaluation_protocol.json`. Key predeclared values
(un-tunable post-hoc — the file is hashed and its digest flows into the replay
manifest `thresholds_id`):

- Outcome `sustained_elevated_activity`, horizon **H = 3** 30-day windows,
  measured strictly after T via `activity_baseline`/`observations_as_of` at
  `T_eval = T + 90 + reporting_lag` (no future-information leakage).
- Minimum sample: **≥ 5 fired signals AND ≥ 12 evaluable periods**; below either →
  `inconclusive_insufficient_sample` (HOLD).
- False-positive tolerance 0.33; lead-time floor median ≥ 0; baseline move 2.0
  (matches the firing thresholds file).
- Preconditions explicitly NOT met: a qualified historical Columbus corpus
  (roadmap **P0.8**) is `NOT_AVAILABLE`, and `score_is_validated = False`.

## What was run

The cutoff-safe replay driver replayed the **real** Development Velocity v0 signal
(`development-velocity-v0`) over the only available data — the committed Columbus
fixture `eval/replay/fixtures/devvelocity_dv_columbus.jsonl`, which is a
**synthetic, illustrative, non-qualified** time-series, NOT the P0.8 corpus — and
the P2.2 metrics (`eval/replay/evaluate.py`) were applied with the predeclared
protocol. Reproducible: `run_fingerprint c83233…`, `thresholds_id 950205…`.

Signals by cutoff (all `known_then`):

| Cutoff | Status | Score |
| --- | --- | --- |
| 2026-01-05 | insufficient_history | — |
| 2026-01-26 | no_signal | 60.0 |
| 2026-02-02 | fired | 90.4 |

Evaluation result:

- Fired signals: **1** (predeclared minimum 5).
- Decidable outcomes: **0** — the fixture ends well before any fired signal's
  90-day outcome window, so no fired signal is evaluable (`fired_without_decidable_outcome = 1`).
- Evaluable periods: far below the predeclared 12.
- Hit rate / false-positive rate: **not computed** (n = 0 — never reported on an
  empty sample).
- **`verdict = insufficient_sample`.**

## Conclusion: HOLD

Per the predeclared protocol, the sample is below both minimums, so the decision
is **HOLD**. This is an honest "not enough evidence," not a negative or positive
result — no hit rate, lead time, or accuracy is claimed. The evaluation
*machinery* (predeclared protocol, cutoff-safe replay, metrics with sample sizes
+ Wilson intervals, abstaining verdict) is built and tested; what is missing is
the **data**.

## What is required to actually evaluate (not yet done)

1. **P0.8 — a qualified historical Columbus corpus**: rights-cleared, with
   reproducible dates/units/stages/dedup/gaps and honest
   `first_observed_at`/`recorded_at`, deep enough that ≥ 5 fired signals each have
   a fully-observed 90-day outcome window and ≥ 12 evaluable periods exist.
2. Re-run this exact predeclared protocol over that corpus (no threshold tuning).
3. Only if it clears the predeclared bars does DV advance toward P2.3 go/no-go;
   otherwise it stays HOLD. The score stays unvalidated until then.

## Verification

`OPENROUTER_API_KEY= python -m pytest tests/test_replay_development_velocity.py tests/test_replay_evaluate.py -q`
(the backtest over the committed fixture is locked as a test asserting
`insufficient_sample`). Synthetic fixtures are not a qualified corpus; passing
these tests is not a signal validation.
