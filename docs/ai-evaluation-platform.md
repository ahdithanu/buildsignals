# AI Evaluation Platform

## What Is Implemented

This is a tenant-scoped, bounded regression runner with deterministic evidence
rubrics. It is not an LLM judge, a semantic verification system, or a production
quality certification. A passing synthetic example only demonstrates the runner
and its configured checks; it does not certify a model or a customer workflow.

| Workflow | Live execution | Replay |
| --- | --- | --- |
| `opportunity_memo` | Existing deterministic memo generator; `rules/memo-v1`, `memo-template-v1` | Captured output |
| `score_explanation` | Existing deterministic deal scoring; `rules/scoring-v1`, `score-explanation-v1` | Captured output |
| `copilot_answer` | Not installed; `workflow_not_available` | Captured output |
| `multi_agent_research` | Not installed; `workflow_not_available` | Captured output |

Live memo/score inputs require `input_json.deal_id` for an accessible deal in the
active organization. Adapters read the deal and independently tenant-scope its
related rows; they do not update the deal or call a model provider. The adapter
constructs the evidence snapshot and a `deal:<deal_id>` citation. Dataset-supplied
context is not substituted for this live evidence. Live requests use `mode: live`
and the default `model: current`, `prompt_version: current`; supplied outputs or
version overrides are rejected.

Replay accepts captured `EvalOutput` values keyed by the persisted case IDs, with
exactly one output per case and no extras. Both `model` and `prompt_version` must
explicitly identify the capture and must not be `current`. These labels describe
the submitted capture; the runner does not independently verify its provenance.
Replay uses the case's stored `retrieved_context` and makes no generation calls.
Seeded examples are synthetic, including those for workflows with live adapters.

## Rubric And Limits

The scorer version is `evidence-rubric-v1`. All five metrics lie in `[0, 1]`:

| Metric | Meaning |
| --- | --- |
| `citation_accuracy` | Fraction of distinct cited source IDs that exist in context and have only valid supplied quotes. |
| `factual_coverage` | Mean of required-phrase matches, valid required-citation checks, and numeric agreement when configured. |
| `rule_compliance` | Mean of forbidden-phrase absence checks and numeric agreement when configured; 1 if no rule checks. |
| `quality` | Minimum of citation accuracy, factual coverage, and rule compliance. |
| `hallucination_risk` | Maximum of invalid/missing citation risk, forbidden-phrase match ratio, and numeric mismatch. |

Phrase/quote matching case-folds and collapses whitespace, then requires a literal
contiguous substring. Source IDs remain case-sensitive. Quotes are optional; if
supplied they must match the referenced evidence text. Repeating a good reference
cannot dilute a bad one. Any invalid quote for a source makes that source's group
invalid. Required IDs must actually be cited validly, not merely present in the
context. No citations or no evidence gives citation accuracy 0 for an answer.
Missing required IDs also contribute their missing fraction to citation risk.
An `expected_score` requires exact numerical equality, including zero; a missing
score is a mismatch. No rounding tolerance is applied.

These are lexical rubric proxies, **not semantic proof**. A valid citation can
still accompany an unsupported assertion, and a phrase can appear in a negated or
misleading statement. The risk metric cannot detect all hallucinations. Use human
review and separately validated task-specific checks for claims these rules do
not establish.

Each dataset/run contains **1 to 25 cases**, executed synchronously. Each case is
limited to 100,000 characters of its schema-normalized JSON serialization (the
schema's 100 KB budget), at most 100 evidence items, and 10,000 characters per
evidence text. Output text is limited to 50,000 characters, citations to 100, and
each quote to 2,000 characters. Rubric lists have at most 50 entries each; at least
one required phrase, required citation ID, or expected score is mandatory.

Default thresholds are quality >= 0.8, citation accuracy >= 1.0, factual coverage
>= 0.8, and hallucination risk <= 0.0. Boundaries are inclusive. Rule compliance
is included through quality, not a separate threshold. Thresholds are persisted
with the run. The run gate requires passing aggregate metrics, no execution
errors, and no failed critical case; cases default to `critical: true`. A failed
critical case cannot be hidden by averages. A completed run can still fail its
gate. Running, interrupted, unsupported, or errored runs must not approve a
release. Failures are retained with bounded error codes and fail-closed metrics.

## Storage, Access, And Operations

Apply `alembic upgrade head` before using the evaluation API. Migration
`20260920_0001` follows `20260915_0001` and creates `eval_dataset`, `eval_case`,
`eval_run`, `eval_result`, and `eval_metric`, with tenant indexes and composite
organization/parent foreign keys. Downgrading this migration drops evaluation
history; back it up before any rollback.

PostgreSQL enables and forces RLS on all five tables. The `tenant_isolation`
policy uses `app.current_org` for both reads and writes. Use the application's
tenant-scoped connection lifecycle and a runtime role without superuser/BYPASSRLS
privileges. SQLite tests enforce relational constraints but do not establish
PostgreSQL RLS behavior. Keep application organization filters as well as RLS;
neither an arbitrary case ID nor a deal ID grants cross-tenant access.

All evaluation endpoints require authenticated organization-admin access,
including reads, comparisons, capabilities, and gate checks as well as creating
datasets, seeding examples, and starting runs. CI must use an authorized token
scoped to the organization that owns the run, never a database-owner credential or an
anonymous development bypass. Creation and run lifecycle events are audited.
Stored case, output, and evidence snapshots can contain sensitive customer data;
snapshot access is admin-only. Do not place credentials in case inputs or
captured output.

Dataset and run list endpoints each return at most 100 records, newest first.
There is currently no cursor/offset pagination, so older history is not fully
browsable through these lists. Persist IDs when creating datasets/runs; their
detail endpoints can retrieve known IDs within the authorized organization.

Run history stores case/output/context snapshots, dataset and context
fingerprints, model/prompt labels, scorer version, thresholds, metrics, latency,
and optional usage. Comparisons require matching dataset snapshots, execution
mode, thresholds, scorer version, and context fingerprint. Incomparable runs
return reasons rather than misleading metric deltas. Metric deltas are candidate
minus baseline; positive hallucination-risk deltas are worse, not better.

**Unknown cost is `null`, not zero.** Unknown token counts and latency are likewise
`null`. Each summary total remains `null` if any result's corresponding value is
unknown; this policy applies independently to latency, input/output tokens, and
cost.
The deterministic live adapters explicitly report zero provider tokens and zero
provider cost because they call no model; this is not a claim of zero compute or
operational cost. Live latency is measured. Replay retains supplied usage and
uses supplied captured latency when present; otherwise replay latency is `null`,
never substituted with local evaluation overhead or zero.

## Add A Case

Create a dataset with `POST /v1/evals/datasets`. This deliberately synthetic case
tests a warning against treating a permit application as an approval:

```json
{
  "name": "Permit uncertainty regression v1",
  "description": "Synthetic replay checks; not production certification",
  "workflow": "copilot_answer",
  "cases": [{
    "name": "Application is not approval",
    "input_json": {"question": "Can construction begin?"},
    "expected_output": {
      "required_phrases": ["application received", "approval is unconfirmed"],
      "forbidden_phrases": ["construction is authorized"],
      "required_citation_ids": ["permit:example-17"]
    },
    "retrieved_context": [{
      "id": "permit:example-17",
      "text": "Permit application received. No approval decision is recorded."
    }],
    "critical": true
  }]
}
```

Take the returned `cases[0].id` and replace `CASE_ID_FROM_RESPONSE` below. Submit
to `POST /v1/evals/datasets/{dataset_id}/runs`:

```json
{
  "mode": "replay",
  "model": "synthetic-fixture-v1",
  "prompt_version": "permit-warning-v1",
  "outputs": {
    "CASE_ID_FROM_RESPONSE": {
      "text": "Application received; approval is unconfirmed. Verify before building.",
      "citations": [{"source_id": "permit:example-17", "quote": "application received"}],
      "tokens_input": null,
      "tokens_output": null,
      "cost_usd": null,
      "latency_ms": null
    }
  }
}
```

To test a live adapter instead, create a memo/score dataset with a real accessible
`deal_id`, a rubric appropriate to its actual deterministic output, and any
required citation set to `deal:<deal_id>`. Submit `{"mode":"live"}`. Do not relabel
synthetic fixture captures as live results.

## CI Gate Client

Inject `EVAL_ACCESS_TOKEN` through your CI secret store. Set `EVAL_BASE_URL` to the
API origin (optionally with a deployment path prefix), **without `/v1`**. Then:

```bash
export EVAL_BASE_URL="https://your-api.example"
python scripts/check_eval_gate.py "$EVAL_RUN_ID"
```

The client sends `GET /v1/evals/runs/{id}/gate` with a bearer token. The gate route
returns the completed `RunRead` only on success; a failed/incomplete gate returns
409. The CLI requires HTTP 200, the requested `id`, `status: completed`, and the
literal JSON boolean `gate_passed: true`. It exits 0 only on success, 1 on gate,
transport, or response failure, and 2 on invalid configuration/usage. Missing
credentials, authentication failures, missing runs, timeouts, bad TLS, invalid
JSON, and incomplete responses cannot produce a passing exit code. Do not mask
the exit status with `|| true` in a release pipeline.

Remote endpoints require HTTPS with normal certificate verification. Plain HTTP
is allowed only for `localhost` and literal loopback IP addresses; private-network
addresses and lookalike hostnames are not exceptions. The client rejects URL
credentials, queries, fragments, and unsafe run IDs. It follows **no redirects**,
including same-origin redirects, and disables environment proxy discovery to
avoid forwarding a local HTTP token through a remote proxy. Configure the final
direct API URL. Requests use a 30-second socket timeout and a 64 KiB response
limit. Output contains only fixed status messages, never tokens, response bodies,
request URLs, or exception details. Do not enable shell tracing around secrets.

Run the network-free CLI tests with:

```bash
python -m pytest tests/test_eval_gate_cli.py -q
```

## Scaling Toward One Million Opportunities

The current synchronous 25-case runner has not established evaluation capacity
for a one-million-opportunity corpus. Do not synchronously evaluate every
opportunity or bypass case limits to emulate that capacity. A next-stage design
should select privacy-reviewed, stratified samples from the opportunity corpus
by workflow, tenant cohort, geography, opportunity type/stage, evidence
availability, and observed failure patterns, plus a fixed critical regression
suite. Track corpus and stratum coverage and report sampling uncertainty instead
of inferring correctness across one million opportunities from a small passing
fixture set.

Move larger evaluations to tenant-isolated queues with bounded workers,
idempotent jobs, explicit retries/timeouts, provider budgets, concurrency limits,
and durable completion accounting. Keep snapshots and scorer versions stable,
reject partial or stale runs at release gates, and evaluate canary changes before
broad rollout. Add retention controls, redaction, queue/latency/error monitoring,
and dedicated PostgreSQL RLS and load tests. Add pagination before relying on
complete dataset/run inventory at scale. Queues, distributed workers, and
million-opportunity evaluation capacity are future work, not guarantees of this
implementation.
