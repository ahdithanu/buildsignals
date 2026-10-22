# Columbus capture and audit — October 22, 2026

## Completed

The local retrospective site-filing archive now covers **January 2023 through
December 2025: 36 months, 2,543 source records, 10,110 temporal observations**.
The October 20 preflight found 2,544 rows. September 2023 changed from 70 to 69
before its October 22 capture; its new provider-before/provider-after/seen/inserted
counts all agree at 69. This is recorded drift, not a silently dropped row.

All 36 completed monthly imports reconciled with no reported failed rows or
remaining checkpoints. Seven months completed October 20; the interrupted August
database was preserved, and August 2023–December 2025 were captured to a new
`resume-20261022` directory. No production database or source enrollment changed.

The offline audit found:

| Measurement | Result |
| --- | ---: |
| Missing planned months | 0 |
| Duplicate stable source IDs across accepted monthly shards | 0 |
| Missing filing dates / filing dates outside pinned month | 0 / 0 |
| Future source-update timestamps versus capture completion | 0 |
| Raw receipt / observation recording outside actual capture interval | 0 |
| Observations recorded before their historical month ended | 0 |
| Ignored interrupted databases | 1 (original August) |

Evidence: [monthly preflight](2026-10-20-columbus-site-monthly-preflight.json),
[offline audit](2026-10-22-columbus-corpus-audit.json). The audit records hashes of
each accepted database/receipt and a combined evidence digest. Raw DBs and full
qualification receipts remain local, Git-ignored, under
`data/qualification/columbus-site-20261020/`; they are not distributed or committed.
Their loss would require recapture with new honest timestamps, not reconstruction
of the original observed vintage. The checked-in aggregates remain durable receipts.

## Scope and rights evidence

One source: `columbus_oh_site_engineering_applications`, event unit **filings**
(`B1_FILE_DD`), existing catalog predicate and approved field allowlist. This
includes the selected site-compliance and commercial lot-split records; no
commercial building issuance rows were pooled. Each month used the existing
local-only historical intake (one page sufficient; counts 43–114). Every database
was a new disposable SQLite file; no application `.env` or production database
was used for intake.

The official Site Engineering application item's public access and CC0
`licenseInfo` were freshly checked October 20 at 22:50 America/Los_Angeles.
Metadata hash and URL are in the preflight receipt. Existing suppression of
personal names/contacts, attachments and geometry remained intact. This is scoped
local research capture under the user's request, not activation or raw-data
redistribution approval. Independent source admission/rights review remains a
separate product gate.

## Acceptance boundary

**Local capture integrity passes; historical completeness is unverified; DV is
HOLD / UNVALIDATED.** A stable source ID identifies a filing, not a unique physical
project. City-default geography is not an independently proven geographic extent.
Populated months are not proof the source includes every eligible filing.
Current status is not status history; do not filter old filings by today's
`approved` interpretation and call that historical approval knowledge.

The archive is 36 separate source/org-isolated local shards, not a silently
merged, accepted replay snapshot. It supports descriptive monthly source counts
and further source-quality investigation. Building a unified admitted snapshot
must preserve provenance, identity and non-backdated capture times and needs its
own verified contract. No coverage attestation was fabricated or supplied.

## Fastest remaining path

1. **Adjudicate the source, using this archive.** Reconcile selected record types
   and monthly counts against City portal/department evidence; establish a
   lifecycle dictionary, missing-record denominator, category changes and
   project-linkage sample. Independent coverage/admission review follows.
2. **Use admitted history as today's baseline.** Historical rows captured now can
   inform future cutoffs. There is no requirement to wait another six months
   merely to accumulate already-available baseline event history.
3. **Freeze prospective predictions and comparator before outcomes.** Existing
   daily Columbus ingestion is a rolling 31-day filing query. Verify successful
   runs and retention of raw versions; separately design bounded reconciliation
   for revisions to older filings. Enabled schedules alone do not prove this.
4. **Finish the evaluation contract before a real result.** The frozen v0 protocol
   describes windows `[T+k*30d,T+(k+1)*30d)` for `k=1..H`, but evaluates at
   `T+H*30d+lag`; the last window is not yet complete at that stated date. Issue
   a reviewed, versioned clarification before looking at outcomes. Do not change
   the old hash-pinned protocol silently. Also implement real outcome extraction,
   holdout enforcement, and the declared lead-time/frequency decision rules.
5. **Bind qualification to actual replay evidence.** Existing coverage attestations
   bind request parameters, not a frozen data snapshot. The evaluator now rejects
   these unbound receipts for protocols declaring P0.8, including a naked `ready`.
   A versioned producer/verifier must bind data/evidence digest, source/method,
   tenant, cutoffs and exact protocol floors to the replay manifest. Generic
   metric protocols remain usable; they do not validate the DV product.
6. Evaluate matured prospective cutoffs against the predeclared comparator and
   holdout; independent P2.3 go/no-go. Twelve evaluable monthly cutoffs and five
   evaluable fires are minimums, not guarantees of statistical adequacy or a pass.

Without authenticated historical availability vintages, the current monthly
sample policy implies roughly **14–16 months** from the first admitted prospective
decision to the minimum matured sample, depending on the clarified window
endpoints/cutoff schedule; sparse firing and coverage failures can extend it.
This is scheduling arithmetic, not a promised validation date. It is not
necessarily 24 additional months: baseline history can already be eligible at a
future cutoff. A publisher-vintage study would require a separately versioned
availability contract and cannot masquerade as BuildSignals-known-then v0.

## Independent City evidence request (prepared specification, not sent)

Use the City's [Records Research route](https://www.columbus.gov/Business-Development/Building-Zoning-Services/Records-Research)
to request existing machine-readable 2023–2025 extracts, category/status dictionary,
related-record IDs, explanation of the 2022–2023 layer discontinuity, and any
retained public extracts/publication or dissemination audit timestamps. Specify
existing records only, the field/privacy scope above, and request a fee estimate
before incurring charges. No outreach or paid request was sent by this task.

The [2023 annual report](https://www.columbus.gov/files/sharedassets/city/v/1/city-council/documents/annual-report/2023-annual-report.pdf)
reports about 580 final site-compliance submittals and a 6% increase over 2022.
That cannot be equated directly with selected ArcGIS rows or reviews/meetings;
it makes pre-2023 comparability a reconciliation question, not a measured economic
surge. No historical public-availability archive has been verified.

## Reproduction

From the repository root, with a project virtualenv and no model key:

```sh
ENVIRONMENT=ci OPENROUTER_API_KEY= .venv/bin/python -m scripts.audit_columbus_corpus \
  --preflight docs/signals/2026-10-20-columbus-site-monthly-preflight.json \
  --directory data/qualification/columbus-site-20261020 \
  --output /private/tmp/columbus-audit-new.json
```

`scripts.columbus_corpus_preflight` defaults to plan-only; `--probe` enables up to
36 logical count queries (zero retries, existing bounded redirects/IP fallback).
`scripts.columbus_corpus_capture` defaults to plan-only; `--capture` opts into
bounded local intake and preserves partial files; `--retry-partial` uses new
attempt directories. Do not rerun capture over the finished archive casually.
The audit reads SQLite in read-only mode and never emits source IDs/addresses.
