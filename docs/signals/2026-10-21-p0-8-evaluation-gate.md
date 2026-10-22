# P0.8 → P2.2 evaluation gate (enforced precondition)

**October 22 correction:** the request-only receipt described below cannot bind
the audited data to an actual replay snapshot. Explicit P0.8 protocols now stay
`corpus_not_qualified` even with `ready` and a matching request fingerprint until
a versioned evidence producer/verifier contract exists. Generic metric protocols
without P0.8 remain available for metric calculation, not DV product validation.
See [the current corpus report](2026-10-22-columbus-corpus-capture.md) for the
required data/method/tenant/cutoff/floor binding and other evaluation blockers.
The older receipt-clears-gate description below is superseded by this correction.

Date: 2026-10-21. Offline, deterministic. This records the enforcement that wires
the P0.8 corpus-qualification gate into the P2.2 Development Velocity evaluation, so
no validation verdict can be produced without a qualified corpus. No source is
accessed or activated.

## Why

`eval/replay/evaluate.py::verdict` decides the P2.2 go/no-go
(`insufficient_sample` | `inconclusive` | `meets_predeclared_threshold`). Until now
the P0.8 precondition ("a qualified historical Columbus corpus is required") lived
only as prose in the predeclared protocol JSON — nothing in code stopped `verdict`
from returning `meets_predeclared_threshold` if a fixture happened to carry enough
fired signals. That is the gap an honest harness must not leave: a validation claim
was reachable without a qualified corpus.

## What changed

`verdict` and `evaluate_outcomes` take a keyword-only `corpus_qualification` (the
dict returned by `qualify_corpus`). A new **first** gate, `_corpus_precondition`,
returns verdict `corpus_not_qualified` unless:

1. a `corpus_qualification` is supplied and is a mapping;
2. its own `verdict == "ready"` (which itself required a verified coverage-audit
   attestation — see the attestation design note); and
3. when the protocol predeclares
   `preconditions.qualified_historical_corpus_P0_8.required_request_fingerprint`, the
   receipt's `request_fingerprint` matches it (constant-time `hmac.compare_digest`).

The gate is evaluated before the sample-size and hit-rate branches, so no other
verdict is reachable without it. It never raises: a missing, non-mapping, or
not-ready receipt, or a malformed `preconditions` block, fails safe to the
`corpus_not_qualified` HOLD. The result echoes the receipt's verdict, fingerprint,
methodology version, and a `fingerprint_bound` flag.

Independent adversarial review: SOUND on the core property — no validation verdict
is reachable without a `ready` corpus, and the gate is correctly ordered first.

## Honest limitation: the binding is not yet pinned

The shipped protocol (`eval/replay/fixtures/dv_v0_evaluation_protocol.json`) does
**not** yet declare `required_request_fingerprint`, because the qualified corpus
does not exist yet — there is no real fingerprint to pin. So today the gate enforces
"a `ready` corpus receipt was supplied" but not "this exact cohort". The result's
`fingerprint_bound: false` makes that visible.

**P2.3 precondition:** before any real validation run, the protocol MUST set
`required_request_fingerprint` to the qualified corpus's `request_fingerprint`, so
the evaluation is bound to the exact cohort that was qualified. Setting it will
change the protocol's content (and any hash over it), which is appropriate at that
point and must be done as a predeclared step, not after seeing a result.

## Effect on the current synthetic-fixture run

The DV v0 backtest over the only committed fixture (synthetic, non-qualified) now
returns **`corpus_not_qualified`** — a stricter, more honest HOLD than the prior
`insufficient_sample` (the fixture is both non-qualified and far too short). The
0–100 score remains UNVALIDATED; DV stays HOLD.

## Verification

`OPENROUTER_API_KEY= python -m pytest tests/test_replay_evaluate.py tests/test_replay_development_velocity.py -q`
(new cases: HOLD without a receipt, with a not-ready receipt, with a non-mapping
receipt, with a fingerprint mismatch; clears with a matching receipt; tolerates
malformed preconditions; determinism preserved). `ready` remains a measurement
gate, never source activation, commercial-reuse clearance, or score validation.
