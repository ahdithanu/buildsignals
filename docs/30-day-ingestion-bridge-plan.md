# 30-Day Plan: Ingest More + Bridge to the First Validated Signal

Window: 2026-10-17 → 2026-11-16. Author: engineering. This is a plan, not an
authorization to bypass any source's terms. Legal_hold sources stay inactive
until a documented reuse basis exists; measured counts are never presented as
market coverage or for-sale inventory; signals are research outputs until
evaluated under a cutoff-safe harness.

## Progress and remaining limits (2026-10-18)

PR #252, stacked on open PR #251, implements `ercot_mis_xlsx`; no further new
ERCOT adapter is needed to begin offline qualification. Review corrections and
fixture-based normalization/persistence regression checks are implemented and
verified on that existing branch. Current verification receipts belong in
`docs/agent-handoff.md`, not in the original 1,783-test claim.

ERCOT remains `technical_hold`, with ingestion and canaries disabled. Earlier
manual public-index/workbook observations do not verify the current connector
through its supported ingestion path. Written commercial-reuse confirmation,
authorized live host/TLS/contract verification, and a bounded canary receipt
remain promotion gates. No activation, merge or deployment is authorized by
this plan or the review-correction task. An interconnection queue snapshot is
power-infrastructure evidence, not an ordinary building-permit application.

PR #251's remaining methodology findings are still outstanding. P0.8 corpus
qualification is partial, and reconstructed historical observations must remain
labeled retrospective; offline ERCOT tests do not establish cutoff-safe replay,
Development Velocity validity, or first-seen availability of historical events.
P0.8 also requires rights-cleared historical permit/planning, land,
construction and infrastructure evidence with an accepted minimum usable
history; the current Columbus corpus does not unlock scoring. Before tuning,
predeclare outcomes, horizons, cohorts, minimum samples, holdouts and false
positive tolerance. Without contemporaneous snapshots or prospective history,
new captures support retrospective non-validating analysis only.
The milestones below are targets, not completed work or standing permissions.

## Objective

Close the two gaps that matter most from the institutional roadmap:
1. **Ingest more, deeper, rights-clean** — breadth (more reviewed public sources),
   depth (historical corpus for one wedge market), and a new input class the
   vision needs (utility/power) — all using the existing adapter set.
2. **Bridge to intelligence** — stand up the temporal baseline + the first
   proprietary signal (**Development Velocity v0**) in one qualified market, with
   a replay/backtest scaffold built alongside, not after.

Success by day 30:
- A dated **measured-coverage attestation** for one wedge market (depth, stages,
  freshness, gaps) — not configured counts.
- **+N reviewed public sources** live on the robust worker, with runtime-failure
  monitoring on.
- **Development Velocity v0** producing versioned, cited, cutoff-safe output in
  that market, with a first honest evaluation (precision / lead-time vs a simple
  baseline) and a go/revise/kill note.

## Wedge-market choice

Validate **Development Velocity in Columbus** — it has the most existing depth
(historical intake, live prod+demo schedules) and is a genuine data-center market
(Intel/Google/AWS). In parallel, qualify **power inputs in Northern Virginia
(Loudoun) and DFW** — the interconnection-constrained markets where Power
Constraint will later live. Phoenix/Atlanta stay on their existing holds until
rights are resolved; no promotion by roadmap priority alone.

## Workstreams

### A. Deepen + harden what we already ingest (week 1)
- Deploy the merged reliability fixes (#249) to the regional/worker image so the
  quarantine guard and IAM-policy accumulation protect daily runs.
- Turn on **runtime-failure monitoring/paging** (the one reliability gap still
  open in the handoff) so a silently failing feed is visible same-day.
- Produce the **measured-coverage attestation** for Columbus: time depth, stages
  (filed/pending/approved/issued/withdrawn where supported), duplicates, freshness
  (collection vs source-update completeness — now measured), and gaps.

### B. Breadth: more reviewed public sources, existing adapters (weeks 1–2)
Qualify → canary → activate only rights-clean public feeds, reusing arcgis /
socrata / legistar / ckan / opendatasoft / rss / planning_documents:
- Columbus/Central OH: Franklin County + adjacent jurisdiction permits & planning
  agendas (deepen the validation market).
- NoVA data-center alley: Loudoun & Prince William County permits/planning
  (public open-data / Legistar) — the power-market wedge.
- DFW: add neighboring jurisdictions to the live Fort Worth/Arlington feeds.
- Baselines input: **Census Building Permits Survey (BPS)** — free/public — for
  historical permit baselines the signal needs.
Each source ships with a catalog entry, field mapping, canary receipt, and a
one-line rights basis. No legal_hold bypass.

### C. New input class — utility/power (weeks 2–3, qualify first)
Power Constraint (the roadmap's #2 signal) needs supply/demand evidence we do
not ingest today. Qualify (do not assume rights):
- **ISO/RTO interconnection queues** — PJM (NoVA), ERCOT (DFW): public queue data.
- State utility-commission filings — VA SCC, PUCT (TX).
Deliverable this month is a **qualified contract + bounded probe** for one of
these (ERCOT's connector is implemented in PR #252 but remains held), plus a concrete blocker
if a reliable recurring interface can't be established — mirroring the MDEQ
qualification pattern. Full utility adapters are P1, not this window.

### D. Temporal depth + corpus qualification (weeks 2–3)
- Run the temporal P0 projection over the Columbus corpus (append-only
  observations/events, as-of reads already exist) and **qualify the historical
  corpus** (P0.8): inventory dates, stages, duplicates, gaps, method versions —
  reproducible and labeled as retrospective where applicable.

### E. The bridge — Development Velocity v0 (weeks 3–4)
- Build **historical/seasonal/peer baselines** and change detection over the
  qualified Columbus series (abstain below minimum sample size).
- Emit a **versioned Development Velocity signal object**: what changed, cited
  drivers, historical comparison, confidence separate from score, invalidation
  conditions. Unavailable fields marked unknown. 0–100 score is an unvalidated
  research output this month.

### F. Validation scaffold, in parallel (weeks 3–4)
- Stand up the **cutoff-safe replay** (freeze snapshots/mappings/method versions;
  reuse the as-of eligibility contract) and run a **first evaluation** of
  Development Velocity: frequency, lead time vs a naive trailing-average baseline,
  false-positive spot-check — with sample sizes and uncertainty. Produce a minimal
  internal QA view, not a terminal. End with a written go/revise/kill.

## Week-by-week

| Week | Dates | Primary milestones |
| --- | --- | --- |
| 1 | 10/17–10/23 | Deploy #249; runtime-failure monitoring on; Columbus measured-coverage attestation; first 2–3 new rights-clean sources qualified+canaried. |
| 2 | 10/24–10/30 | Activate week-1 sources; add NoVA(Loudoun)+DFW jurisdictions + Census BPS; begin ISO/RTO (PJM/ERCOT) contract qualification; start temporal projection over Columbus. |
| 3 | 10/31–11/06 | Finish corpus qualification (P0.8) for Columbus; land one utility/power bounded probe or a documented blocker; build baselines + Development Velocity v0 (offline). |
| 4 | 11/07–11/16 | Replay scaffold + first Development Velocity evaluation; internal QA view; go/revise/kill note; refreshed measured-coverage + source inventory. |

## Guardrails (non-negotiable)
- No source is activated without a documented rights basis; legal_hold
  (Atlanta, Phoenix, Mississippi, D'Iberville, Bozeman, etc.) stays inactive.
- Collection recency ≠ filing recency; parcels remain investigation leads.
- Development Velocity is labeled an unvalidated research output until the week-4
  evaluation; thresholds are set before seeing results.
- Each activation ships bounded caps, canary, tenant isolation, and a receipt.

## What this does and does not buy
- Buys: materially more real, rights-clean data; a qualified validation market;
  the first real signal + an honest evaluation — i.e., the start of the moat.
- Does not buy: the full 3-signal validated product, the institutional terminal,
  the financial layer, or the PRD §21 expansion gate (≥3 validated signals, ≥5
  institutional users, ≥1 paying customer). Those remain beyond 30 days.
