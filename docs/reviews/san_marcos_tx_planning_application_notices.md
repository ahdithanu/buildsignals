# San Marcos Planning Application Notices Promotion Review

## Status

Approved by the Build Signals owner on August 14, 2026 for the narrow production
rights and data-minimization scope below. The machine-readable approval is in
`docs/reviews/san_marcos_tx_planning_application_notices_approval.json`.

## Source

- Candidate: `san_marcos_tx_planning_application_notices`
- Official archive: `https://www.sanmarcostx.gov/m/newsflash?cat=30`
- Official page: `https://www.sanmarcostx.gov/1537/Public-and-Application-Notices`
- Publisher: City of San Marcos, Texas
- Published purpose: public notice of submitted planning applications and
  related hearings

## Technical Review

The legacy CivicPlus RSS category remained empty on August 14, 2026 while the
official NewsFlash archive exposed fresh August 10-12 application notices. The
generic archive connector reads the category list only and does not follow
article detail, document, or attachment links. A bounded no-write canary fetched
10 records, validated all 10 as `pre_approval`, and reported zero failures.

Stable CivicPlus article IDs provide source identity. Posted dates are filing or
notice activity context, not a publisher refresh watermark. Records use stable
upserts, and disappearance from the bounded current window must not be treated
as withdrawal, denial, deletion, or approval.

## Approved Production Scope

Allow only:

- stable `article_id`
- notice `title`
- canonical official `link`
- `published_at` date
- contact-suppressed project `description`, capped at 2,000 characters

The bounded description may preserve project facts and named organizations,
including developers, applicants, representatives, and owners, for entity
resolution and evidence-backed graph relationships. The connector removes email
addresses and phone numbers before normalization.

Where the City's own summary uses explicit `submitted by` and `on behalf of`
language, declarative transforms map those values conservatively to canonical
applicant and owner fields. Applicant values keep `unknown` semantics and are
not relabeled as developers. Owner values can project through the shared graph
service as evidence-backed property-owner relationships.

Suppress and do not fetch:

- email addresses, phone numbers, and other applicant or planner contact fields
- article detail bodies beyond the bounded category-list summary
- linked permit records, plans, staff reports, and document bodies
- attachment contents
- raw archive replacement downloads or customer-facing raw exports

The approved export policy is
`derived_planning_notice_context_only_no_raw_document_export`.

## Approval Record

The Build Signals owner approved both statements on August 14, 2026:

1. Build Signals may store and process the official San Marcos Planning
   Application Notices metadata for commercial, customer-facing derived
   development intelligence with City attribution and no raw-source replacement
   export.
2. The field allowlist, connector-level contact suppression, link-fetch
   prohibition, and bounded-summary policy above are sufficient for production
   data minimization.
