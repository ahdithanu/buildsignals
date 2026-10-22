# Corpus coverage-audit attestation (P0.8 condition 9)

Date: 2026-10-21. This records the mechanism that lets `qualify_corpus` reach the
`ready` verdict — and only reach it — through an explicit, verified, independent
coverage-audit attestation. It is the implementation of condition 9 in
`docs/signals/2026-10-20-columbus-historical-intake-scoping.md`. No source is
accessed or activated; `ready` is a measurement gate, never source activation,
commercial-reuse clearance, or score validation.

## Why

Before this change, `qualify_corpus` could never return `ready`: the verdict fell
through to `insufficient_coverage` because a corpus cannot self-certify per-window
source coverage from timestamp arithmetic alone. That is honest, but it left P0.8
with no completable path. The attestation closes that gap without weakening the
honesty posture: `ready` now requires a human/operator to have performed an
independent coverage audit and to certify it explicitly against the exact measured
cohort.

## The contract

`CoverageAuditAttestation` (in `app/services/corpus_qualification.py`), an optional
`coverage_audit` field on `CorpusQualificationRequest` defaulting to `None`:

| Field | Rule |
| --- | --- |
| `auditor` | who performed the audit (`NonblankKey`). |
| `attested_at` | when (`UtcCutoff`); must be `<= as_of`. |
| `audit_methodology_version` | the audit method id (`NonblankKey`). |
| `attested_request_fingerprint` | 64-hex; the measured-inputs `request_fingerprint` the audit certifies. |
| `covered_window_indices` | explicit list (≥1, non-negative) of the complete-window indices certified. |
| `known_then_availability_confirmed` | must be `True`. |
| `decision` | `Literal["coverage_audited"]` — no default, must be stated. |
| `rationale` | bounded free text (1–5000). |

`qualify_corpus` sets `coverage_audited = True`, and the verdict becomes `ready`,
**only** when all hold (`_evaluate_coverage_audit`):

1. an attestation is present;
2. `hmac.compare_digest(attested_request_fingerprint, request_fingerprint)` matches
   — binding the audit to this exact cohort + floors;
3. `attested_at <= as_of`;
4. `known_then_availability_confirmed is True`;
5. `set(covered_window_indices) == set(range(complete_windows))` — every complete
   window is explicitly certified (no blanket, partial, or over-certification).

Otherwise the verdict stays `insufficient_coverage` with a specific shortfall. The
function never raises on a semantically-bad attestation — it fails safe to HOLD.
(Structurally malformed attestations — bad hex, wrong `decision`, empty list — are
rejected by Pydantic at request construction, which also never yields `ready`.)

## Honesty guarantees (verified adversarially)

- **Default off.** No attestation → unchanged `insufficient_coverage`.
- **Ordering preserved.** Depth and completeness are gated *before* coverage, so a
  valid attestation cannot rescue a shallow, gappy, duplicated, or
  non-known-then corpus (depth still folds in the `known_then_upper_bound`).
- **Fingerprint excluded from itself.** `coverage_audit` is excluded from the
  `request_fingerprint` input, so the auditor signs the measured inputs (not the
  signature), and pre-existing no-audit requests keep an identical fingerprint
  (determinism intact).
- **No activation claim.** `WARNINGS` and the module docstring state `ready` records
  an independent audit, not an automatic pass, and authorizes no activation or reuse.

## Known limits (by design, not defects)

- The fingerprint is **integrity, not authentication**: `fingerprint` is an unkeyed
  SHA-256, so it binds the attestation to a specific measured request but does not
  cryptographically stop a requester from self-signing. The honesty guarantee rests
  on the attestation being a genuine operator certification (the house trust model),
  not on a key. An auditor-held HMAC key would be the hardening step if forgery
  resistance is later required.
- **Floors are caller-supplied** (with the predeclared protocol defaults) and are
  baked into the signed fingerprint, so they are visible in `predeclared_minimums`.
  A `ready` verdict therefore does not by itself prove the *predeclared* P2.2 floors
  were used — a reviewer must check `predeclared_minimums` against the hash-pinned
  protocol before relying on it for P2.3.

## Verification

`OPENROUTER_API_KEY= python -m pytest tests/test_corpus_qualification.py -q`
(23 cases; 7 new `test_coverage_audit_*` cover ready-promotion, fingerprint
exclusion, wrong-fingerprint / partial-window / unconfirmed-known-then /
future-attested HOLDs, and that a valid audit cannot bypass `insufficient_depth`).
Independent adversarial review found no dishonest path to `ready`.
