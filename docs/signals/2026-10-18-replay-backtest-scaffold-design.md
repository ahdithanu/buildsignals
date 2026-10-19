# Cutoff-Safe Replay / Backtest Scaffold (Design)

Status: design only. Date: 2026-10-18. Author: ahdi@uaconsulting.co.

This document designs the **P2.1 "Cutoff-safe replay and versioning"** scaffold and
the minimal **P2.2** evaluation skeleton that will wrap the forthcoming
Development Velocity v0 signal. It authorizes no deployment, no worker, no source
activation, and no production data access. Replay runs offline against isolated
local or explicitly approved evaluation data only.

This is a replay and reproducibility harness, not a backtester that establishes a
signal works. Per `institutional-intelligence-roadmap.md` P2.2/P2.3, outcome
definitions, holdouts, and go/no-go acceptance are later work; thresholds are
predeclared before any result is seen and are never tuned afterward.

## Goals And Non-Goals

**Goals**

- Given a method id + version and a sequence of cutoffs `T`, produce the signal
  as-of each `T` using only eligible observations, deterministically and
  reproducibly (repeated runs give byte-identical results).
- Freeze and pin: source snapshots, entity mappings, features, and method/code
  versions, into a single verifiable manifest.
- Honor the temporal AS-OF eligibility contract already enforced by
  `app/services/temporal_service.py` so no future information or later correction
  leaks into an as-of-`T` answer.
- Distinguish genuine **known-then** replay from **retrospective reconstruction**,
  and never invent history that was not available at `T`.
- Provide a minimal, non-UI evaluation skeleton with metric stubs and a
  per-cutoff reproducibility check.

**Non-goals (explicitly deferred)**

- No outcome/holdout labeling, hit-rate, false-positive rate, or lead-time
  acceptance verdict (P2.2 proper). We stub the metric surface and record the
  predeclared thresholds, nothing more.
- No score validation, no tuning, no market-coverage claim, no terminal/UI.
- No new network sources, no graph-as-of reconstruction (a later graph feature;
  temporal observations already carry frozen `entity_id` snapshots).

## Temporal Contract We Build On

The temporal service already enforces the eligibility rule. Replay reuses it
verbatim rather than reimplementing time filtering:

- Observations eligible at cutoff `T` require **both** `first_observed_at <= T`
  (trusted receipt, derived from `RawSourceRecord.received_at`) **and**
  `recorded_at <= T` (server-assigned interpretation time).
  See `observations_as_of(...)` in `app/services/temporal_service.py:125`.
- Events additionally require their own `recorded_at <= T`
  (`events_as_of(...)`, `temporal_service.py:153`).
- Series are partitioned by `(entity_id, source_id, external_record_id,
  attribute, methodology_version)` via `observation_series_key(...)`
  (`temporal_service.py:33`); different sources or interpretation versions are
  never silently compared.
- Ordering is deterministic: `recorded_at DESC, id DESC`.

Consequence, which the scaffold depends on and tests: a correction or backfill
whose `recorded_at` is after `T` is invisible at `T`. An old filing imported
today, or old raw bytes reprojected today, both carry `recorded_at = today` and
are therefore excluded from any cutoff before today. This is exactly the
roadmap's time-proof fixture and the behavior our unit tests pin.

## Where This Lives

Mirror the existing top-level `eval/` harness (`eval/bench.py`,
`eval/golden.jsonl`, `eval/models.json`, writing `eval/results.*`). Replay is
multi-module, so it is a subpackage `eval/replay/` with a `bench.py`-style CLI
entry, and its fixtures/manifests live beside it checked into the repo for
reproducibility.

```
eval/
  bench.py                      # existing model-routing benchmark (unchanged)
  golden.jsonl                  # existing
  models.json                   # existing
  replay/
    __init__.py
    run.py                      # CLI entry (argparse, mirrors bench.py main())
    driver.py                   # replay driver: produce signal as-of each T
    manifest.py                 # freeze + pin snapshots/mappings/features/versions
    signals.py                  # SignalFn protocol + registry of method ids
    metrics.py                  # P2.2 metric STUBS + reproducibility check
    thresholds.py               # load predeclared thresholds (never tuned)
    fixtures/
      devvelocity_v0_known_then.jsonl     # deterministic known-then series
      devvelocity_v0_with_correction.jsonl# same series + later-dated correction
      thresholds.devvelocity-v0.json      # predeclared outcomes/thresholds
    README.md                   # how to run; emphasizes offline + isolated data
  replay_results/               # run outputs (gitignored except a pinned sample)
    <run_id>/manifest.json
    <run_id>/signals.jsonl
    <run_id>/metrics.json
    <run_id>/reproducibility.json
```

Tests follow the existing `tests/test_temporal_*.py` and `tests/test_eval_*.py`
naming: `tests/test_replay_driver.py`, `tests/test_replay_manifest.py`,
`tests/test_replay_metrics.py`.

## Component 1: The Replay Driver

### Signal interface

The Development Velocity v0 signal (forthcoming, P1.2) is injected, not hardcoded,
so the driver stays domain-neutral like `temporal_service`. A method is a pure
function of `(db, as_of, series, method_version)` whose only time input is
`as_of` — it must read nothing from the wall clock, no RNG, no network.

```python
# eval/replay/signals.py
from typing import Protocol
from datetime import datetime
from sqlalchemy.orm import Session

class SignalResult(Protocol):
    status: str          # "fired" | "no_signal" | "unavailable" | "insufficient_history"
    value: float | None  # method-defined magnitude, or None
    drivers: list[dict]  # cited observation/event ids (evidence lineage)
    method_version: str

class SignalFn(Protocol):
    def __call__(
        self, db: Session, *, as_of: datetime, series: "SeriesSpec", method_version: str
    ) -> SignalResult: ...

# Registry pins method id -> (callable, supported versions). Development
# Velocity v0 registers here once P1.2 lands; until then only the fixture
# reference method is registered.
REGISTRY: dict[str, "MethodEntry"] = {}

def get_method(method_id: str, method_version: str) -> SignalFn: ...
```

`SeriesSpec` names the cohort under replay: an explicit list of
`series_key`s (or `(entity_id, attribute)` pairs resolved to series keys through
`observation_series_key`) plus the pinned `methodology_version`. It is frozen in
the manifest so the cohort cannot drift between runs (no survivorship leakage —
the cohort is fixed before the run, not selected from survivors at `T`).

### Driver signature

```python
# eval/replay/driver.py
@dataclass(frozen=True)
class CutoffSignal:
    as_of: datetime
    status: str
    value: float | None
    drivers: list[dict]
    fingerprint: str          # fingerprint(canonicalized result) for reproducibility
    mode: str                 # "known_then" | "reconstructed" (see below)

@dataclass(frozen=True)
class ReplayRun:
    manifest: "ReplayManifest"
    signals: list[CutoffSignal]   # one per cutoff, in ascending as_of order

def replay(
    db: Session,
    *,
    method_id: str,
    method_version: str,
    cutoffs: Sequence[datetime],   # each MUST be timezone-aware (UTC)
    series: "SeriesSpec",
    manifest: "ReplayManifest",
) -> ReplayRun: ...
```

For each cutoff `T` (sorted, de-duplicated, each tz-aware or we raise exactly as
`observations_as_of` does), the driver:

1. Resolves the `SignalFn` from the registry for `(method_id, method_version)`;
   a missing/unknown version is a hard error, never a silent fallback.
2. Calls the signal, which internally reads eligibility-filtered rows **only**
   through `observations_as_of` / `events_as_of` / `numeric_change` at `as_of=T`.
   The driver asserts the method touched no other data path (see determinism
   guards). Values that do not exist yet surface as `unavailable` /
   `insufficient_history` — the driver copies that through and never fabricates a
   zero, an interpolation, or a carried-forward value.
3. Classifies `mode` for that cutoff: **known_then** if every eligible driver
   observation's `recorded_at` precedes `T` by at least the manifest's
   `reconstruction_guard` margin (i.e., the knowledge genuinely existed before
   `T`); **reconstructed** if eligible rows were recorded in a backfill clustered
   near the snapshot freeze time. Reconstructed cutoffs are labeled, reported, and
   excluded from any known-then-only metric; they are never presented as a signal
   that was actually emitted at `T`. (Mirrors `temporal-foundation.md`: a
   retrospective simulator must label simulated output separately.)
4. Canonicalizes the result with `fingerprint(...)` from `temporal_service`
   (sorted-key, finite-only JSON SHA-256) and stores it.

### Determinism guarantees and how they are enforced

- **Single time input.** The only clock the method sees is `as_of`. No
  `datetime.now()`, no `_utcnow()`, no RNG, no env-dependent branch. The driver
  runs methods with a guard that fails the run if the method calls the real
  clock (patch `temporal_service._utcnow` / `datetime.now` to raise during
  replay reads; writes are not permitted during replay at all).
- **Frozen snapshot.** Replay runs against an isolated snapshot database whose
  content hash is pinned in the manifest (see Component 1b). Because the live
  temporal store is append-only and reads are `recorded_at`-bounded, a frozen
  snapshot plus a fixed cutoff list yields a fixed input set.
- **Stable ordering.** Inherited from `observations_as_of` (`recorded_at DESC,
  id DESC`). The driver sorts cutoffs ascending and never relies on dict/set
  iteration order.
- **Canonical output.** Every result and the whole run are hashed with the same
  `fingerprint` used across the temporal layer, so "identical results" is a
  checkable equality of `run_fingerprint`, not a visual diff.
- **No writes.** The driver opens the session read-only; any attempted temporal
  write (ORM listeners/DB triggers already reject update/delete) is also blocked
  at the driver layer so a buggy method cannot mutate the snapshot mid-run.

### Component 1b: Freezing and pinning (the manifest)

```python
# eval/replay/manifest.py
@dataclass(frozen=True)
class ReplayManifest:
    run_id: str
    created_at: datetime            # recorded for provenance only, never read by the method
    method_id: str
    method_version: str
    code_version: str               # git rev of the repo at run time
    module_hashes: dict[str, str]   # sha256 of signals.py/driver.py/the method module
    snapshot_id: str                # content hash of in-scope raw records + observations + events
    series: "SeriesSpec"            # frozen cohort (no post-hoc selection)
    entity_mapping_id: str          # hash of the entity_id snapshots in scope (graph merges frozen)
    feature_version: str            # feature/normalization method string, e.g. canonical-observation-v1:<hash>
    cutoffs: list[datetime]
    thresholds_id: str              # hash of the predeclared thresholds file
    data_scope: str                 # "local_fixture" | "approved_local_snapshot" — gates the run
    reconstruction_guard: timedelta

def freeze(db, *, method_id, method_version, series, cutoffs, thresholds, data_scope) -> ReplayManifest: ...
def verify(db, manifest: ReplayManifest) -> None:   # re-hash snapshot; raise on drift
```

What each pin buys us:

- **Source snapshots** — `snapshot_id` is the SHA-256 over the in-scope
  `RawSourceRecord` rows (content-addressed already) plus the `TemporalObservation`
  / `TemporalEvent` rows for the cohort. `verify()` re-hashes before a run and
  refuses to proceed on any drift, so a mutated snapshot cannot silently change
  results.
- **Entity mappings** — temporal observations carry historical `entity_id`
  snapshots and are deliberately not graph foreign keys
  (`temporal-foundation.md`), so a later graph merge cannot rewrite history.
  `entity_mapping_id` hashes those snapshots to make the frozen mapping explicit.
- **Features** — `feature_version` is the method/normalization string already
  embedded in `methodology_version` (e.g. `canonical-observation-v1:<norm-hash>`).
- **Method/code versions** — `method_version`, `code_version`, and
  `module_hashes` pin exactly what logic ran. A version bump forces a new run;
  results across versions are never compared implicitly.
- **data_scope** — the run refuses to start unless scope is `local_fixture` or
  `approved_local_snapshot`. There is no path to production data.

## Component 2: Minimal Evaluation Skeleton (no UI)

`eval/replay/metrics.py` consumes a `ReplayRun` and the predeclared thresholds and
emits JSON only (no terminal, no chart), matching how `bench.py` writes
`results.*`. All three are **stubs** in the roadmap sense: they compute the
mechanical quantity and record the predeclared threshold, but render no
keep/revise/kill verdict (that is P2.2/P2.3).

```python
def signal_frequency(run: ReplayRun) -> dict: ...
def lead_time_vs_trailing_baseline(run: ReplayRun, *, baseline: "BaselineRun") -> dict: ...
def reproducibility_check(run_a: ReplayRun, run_b: ReplayRun) -> dict: ...
def evaluate(run: ReplayRun, *, baseline, thresholds, repro_run) -> dict:  # bundles all three
```

1. **Signal frequency** — fraction of known-then cutoffs where `status == "fired"`
   (reconstructed and unavailable cutoffs reported separately with counts, never
   folded into the denominator silently). Output: `{fired, eligible_cutoffs,
   frequency, reconstructed_excluded, unavailable_excluded, threshold}`.

2. **Lead time vs a naive trailing-average baseline** — the baseline is the
   existing descriptive trailing comparator, `activity_baseline(...)` in
   `app/services/activity_baseline.py` (its `baseline_periods` trailing windows),
   run as-of the same cutoffs through the same driver so it is cutoff-safe too.
   The metric reports, per cohort, the first cutoff at which the replayed signal
   fires minus the first cutoff at which the trailing baseline crosses its
   predeclared move — a signed lead-time delta in days, plus `unavailable` when
   either never fires in the cutoff range. It computes the comparison; it does
   not assert the lead time is real or significant (that needs P2.2 outcomes and
   sample sizes).

3. **Per-cutoff reproducibility check** — re-run the identical
   `(manifest, cutoffs)` and assert, per cutoff, `signal.fingerprint` equality,
   and overall `run_fingerprint` equality. Output lists any cutoff whose
   fingerprint diverged (expected: none). This is the concrete meaning of
   "repeated runs give identical results."

**Predeclared outcomes / holdouts / thresholds.** `eval/replay/thresholds.py`
loads `fixtures/thresholds.<method>.json` (hashed into the manifest as
`thresholds_id`) **before** the run. The file carries placeholders for the P2.2
fields — `outcome_definition`, `horizon_days`, `holdout_periods`,
`holdout_markets`, `false_positive_tolerance`, `min_sample_size`,
`lead_time_comparator` — each marked `status: "predeclared_pending_P2.2"`. The
metrics read thresholds; they never write them back. Because the thresholds hash
is in the manifest, a post-hoc edit changes the run identity and is therefore
detectable — thresholds cannot be chosen after seeing results.

## Component 3: Deterministic Unit Tests

All tests run offline on disposable SQLite (as the temporal suite does), use the
checked-in fixtures, and assert fingerprint equality rather than fuzzy matches.
A reference fixture method (a trivial `numeric_change`-based signal) stands in for
Development Velocity v0 so the scaffold is testable before P1.2 lands.

`tests/test_replay_driver.py`

- **Known-delta reproduces an identical signal.** Load
  `devvelocity_v0_known_then.jsonl` (a series with a known step change), replay
  over fixed cutoffs, assert the as-of-`T` signal `status`/`value` match the
  fixture's expected values and the `run_fingerprint` equals a pinned constant.
- **Determinism.** Run `replay(...)` twice on the same manifest; assert identical
  `run_fingerprint` and per-cutoff fingerprints (this is `reproducibility_check`
  at the test layer).
- **A later-dated correction does not change the earlier result.** Load
  `devvelocity_v0_with_correction.jsonl` — identical to the known-then series
  plus one correction row with `recorded_at = T_corr` after an earlier cutoff
  `T_before`. Assert the as-of-`T_before` signal is byte-identical to the
  no-correction run, and that the correction only appears at cutoffs `>= T_corr`.
  This is the roadmap's time-proof fixture expressed as a test.
- **No fabrication before data exists.** For a cutoff before the first
  `first_observed_at`/`recorded_at`, assert `status in {"unavailable",
  "insufficient_history"}` with `value is None` — never 0, never carried-forward.
- **Clock/RNG guard.** Assert the run fails loudly if the registered method calls
  the real clock or attempts a temporal write during replay.
- **known_then vs reconstructed labeling.** A backfilled series (rows recorded
  near snapshot freeze) is labeled `reconstructed` and excluded from the
  frequency denominator; a genuinely-aged series is labeled `known_then`.

`tests/test_replay_manifest.py`

- `freeze()` then `verify()` passes on an untouched snapshot; mutating any
  in-scope row (or appending one) changes `snapshot_id` and makes `verify()`
  raise. Thresholds-file edit changes `thresholds_id`.
- A run with `data_scope` other than the two approved values refuses to start.

`tests/test_replay_metrics.py`

- `signal_frequency` excludes reconstructed/unavailable cutoffs and matches a
  hand-computed value on the fixture.
- `lead_time_vs_trailing_baseline` returns the expected signed delta on a fixture
  where the signal leads the trailing baseline by a known number of days, and
  `unavailable` when the baseline never crosses in range.
- `reproducibility_check` reports zero divergences on two identical runs and
  flags the exact cutoff when one fixture row is perturbed.

## Open Dependencies

- Development Velocity v0 (P1.2) must register a `SignalFn` with a pinned
  `method_version`; until then the reference fixture method exercises the harness.
- P0.8 qualified historical corpus and the `known_then` vs `reconstructed`
  distinction depend on honest `first_observed_at`/`recorded_at`, which the
  temporal layer already enforces and does not backdate.
- P2.2 proper (outcomes, holdouts, hit/false-positive rates, by-geography
  breakdowns) and P2.3 go/no-go build on this scaffold; the thresholds file
  already reserves their fields as predeclared-pending.
