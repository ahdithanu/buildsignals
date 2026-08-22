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
