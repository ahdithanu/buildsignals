# Planning and Meeting Intelligence

## Why This Layer Matters

Building permits often appear after site control, entitlement work, and public
negotiation have already started. Planning commissions, city councils, zoning
boards, economic-development authorities, design-review boards, and utility
commissions can publish useful evidence six to eighteen months earlier.

This layer treats those records as planning evidence, not as permits. That
distinction preserves the meaning of stages such as scheduled, staff review,
public hearing, recommended, approved, denied, and withdrawn.

## Canonical Record

`planning_records` stores one current representation of an official public
item while `raw_source_records` retains every immutable source version. A
planning record can represent:

- agenda item
- meeting minutes
- staff report
- zoning or entitlement case
- incentive or development agreement
- annexation or comprehensive-plan amendment
- design-review or utility-capacity discussion
- public hearing or notice

The canonical fields include title, summary, evidence excerpt, meeting and
publication dates, governing body, project, address, parcel, applicant, owner,
developer, coordinates, source URL, confidence, categories, and priority
reasons. A stable source record identifier is required.

## Priority Detection

The first classifier identifies:

- data centers, hyperscale campuses, server farms, and mission-critical facilities
- public incentives, abatements, development agreements, and PILOT agreements
- rezonings, conditional uses, site plans, annexations, and plan amendments
- new facilities, distribution centers, manufacturing facilities, and headquarters
- exact company aliases from the shared company and brand catalog

Ambiguous company aliases require context. All company matches remain
reviewable and retain the exact field, excerpt, detector version, confidence,
raw record, first-seen timestamp, and last-seen timestamp.

## Knowledge Graph Projection

Each planning item becomes a source-record entity linked to its canonical
record. Evidence-backed relationships connect it to the subject property,
tracked companies, applicants, owners, and developers. Property links preserve
address, parcel identifier, and coordinates so nearby-parcel discovery can run
once the event has a reliable location.

### Official Cross-Source References

`record_external_references` is the indexed bridge between distinct canonical
records that cite the same official identifier. A row stores the canonical
record type and ID, an explicit namespace, normalized value, source field,
optional source URL, immutable raw-record pointer, creation time, and last
verification time. It does not merge the records: an agenda item remains a
planning event and a current-project row remains a permit/project record.

Sources opt in through `settings.external_reference_extractors`. Extractors
support direct scalar IDs and URL query parameters with an optional exact-host
allowlist. For example, a meeting source can publish a scalar Legistar matter
ID while a project source extracts the same ID from an official legislation
URL:

```json
{
  "external_reference_extractors": [
    {
      "source_field": "legistar_matter_id",
      "namespace": "legistar:example-city:legislation",
      "transform": "scalar"
    },
    {
      "source_field": "legislative_url",
      "namespace": "legistar:example-city:legislation",
      "transform": "url_query_parameter",
      "parameter": "ID",
      "allowed_hosts": ["example-city.legistar.com"]
    }
  ]
}
```

Namespaces must identify both the issuing system and jurisdiction so unrelated
systems cannot collide. Matching also requires the same normalized city and
state. Exact canonical permit/file numbers remain the first join path; an
external reference is used when those numbers differ. Created graph edges keep
both reference-row IDs and raw evidence pointers. If a source corrects or
removes an identifier, the current index is updated and the former graph edge
is closed with `valid_to` rather than deleted.

Existing records can be indexed without refetching an external system. Run a
dry pass first, then execute bounded resumable batches:

```bash
python -m app.services.ingestion.cli references backfill \
  --organization ORGANIZATION_ID \
  --record-type permit \
  --source-key madison_wi_current_planning_projects \
  --batch-size 500 \
  --dry-run
```

Remove `--dry-run` after reviewing the counts. Use the reported `next_cursor`
with `--after-id` to resume a capped run, or set `--max-records` for a deployment
window. The command reads only existing canonical and immutable raw rows; it
does not open network connections. Run each record type separately. Backfilling
a production project source does not authorize or activate a held planning
source, which must complete its own approval and promotion process first.

## Source Rollout

Prioritize source families in this order:

1. Structured agenda APIs and open-data tables with item-level IDs and text.
2. RSS or Atom feeds for official notices and meeting updates.
3. HTML agenda and staff-report pages with stable URLs.
4. Text PDFs with page-level citations.
5. Scanned packets requiring OCR, only after document quality monitoring exists.

The highest-value governing bodies are planning commissions, city councils,
zoning boards, economic-development corporations, boards of adjustment,
design-review boards, and public utility commissions. Coverage is managed by
jurisdiction and source, not by state alone.

## Document Extraction Path

The next service boundary is a bounded document fetcher that:

1. Downloads only allowlisted official URLs.
2. Records content type, byte size, checksum, fetch time, and source URL.
3. Extracts HTML or PDF text without altering the original evidence.
4. Retains page or section citations for every excerpt.
5. Rejects encrypted, oversized, malformed, or unsupported documents.
6. Sends extracted sections through the planning classifier and entity resolver.

OCR should be asynchronous and separately metered. Low-quality OCR must lower
confidence and never silently replace the official document.

## San Jose Reference Pattern

San Jose demonstrates the preferred multi-source city pattern:

1. The Planning Director hearing archive discovers dated agenda and minutes
   documents and records cancellations.
2. Agenda PDFs create early planning events at the agenda-item grain, with the
   official file number, hearing date, project scope, location, parties,
   environmental review, and staff recommendation preserved as page-cited
   evidence.
3. Minutes update the same event with the public decision; they do not replace
   the agenda evidence.
4. The Data Center and Other Large Energy Use Projects page provides a monthly
   priority watchlist for applications on file and links into permit and
   environmental-review records.
5. The existing San Jose Planning Permit Applications source supplies the
   authoritative application lifecycle, address, APN, parties, status, and
   geometry. Its `FOLDERRSN` maps to the `folderRSN` identifier in SJPermits.

Records join by normalized planning file number first, followed by `FOLDERRSN`,
APN, and normalized address. A meeting cancellation is not a project
withdrawal, and disappearance from a current-project table is not a final
decision without corroborating evidence. Once a joined record has reliable
geometry or an APN, it can enter nearby-parcel discovery.

The `san_jose_ca_planning_director_hearings` candidate is fully configured for
the bounded `planning_documents` adapter but remains `technical_hold`. Its
probe limits index traversal to one page, 24 same-host documents, 10 MB per
document, 100 items per document, and 250 records. The item rules recognize
headings such as `4.A SP26-005 & ER26-024`, preserve every official file number,
and extract project description, address, owner, environmental review, and
staff recommendation with document hash and page provenance. Defaults label
agenda items as pre-approval hearing signals and minutes as recorded decisions;
freshness is measured from daily collection, with a seven-day SLA.

An official-page probe using a production-style HTTP client returned HTTP 403
on 2026-08-22. The candidate must not be promoted until San Jose provides or
confirms a supported automated access path. Browser automation is explicitly
not an activation strategy.

## CivicEngage Agenda Pattern

The existing `planning_documents` boundary also supports CivicEngage agenda
centers when a publisher provides same-host HTML agenda views. The connector
reads the bounded meeting index, follows only allowlisted HTML agenda links,
segments numbered project items, and emits stable hearing evidence from official
case numbers. Packets, staff-report attachments, media, contacts, and raw
document redistribution remain outside this boundary.

Maricopa County is the first validated example. A three-meeting no-write canary
on August 26, 2026 emitted 18 project-level records with no missing case
identities. The sample included zoning (`Z`), comprehensive-plan (`CPA`), and
military-compatibility (`MCP`) cases from June 25, July 23, and August 6. Repeated
cases reconcile through the `maricopa:planning_case` external-reference
namespace instead of being treated as unrelated projects.

The Maricopa candidate remains `legal_hold`. Arizona's commercial-purpose
public-record rules require BuildSignal to disclose the intended commercial use
and obtain County approval before production storage, analysis, or customer
display. The configured source therefore cannot run a canary, promote, schedule,
or enter the production host allowlist until that approval is recorded.

Jacksonville demonstrates the same document boundary against current PDF
agendas. Its official Planning Commission page publishes a meeting agenda and a
results agenda for the same hearing date. The source definition classifies the
first as `hearing_scheduled` and the second as `decision_recorded`, then joins
both through exact zoning, variance, waiver, land-use, or ordinance case IDs.

Jacksonville also drives two reusable safety improvements. The document index
accepts official two-digit years such as `08-20-26` using Python's bounded `%y`
century rule, and `planning_documents` can apply source-configured suppression
patterns before segmentation and evidence creation. The Jacksonville scope
uses that boundary to remove complete owner/agent lines before they can enter a
summary, evidence excerpt, or raw planning item.

The August 26, 2026 canary emitted 38 addressed project records from the current
agenda/results pair: 19 scheduled hearings and 19 recorded decisions, with no
missing case identities and no retained owner or agent lines. City website
copyright leaves the source on `legal_hold` pending explicit commercial reuse,
storage, attribution, and derived-display approval.

## Legistar Source Family

`LegistarPlanningConnector` provides a reusable boundary for cities that expose
current public meetings through the Granicus Legistar Web API. It discovers a
bounded date window of events, filters to allowlisted governing bodies, and
requests item-level agenda and minutes notes without downloading attachments.
Each emitted record has a stable identity composed from the Legistar client,
event ID, and event-item ID.

Agenda evidence emits a `hearing_scheduled` pre-approval signal. Minutes or an
official action emit a `decision_recorded` lifecycle state while retaining the
same source identity and immutable raw versions. Items without a positive
matter ID or official file/reference number are rejected; this keeps procedural
and accessibility text out of the intelligence layer. Per-run event, item,
record, and evidence-size limits protect the ingestion worker.

Dallas is the first configured candidate because its `cityofdallas` API and
City Plan Commission body were current during validation on 2026-08-24. It
entered `operational_retry` after the narrow commercial SaaS storage and
derived-display scope was approved on 2026-08-24. Its bounded canary and
promotion review passed the same day, and it now runs as a daily pre-approval
production source with an exact-host deployment policy.
Atlanta is not configured because its public Legistar event feed was stale at
July 2022 during the same validation. Other cities must pass current-feed,
body-name, rights, and lifecycle checks before reusing the connector.

The Dallas canary measures publisher freshness against a 14-day SLA that
matches the planning-meeting publication cadence while retaining daily change
collection. A bounded one-year probe on 2026-08-24 found no minutes or action
payloads in 21 City Plan Commission events, so Dallas Legistar is admitted only
as a pre-approval agenda source. Existing permit feeds remain the approval and
issuance confirmation layer; Dallas needs a separately validated official
minutes source before planning decisions can be claimed.

Madison is the second validated Legistar pattern and demonstrates the fuller
lifecycle. A bounded 2026-08-25 probe processed seven Plan Commission events
and emitted 67 matter-backed records: three scheduled hearings and 64 recorded
decisions, with no missing matter/file identities. The candidate joins official
Legistar references to `madison_wi_current_planning_projects`, whose project
records already carry Land Use, Rezoning, and Urban Design Commission
legislative URLs, project IDs, addresses, parcels, organizations, and owners.
It remains `legal_hold` until its narrow commercial storage, derived-display,
attribution, and suppression scope is explicitly approved.

Arapahoe County is the third validated Legistar pattern and extends the meeting
moat into the Denver metro. The County's official planning page links its Active
Planning Cases map and states that the map covers land-development cases under
review. A bounded August 25, 2026 API probe processed 13 relevant meetings and
emitted 25 substantive records: eight scheduled hearings and 17 recorded
decisions, with 23 Planning Commission items, two Board of Adjustment items,
zero missing matter/file identities, and source modification through August 21.
The configured scope also includes the East Arapahoe County Advisory Planning
Commission. This candidate remains `legal_hold`; technical validation of public
records does not itself authorize commercial storage or customer-facing derived
display.

Hillsborough County is the fourth validated Legistar pattern and adds a dense
Florida land-use layer before downstream construction permits. A bounded August
27, 2026 probe processed 30 current meetings across BOCC Land Use, Zoning
Hearing Master, and Land Use Hearing Officer and emitted 330 decision-backed
records. Every record had a matter or case identity, and source changes were
current through August 25. The evidence includes rezonings, planned
developments, special uses, folios, acreage, locations, continuances,
withdrawals, and named applicants such as national retailers and developers.

This candidate also establishes a privacy-aware Legistar boundary. Public
applicant and organization names remain in derived evidence so entity
resolution can connect brands and developers to projects. Source-configured
patterns remove email addresses and phone numbers before titles, summaries, or
evidence are created; attachments, direct contacts, and raw redistribution are
excluded. The source remains `legal_hold` until Hillsborough County approves
the bounded commercial storage, attribution, and derived-display scope.

The initial connector uses newest-first EventId ordering with offset paging
inside a narrow date window so bounded canaries exercise current publication
activity.
If a client approaches the Legistar response cap or exhibits concurrent event
churn, migrate that source to EventId keyset paging before widening history.

## Tradeoffs and Scaling

- JSON categories are portable for the initial bounded queue; normalize them
  into a join table when query volume or taxonomy complexity warrants it.
- Exact aliases are favored over broad semantic matching to control false
  positives. Embedding search can later retrieve candidates, but deterministic
  evidence should remain the confirmation path.
- The checked-in catalog seeds major hyperscalers and data-center operators.
  Full Fortune 500 coverage should come from a licensed or customer-supplied
  watchlist with effective dates rather than an unversioned scraped list.
- Meeting records can change after publication. Immutable raw versions and
  first/last-seen timestamps make corrections and removals auditable.
- The external-reference index adds one write per declared identifier and keeps
  lookups relational and bounded. If a provider emits very high-cardinality
  identifier sets, move synchronization to a bulk upsert worker rather than
  replacing exact joins with fuzzy database scans.

## Unified Expansion Ranking

The brand expansion API combines reviewable company matches from planning
records and permits without collapsing their lifecycle stages. Each company and
market reports planning, pre-approval permit, and approved permit counts, plus a
combined evidence-weighted confidence score. Planning events can be filtered by
company so the UI can move from a ranked expansion signal to the official
agenda excerpt and source document.

Nearby-parcel counts remain anchored to permit matches until a separately
reviewable planning-to-parcel search workflow is available. This avoids
presenting a loosely located agenda mention as a parcel acquisition lead.
