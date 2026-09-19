# Institutional Intelligence Roadmap

## Scope and Evidence

Audit date: September 14, 2026. Tracked baseline: `ca95615` in
`/private/tmp/buildsignals-temporal-foundation`. The full user-supplied BuildSignals
PRD was read from
`/Users/ahdithebomb/.codex/attachments/eba9d98c-6476-46f6-ba1b-00ef8b781eb5/pasted-text.txt`.
PRD section numbers below provide traceability without reproducing the PRD.

This is a local audit, not a claim of production or predictive readiness. Tests
were inspected, not executed. Concurrent uncommitted temporal models, schemas,
services, routes, migration and ingestion projection appeared during the audit;
they are in-flight P0 work, not accepted capabilities or a completed code review.
The mapping describes the baseline commit. New implementation remains local:
this roadmap authorizes no deployment, worker creation, source activation or
production migration.

Implementation follow-through: the first P0 increment is now present locally,
with permit/planning projection, authenticated temporal reads, immutability and
regression tests. See `temporal-foundation.md` for the actual contract, validation
results and release limitations. Historical corpus qualification, the broader
graph expansion and all proprietary signal/validation gates remain open.

September 19 follow-through: the missing temporary worktree was recovered into
`.worktrees/temporal-foundation` on `codex/temporal-foundation-recovery` and retested.
`activity-baseline.md` documents the new descriptive source-cohort endpoint;
`columbus-historical-intake.md` records official-source aggregate measurements
and historical qualification gaps. Neither constitutes an accepted historical
corpus or validated Development Velocity signal. Local PostgreSQL migration and
isolation verification is now available; production verification remains open.

## PRD Adoption

- **Product/customer (sections 1-3, 20, 23):** Observe -> Connect -> Measure ->
  Detect -> Test -> Explain. Answer what changed, why it matters, who/what is
  exposed, and what to investigate. Start with analysts/associates at real estate
  private equity, infrastructure/data-center investors, land funds and institutional
  CRE acquisition teams. Broader financial customers follow validation.
- **Wedge (section 3):** data center and power infrastructure in five US markets:
  Northern Virginia, Dallas-Fort Worth, Phoenix, Atlanta, and Columbus. Validate
  Development Velocity in one market selected on measured data quality; qualify
  the others individually. These are targets, not coverage claims. Land,
  development, infrastructure and company activity supply the wedge;
  manufacturing and further domains remain future scope.
- **Foundation (sections 4-7, 18-19, 22):** adopt temporal observations, normalized
  events, raw provenance, entity resolution, and the physical-economy graph.
  Reuse relational models and connector/service boundaries. First P0 is a subset
  of the PRD's foundation, not its completion.
- **Intelligence and validation (sections 8-10, 19-21):** pursue Development
  Velocity, then Power Constraint, then Physical Expansion. A multi-observation
  signal is not an event or deal score. Define replay/evaluation alongside early
  experiments; evaluate all three before major institutional UI. Scores and
  confidence need versioned methods and empirical evaluation.
- **Product and financial layers (sections 9, 11-16, 18):** adopt evidence-linked
  signal objects and post-validation terminal, market/company views, Copilot,
  watchlists and material alerts. Separate facts, calculations, model conclusions
  and speculation. Securities, debt, portfolios, Physical Activity Divergence
  and Capital Stress remain later financial-layer work.
- **Preservation and exclusions (section 17):** keep permit/planning discovery,
  retail/builder evidence and review, nearby-parcel investigation, saved work,
  and authorized exports working. Do not invest in generic parcel search, GIS,
  CRM/broker/contact databases,
  deal-pipeline expansion, property underwriting, transaction execution, generic
  chat, standalone summarization, or construction lead generation as the new
  product. Maintain existing workflows without expanding these categories.
- **Distribution (section 18):** P0 needs an internal authenticated temporal
  API; institutional feeds/integrations and portfolio monitoring remain P5.

## Capability Map

**Existing** means code and relevant tests are present, not operationally verified.
**Partial** means reusable pieces exist but do not meet the PRD capability.
**Missing** means no implementation of the target capability was found in the
tracked baseline. Paths are repository-relative.

| PRD capability | State | Audited evidence and adoption gap |
| --- | --- | --- |
| Raw provenance/source registry (4, 18) | Existing | `app/models/ingestion.py`: source/mapping/run records and content-addressed `RawSourceRecord` with payload, source-update and receipt times. Migration `20260809_0002` adds DB mutation guards with organization-erasure exceptions. Reuse this store. |
| Temporal observations and historical availability (4, 18) | Partial | Raw versions exist, but `RawSourceRecordObservation` is a mutable last-seen sidecar. Canonical permit/planning rows are overwritten in `app/services/ingestion/service.py`. No generic entity/attribute/value history with separate recorded-time cutoff in the baseline. |
| Normalized event engine (6) | Partial | `PermitEvent` records ingestion lifecycle activity; `PlanningRecord` stores planning types/stages; `ParcelLineageEvent` models splits/merges. No cross-domain append-only economic event engine. Database creation/disappearance does not prove filing/withdrawal. |
| Resolution and physical graph (5) | Partial | `app/models/graph.py`, `app/services/graph_service.py`: source identities, aliases, matching, reviewed merges, evidence, validity fields, verification queue. Company/parcel/property/permit/city/lender types exist. Project/facility/utility/infrastructure/market types, explicit parent/subsidiary and exposure semantics, and point-in-time resolution history remain gaps. |
| Permit/planning/retail research inputs (3, 7) | Existing | Ingestion service, `planning_intelligence.py`, `brand_intelligence.py`, exact references, and corresponding tests support evidence-linked planning/permit/company workflows. Data-center tags and keyword matches are useful inputs, not power supply/demand ingestion or a Physical Expansion Signal. |
| Scheduling/admission/measured inventory | Existing | `app/services/ingestion/`: dispatcher, scheduling, host-policy and measured-coverage services, with tests. Configuration does not establish running workers, complete history or live coverage. |
| Baselines, change detection, proprietary signals (7-8) | Missing | `planning_intelligence.py` has keyword priority; `brand_intelligence.py` aggregates matches; `scoring_service.py` scores deals. None implements historical/seasonal/peer baselines or the three proposed signals. `enrichment_service.py` explicitly generates mock data; exclude it from evidence and evaluation. |
| Standard signal object (9) | Partial | `app/schemas/buildsignal.py`: change, thesis, confidence rationales, cited support/counterevidence, implications and questions. Historical statistics, versioned drivers/scores, explicit invalidation and related signals remain gaps; `app/models/signal.py` is a small record. |
| Human review/publication | Existing | `app/models/buildsignal.py`, assessment services/tests: snapshots, independent review, audit and version-checked publish/withdraw. Application-append-only with deletion cascades, not tamper-proof. Publication is tenant-internal, not deployment/distribution. |
| Historical replay/backtesting (10, 18) | Missing | No cutoff-safe feature/outcome evaluation harness or performance reports found. Scheduler `as_of`, saved parcel-search timestamps, brand backfill, and assessment revisions do not provide historical signal replay or signal-method versioning. |
| Copilot/multi-agent research (14) | Missing | PRD current-state claims are not substantiated by this checkout. Ingestion orchestration is different; `memo_service.py` produces templated deal memos. Audit separately before assuming an agent stack exists. |
| Institutional views/watchlists/alerts (11-16) | Partial | `src/App.tsx` wires Signals, Planning, Brand Expansion, graph, inbox and acquisition views. Watchlist navigation/catalog cohorts are not user subscriptions or material alerts. Terminal and performance pages remain gaps. |
| Financial layer (18) | Missing | A lender graph type and deal loan assumptions are not security/debt-instrument mapping, portfolio exposure, second-order inference, Divergence, or Capital Stress. Required graph types/relationships, licensed inputs, and financial outcome evaluation remain absent. |
| Institutional distribution (18) | Partial | `/v1` APIs, data-portability/parcel exports, and deal memos exist. Versioned signal feeds, organization API keys, institutional integrations, signal memos, and portfolio monitoring remain future work; see `docs/enterprise-product-roadmap.md`. |

## Five-Market Intake

This is a static catalog audit, not a provider check or ingestion authorization.
Sources: `app/services/ingestion/{catalog,promoted_catalog,candidate_catalog}.json`.

| Market | Starting point and constraint |
| --- | --- |
| Northern Virginia | Configured `fairfax_county_va_development_tracker_site_records`; Fairfax is a starting jurisdiction, not coverage of the full market. |
| Dallas-Fort Worth | Configured Fort Worth commercial permits and Arlington applications/issued permits; `dallas_tx_legistar_planning_agendas` supplies pre-approval evidence, not verified decisions. |
| Phoenix | `phoenix_az_plan_review_and_permits` and Maricopa planning-agenda candidates are `legal_hold`. No promotion based on roadmap priority. |
| Atlanta | `atlanta_ga_building_permit_tracker` is `legal_hold`; access and permitted commercial use require resolution. |
| Columbus | Configured `columbus_oh_site_engineering_applications` and `columbus_oh_commercial_building_permits`; measure actual time depth and jurisdiction reach. |

Qualify jurisdiction/utility-service-area boundaries, permissions, historical
depth, stages, duplicates, missingness, freshness and inventory per market.
No market is accepted here; permit volume cannot substitute for missing utility
inputs in a Power Constraint score.

## Acceptance-Gated Backlog

All items remain open without dated evidence: owner, code/method version,
test/evaluation artifact, result, limitations and reviewer. Phases express
dependencies, not calendar promises. Local acceptance is not operational approval.

### P0: Temporal Foundation

**Selected first increment:** append-only temporal observations/events, raw
provenance, non-backdated receipt and recording times, authenticated as-of API,
basic numeric change, and permit/planning projection. No signal scores,
backtests, full utility ingestion, or major UI. These are behavioral acceptance
criteria, not a requirement to finalize the broader model shape now.

| ID | Deliverable | Acceptance gate |
| --- | --- | --- |
| P0.1 | Tenant-scoped observation/event storage | Capture entity, attribute, typed value/unit, source/source type, geography, confidence or explicit unknown, relationship references where evidenced, and method version. Every observation resolves to immutable raw evidence; every event resolves to its observation/evidence. Reject cross-tenant links. Enforce append-only normal writes; corrections/retractions append with traceable identity instead of rewriting prior rows. Test DB and API boundaries, including the documented erasure exception. |
| P0.2 | Receipt, recording, and event-time contract | Source occurrence/publication/update dates are separate from trusted first receipt (`RawSourceRecord.received_at`) and server-assigned observation/event `recorded_at`. No client or imported source date can backdate either system time. Preserve a verifiable existing raw receipt; new imports receive current capture time and legacy projections receive current recording time. Unknown historical availability stays unknown. Test delayed imports, old/future source dates, forged timestamps, and normalization corrections. |
| P0.3 | Idempotent permit/planning projection | Reuse raw records, canonical ingestion, source identities, and graph links. Identical retries do not duplicate observations/events; conflicting reuse of an identity is rejected. Changed payloads, mapping versions, and A -> B -> A recurrence retain distinguishable history. Keep filed/pending/approved/issued/withdrawn stages distinct where supported; do not turn ingestion `created`, agenda appearance, or missing snapshot rows into unsupported economic events. Preserve raw titles/excerpts and bounded graph labels. Test both source types, retry/rollback, correction, and reprocessing. |
| P0.4 | Bounded authenticated as-of reads | For knowledge cutoff T, return only observations whose trusted receipt and recording times are <= T. Events additionally require their own recording time <= T. Filter before choosing current values or applying corrections. Do not silently join today's canonical facts or graph merges into historical answers. Return evidence IDs, time semantics, stable ordering, bounded pagination, and explicit unavailable states. Test exact cutoff boundaries, late events/corrections, no-auth and cross-tenant denial. This is temporal data access, not a backtester. |
| P0.5 | Basic numeric change | Compare the latest two eligible recorded observations in the same entity/source-record/attribute/method series at T, with compatible units. Return observation IDs, values, absolute delta, direction and `100 * (current - previous) / abs(previous)` when previous is nonzero. Define missing-history, nonnumeric, incompatible-unit, overflow and zero-baseline states; never substitute zero or infinity. No acceleration, anomaly or investment scoring. |
| P0.6 | Local integration and regression acceptance | Exercise new schema/migration, immutability, timestamp, projection, as-of, and numeric cases on disposable local databases. Run relevant existing ingestion/planning/brand/graph/assessment/parcel regressions and API contract checks. Verify PostgreSQL forced RLS and mutation behavior as the application role before calling the DB contract accepted; a skipped test remains an open gate. No changes to deployed services or marketed coverage. |

**Time-proof fixture:** January event, raw receipt September 14, observation
recording September 15: absent at January and September 14 cutoffs; eligible only
after September 15 recording. A September 16 correction cannot change the earlier
result. Reprojecting old raw evidence cannot backdate normalized knowledge.
Full graph-as-of reconstruction remains a later dependency.

**Remaining P0, after the first increment:**

| ID | Deliverable | Acceptance gate |
| --- | --- | --- |
| P0.7 | Expand physical identity/graph contracts | Add company hierarchy, project, facility, utility, municipality/market, infrastructure and event semantics incrementally. Labeled resolution cases demonstrate justified links, unresolved cases, and reviewable corrections. Preserve historical identities and time-bounded relationships; do not rewrite earlier evidence after a merge. Reuse the existing graph explorer for internal QA. Full securities/debt exposure work stays P4. |
| P0.8 | Qualified historical input corpus | Admit bounded, rights-cleared historical permit/planning, land, construction, and infrastructure inputs for the selected first market, then qualify the other four separately. Inventory dates, units, stages, duplicate projects, gaps, and source/method versions are reproducible. Retrospective archives remain labeled as such; publisher event dates do not prove information was available then. A first market and minimum usable history must be accepted before P1 scoring. |

### P1: Proprietary Intelligence

Requires P0's relevant data/identity gates. Define P2 outcomes and holdouts before
tuning; start replay-contract work alongside experiments, not after UI work.

| ID | Deliverable | Acceptance gate |
| --- | --- | --- |
| P1.1 | Historical baselines and change detection | Compare trailing/historical periods, seasonality, markets/companies and peers where supported. Document sampling windows and denominators; treat outages, onboarding, duplicate projects and corrections separately from economic change. Require minimum sample sizes and abstain when coverage is inadequate. Reproduce each delta and any anomaly statistic from cutoff-eligible inputs. |
| P1.2 | Three experimental signals in sequence | First Development Velocity in one qualified market; then Power Constraint using rights-cleared utility filings, queues, substations/transmission/generation and demand evidence; then Physical Expansion using resolved facilities, permits, land, hiring, CapEx/disclosures and utility activity. Each needs a versioned method, explicit required/optional inputs, missing-data policy, repeatable daily/weekly output and cited drivers. Proposed 0-100 scores are unvalidated research outputs until P2; full utility adapters belong here, not the first P0 increment. |
| P1.3 | Signal object and evidence contract | Supply PRD section 9 header, what changed, cited drivers, historical statistics/comparisons, implications/exposures, support/counterevidence, invalidation and related signals. Explain confidence separately from score; mark unavailable fields. Counterevidence retrieval records search scope; absence is unknown, not proof. Analyst approval is not empirical validation. |

### P2: Validation Before Major UI

| ID | Deliverable | Acceptance gate |
| --- | --- | --- |
| P2.1 | Cutoff-safe replay and versioning | Freeze source snapshots, entity mappings, features, code/method versions, cohorts and outcome definitions. Exclude future information, later corrections and survivorship leakage. Distinguish actual known-then replay from retrospective reconstruction; unavailable history cannot be invented. Repeated runs reproduce results. Use only isolated local/approved evaluation data. |
| P2.2 | Evaluate all three signals | Predeclare outcomes/horizons, simple baselines, sample requirements, holdout periods/markets, false-positive tolerance and lead-time comparator before tuning. Measure frequency, average/median subsequent outcome, hit rate, false-positive rate, and results by geography, environment and confidence, with sample sizes and uncertainty. Produce an internal evaluation report or minimal QA view, not a polished terminal. |
| P2.3 | Independent go/no-go review | Freeze feature expansion, inspect false positives and contradictions, and document keep/revise/kill decisions and methodology. Weak signals are removed or revised and retested; thresholds cannot be chosen after seeing results. Require accepted results for the three-signal product before major P3 investment. Inconclusive evidence means hold, not predictive marketing. |

### P3: Institutional Product

Requires P2 acceptance. Existing workflows/minimal QA can support validation;
polished terminal work cannot lead it.

| ID | Deliverable | Acceptance gate |
| --- | --- | --- |
| P3.1 | Change-first terminal, signal, market/company views and search | Each displayed signal drills through versioned drivers, evidence/counterevidence, history, methodology, and measured performance. Missing/stale data is visible; no fabricated conviction, completeness, or exposed companies. Complete desktop/mobile research flows without regressing permit/planning/retail review or saved parcel work. |
| P3.2 | Research Copilot | Explain drivers, contradictions, exposures, similar periods, invalidation and next investigation with citations. Separate facts, calculations, model conclusions and speculation; abstain on unsupported causality. Test reference integrity, tenant isolation and known-time boundaries. |
| P3.3 | Watchlists and material alerts | Persist companies, markets, themes, assets and infrastructure projects. Test preferences, deduplication, thresholds, corrections and contradiction alerts with traceable signal versions. Analysts confirm materiality without notification spam. |

### P4: Financial Layer

Requires validated physical signals and qualified financial inputs. Extending to
additional asset classes also requires the domain-expansion gate below.

| ID | Deliverable | Acceptance gate |
| --- | --- | --- |
| P4.1 | Securities, debt and exposure graph | Licensed identifiers, ownership/subsidiary paths, lender/debt terms and portfolio positions resolve with effective/known-time lineage. Prove direct exposures first; label and review second-order beneficiary/adverse-exposure hypotheses separately. Proximity alone is not financial exposure. |
| P4.2 | Physical Activity Divergence and Capital Stress | Compare physical observations against timestamped public expectations; add debt maturities/refinancing, vacancy/rents, liens, transactions and asset evidence for stress. Apply separate methodology, cutoff-safe financial-outcome evaluation and independent go/no-go gates. Neither legacy deal scores nor generic memo buy/pass labels establish these signals. |

### P5: Distribution

Requires accepted signal contracts, permitted redistribution and satisfied pilot
operational gates; financial outputs additionally depend on P4.

| ID | Deliverable | Acceptance gate |
| --- | --- | --- |
| P5.1 | Institutional API, feeds, exports and integrations | Versioned schemas, scoped/revocable machine credentials, tenant isolation, pagination/cursors, correction/withdrawal delivery, idempotent consumption and source-use restrictions pass contract/security tests. Exported claims preserve as-of time, method version and evidence lineage. Existing `/v1` endpoints are a foundation, not completion. |
| P5.2 | Research memos and portfolio monitoring | Generate reviewed signal-based memos with counterevidence/invalidation, not mock enrichment or templated deal recommendations. Monitor authorized portfolio exposures with traceable changes, permissions and delivery controls. Pilot users can reproduce each cited result and understand unresolved exposure. |

## Product Evidence and Expansion Gate

Adopt signal precision, lead time versus a documented comparator, novelty,
research compression, and investment relevance as primary metrics. Define each
denominator, observation window and labeling/review process before evaluation.
Do not optimize this work around page views, MAU, chat counts or document volume.

Before expanding beyond the first domain, **all** PRD section 21 conditions must
be evidenced: at least three working proprietary signals; historical backtesting;
documented methodology; evidence lineage; repeatable generation; acceptable
false-positive rate; measurable lead time; at least five institutional users
consistently reviewing signals; at least three users reporting influence on
research or capital allocation; and at least one paying institutional customer.
Define acceptable statistical thresholds prospectively with research/pilot
owners. User influence is reported feedback, not proof of investment returns.
No condition is marked satisfied by this audit.

## Separate Work and External Gates

The **separate unreleased parcel repair** is user-reported work outside this
roadmap's acceptance evidence. Do not assume it is merged, deployed, tested here,
or a substitute for temporal P0. Preserve its ownership and review/release path;
coordinate compatibility through permit/retail/evidence-to-parcel regressions.

These require separate authorization; they neither prevent local P0 development
nor become satisfied by it.

| Gate | Current boundary | Evidence required to close |
| --- | --- | --- |
| Worker creation/activation | Creation pending approval per user; existing configuration is not authorization. | Explicit approval, reviewed source/wave/host scope, plan-only parity, bounded run evidence, freshness/failure handling and tenant checks. No provisioning in this task. |
| Recovery email | Reset routes/tests and Resend exist; `email_service.py` falls back to console without credentials. Delivery unverified. | Approved sender/configuration, delivered pilot recovery message, correct URL, expiry/single use, session revocation, safe failures and no token logging. |
| Pilot authentication/data smoke | Health/public login does not prove the pilot workflow. | Deployed `REQUIRE_AUTH_SMOKE=true`, matching schema/API/frontend, intended organization and real records; browser permit/planning/retail review -> parcel investigation -> save/export. Empty lists prove access only. |
| Backups/restore/isolation | Provider/retention assumptions in `docs/backups.md` are unverified; `docs/ops-log.md` has an example, not a completed drill. | Confirm provider/retention, isolated PostgreSQL restore, measured RPO/RTO, integrity and application-role cross-tenant read/write checks, with dated review. SQLite/CI are not substitutes. |
| Schema parity | New temporal tables match their migration, but repository-wide Alembic checks reproduce legacy model/migration drift on the unchanged baseline. | Reconcile legacy nullability/index differences under a separate reviewed migration; run the full drift check and PostgreSQL compatibility checks before release. |
| Measured coverage | Inventory API exists; configured counts/synthetic tests do not prove coverage. | Dated market/source inventory, failed runs, historical depth, freshness, stages, extent, gaps and overlaps. Aggregate all relevant pages; counts are per source, not cross-source deduplicated. Disclose unknowns, preserve legal holds; parcels are not verified for-sale inventory. |

References: `docs/customer_ingestion_dispatcher.md`,
`docs/runbooks/ingestion-scheduling.md`, `docs/measured-coverage.md`,
`docs/releases/database-readiness-20260912.md`, `docs/backups.md`, and
`docs/commercial-readiness-audit.md`. Historical checklists are not fresh
attestations; future releases require explicit authorization and dated evidence.
