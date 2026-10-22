# Unified Columbus evidence snapshot and replay binding

Date: October 22, 2026. Local/offline implementation; no collection, production
deployment, source activation, paid calls or external certification in this step.

## Unified research corpus

`scripts.unify_columbus_corpus.build_snapshot(preflight, directory, database)`
consumes the verified monthly archive, reruns its audit and exclusively creates a
new local SQLite snapshot plus `.snapshot.json` lineage sidecar. The real archive
has 36 original ingestion runs, 2,543 raw records/permits, 10,110 observations and
5,086 temporal events. One inactive local source and one dedicated local tenant
replace the isolated shard namespaces. Original raw/observation/event IDs,
payloads, content hashes, dates and capture/recording times are preserved;
source-dependent series keys are recomputed and namespace remapping is explicit.

Input files are read-only. Input DB and receipt hashes are checked before and
after copying. Missing/failed/duplicate/mixed-source or cross-tenant evidence
cannot produce a complete snapshot. Existing destinations are never overwritten;
the original interrupted August file remains excluded. Source admission remains
false and no independent coverage attestation is generated.

The builder copies the evidence/canonical tables required for this research path,
not an entire application tenant or a reconstructed physical-project graph.
Entity IDs retain their original interpretation; they are not newly verified
unique physical projects. This is not a deployable production database.

Two independent builds from the real inputs have the same **logical content
digest**. SQLite file bytes can differ and have separate artifact hashes; those
file hashes are not presented as a cross-build reproducibility guarantee.

Local primary artifacts:

- `data/qualification/columbus-site-unified-20261022.db`
- `data/qualification/columbus-site-unified-20261022.snapshot.json`
- `data/qualification/columbus-site-replay-verified-20261022/`

The qualification artifact directory is Git-ignored. Sanitized receipts are
checked into `docs/signals/`; no raw payloads or DBs are published.
See [the sanitized snapshot/binding receipt](2026-10-22-unified-columbus-receipt.json)
for counts, lineage hashes, protocol/code identities and both-build comparison.

## Snapshot-bound receipt contract

`eval.replay.corpus_binding` adds:

```python
produce_corpus_binding(db, *, manifest, request, protocol) -> dict
verify_corpus_binding(db, *, manifest, protocol, receipt) -> dict
```

The producer measures qualification internally. The verifier re-reads the actual
database, rechecks the manifest and relevant implementation bytes, reconstructs
the request and recomputes the entire receipt. A caller-supplied `ready` or
`verified` flag is insufficient. `verified` means evidence identity/integrity
matched; `qualified` separately means the measured corpus passed its gates.
For a positive audited binding, the operator's audit must explicitly attest the
same `attested_snapshot_id`; an old request-only audit cannot be reused to certify
a newly changed/refrozen dataset. Legacy standalone qualification receipts remain
separate from this stronger replay-admission contract.

The contract binds:

- actual observation/raw/event content, including reader-affecting geography,
  source/type, entity, confidence, timestamps and raw payloads;
- organization, source, observation method, geography and attribute;
- exact manifest identity, cutoffs, full matching source/method reader universe,
  baseline windows and lag, protocol content and P0.8 quality/sample floors;
- relevant replay, signal, temporal, baseline and qualification implementation
  bytes. Edits require refreezing; commit ID alone is not code-integrity proof.

DV reads a source-wide cohort, so the binder rejects a manifest that omits
matching series which could influence that read. The driver also refuses series
or cutoff arguments differing from the frozen manifest. Once a qualified binding
is supplied, the evaluator reruns the actual frozen DV implementation and checks
the replay's signals, evidence, modes and fingerprints; self-consistent hashes of
fabricated signals do not clear it.

Independent audit attestations retain the existing **trusted operator** model.
Hashes provide integrity, not auditor authentication or proof of historical
publication. A reviewer assertion is never synthesized for the real archive.

## End-to-end acceptance and remaining boundary

The real diagnostic follows intake receipts → audited shards → unified snapshot →
frozen cohort → producer/verifier → repeated actual DV replay → evaluation HOLD.
`eval.replay.columbus_snapshot` opens the SQLite artifact read-only, validates its
file hash against the sidecar, and writes results only to a new output directory.

Real-data result: **37 cutoffs, all `insufficient_history`, zero eligible signal
cutoffs, reproducible replay, binding integrity verified, corpus not qualified**.
Historical event depth is 36 complete 30-day windows, but known-then evaluable
periods remain zero. Qualification is `insufficient_depth`; evaluation is
`corpus_not_qualified`. The 0–100 DV score remains UNVALIDATED.

Synthetic operator-audited fixtures separately prove the binding can clear and
reach sample evaluation. Negative tests reject changed data, code, protocol,
tenant, source/method, floors, cutoffs, omitted series and fabricated signals.
These are software-contract tests, not evidence that real Columbus is qualified.

Final verification: **165 targeted tests passed**, including real local intake →
unification → snapshot-bound replay integration, plus adversarial binding and
existing qualification/baseline/DV/replay regressions. Relevant Ruff and whitespace
checks passed. Two independently built real snapshots have identical snapshot IDs
and replay fingerprints; each diagnostic also replays twice internally. Original
signal status/value assertions are unchanged; the golden replay fingerprint was
updated only because the evidence hash now covers additional provenance fields.
Full backend/PostgreSQL and frontend/browser suites were not rerun: this increment
changes offline snapshot/evaluation tooling, not a frontend or production release.

**Closed here:** unified research snapshot, timestamp/lineage-preserving import,
snapshot-bound receipt producer/verifier, strict replay scope/argument checks,
actual replay-output verification, and executable offline end-to-end diagnostic.

**Still separate:** independent source completeness/admission; genuine matured
known-then observations; method-specific outcome extraction, clarified outcome
window endpoints, temporal holdout and a manifest-bound comparator. Until that
method-specific contract exists, adequate-sample P0.8 evaluations remain
`inconclusive`; generic metric helpers cannot substitute for DV validation.
No frozen protocol, firing threshold, golden outcome label or source gate changed.

## Commands

```sh
ENVIRONMENT=ci OPENROUTER_API_KEY= .venv/bin/python -m scripts.unify_columbus_corpus \
  --preflight docs/signals/2026-10-20-columbus-site-monthly-preflight.json \
  --directory data/qualification/columbus-site-20261020 \
  --database /private/tmp/columbus-unified-new.db

ENVIRONMENT=ci OPENROUTER_API_KEY= .venv/bin/python -m eval.replay.columbus_snapshot \
  --database /private/tmp/columbus-unified-new.db \
  --output /private/tmp/columbus-bound-replay-new
```

Choose new paths for each invocation. The diagnostic deliberately supplies no
outcomes and cannot claim validation; it exercises the complete evidence-binding
path without waiting on external data or making unsupported historical claims.
