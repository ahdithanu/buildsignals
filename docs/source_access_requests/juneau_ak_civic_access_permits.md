# Source Access Request: Juneau Civic Access Permits

- Candidate key: `juneau_ak_civic_access_permits`
- Jurisdiction: Juneau, AK
- Record type: permit
- Current status: `technical_hold`
- Official source: https://juneau.org/community-development

## Requested delivery
- A supported HTTPS API or recurring CSV/JSON delivery
- A complete historical backfill plus an ongoing incremental feed
- A published refresh schedule, support contact, and change-notice process

## Requested fields
- record_id
- permit_number
- permit_type
- project_name
- status
- applied_date
- issued_date
- expiration_date
- finalized_date
- parcel
- address
- description

## Lifecycle requirements
- Include records from initial submission through final disposition
- Include created, submitted, modified, status-change, issued, and completed dates when available
- Provide status definitions and identify which statuses are pre-approval, approved, denied, withdrawn, expired, or void

## Reconciliation requirements
- Provide a durable source record ID that survives edits and status changes
- Provide a monotonic modification cursor or reliable last-modified timestamp
- Represent deletions, merges, withdrawals, and replaced records
- Provide row counts or another control total for each delivery
- Document pagination, rate limits, timezone, schema, and null semantics

## Rights confirmation
- Commercial SaaS storage and automated processing
- Normalization, entity matching, scoring, and other derived analysis
- Customer display of source-backed facts and evidence links
- Customer API and export of value-added results
- Retention of historical versions for audit and provenance

## Privacy limits
- Exclude personal phone numbers, personal email addresses, signatures, credentials, and payment data
- Exclude plan sheets and attached documents unless separately approved
- Permit suppression of personal party data while retaining organization names and public record identifiers

## Acceptance checks
- A sample delivery validates against the documented schema
- Record IDs are unique at the documented grain
- Incremental delivery reconciles to an authoritative control total
- Pre-approval and approved records are both present when the source tracks them
- Written rights cover the requested production uses

## Requested response

Please confirm the supported delivery method, field dictionary, refresh cadence, historical coverage, technical contact, and the production rights listed above.
