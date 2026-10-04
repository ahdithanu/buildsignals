# Measured Ingestion Inventory

The Coverage page (`/source-health`) now distinguishes configured sources from
canonical records stored for the signed-in organization. The report supports
permits, parcels and planning records, with 25 sources per page and adjustable
freshness windows. The readiness rollup spans every measured source for the
selected record type in the signed-in organization, while the detailed source
list remains paginated. These are stored-record measurements, not provider
totals or national coverage claims.
The UI also rolls the current source page into up to six observed state/DC
buckets so a reviewer can quickly see where stored records, geocoded rows,
collection recency and source-date recency actually exist. This rollup is still
source-page scoped; it is not a statewide coverage score or a substitute for
statewide completeness.
The API returns `readiness` for the selected record type and `page_totals` for
the current query page so the frontend can display measured source,
stored-record, geocoded-record, freshness and observed geography counts without
deriving broader coverage claims in the browser.
It also returns `readiness_states`, an all-source observed state/DC breakdown for
the selected record type, and `readiness_jurisdictions`, a bounded top local
jurisdiction/city-style rollup. Unknown geography stays explicit.
Each returned source includes a `readiness_status` and short
`readiness_reasons` so operators can distinguish empty, disabled, stale, fresh
and unknown-date sources without inferring from raw counts. The response also
includes all-source `readiness_status_counts` for the selected record type; the
UI renders those counts as clickable, URL-backed audit buckets and provides a
copy action for the current measured-inventory view. Record type, readiness
status, and freshness window are preserved in copied links.

## API and Semantics

`GET /v1/ingestion/coverage/measured` requires authentication and returns
`Cache-Control: no-store`. Parameters are `record_type` (parcel, permit, planning),
`limit` (1-100), `offset` (nonnegative), `freshness_hours` (1-8760), and
optional `readiness_status` (`fresh`, `empty`, `disabled`, `stale_collection`,
`stale_source_date`, or `unknown_source_date`).

- Counts are unique within a source, not deduplicated across overlapping sources.
- Inactive permit/parcel rows are excluded. Disabled sources and zero-record
  configured sources remain visible.
- Collection recency and the latest raw record's source-update date are separate.
  Unknown and future source dates remain explicit; collection today does not mean
  that the source published or changed today.
- Only recognized state/DC codes are grouped as known states. Unknown geography
  is not inferred from a configured jurisdiction.
- Valid coordinate counts and observed extents do not prove geocoding accuracy or
  complete geographic coverage. Jurisdiction labels are not nationwide totals.
- Parcel inventory does not establish verified for-sale availability.
- `readiness` spans all configured sources for the selected record type in the
  signed-in organization. It is tenant-scoped measured inventory, not a market
  coverage claim.
- `readiness_states` rolls up observed canonical-record state/DC values across
  all measured sources for the selected record type. It is not statewide source
  completeness and does not infer geography from configured jurisdiction names.
- `readiness_jurisdictions` surfaces the highest-volume observed jurisdiction
  labels from stored canonical records. It is an operations drilldown, not proof
  of citywide completeness.
- `page_totals` is scoped to the returned source page and request filters. It is
  not a tenant-wide total unless the caller has paginated through every page and
  retained the same query parameters.
- `readiness_status_counts` spans all configured sources for the selected record
  type and is not affected by pagination or `readiness_status` filtering.
- Source-level readiness statuses are operational triage labels. They do not
  certify source rights, provider uptime, or market completeness.

The UI hides unconfirmed totals when measurement fails, provides retry and bounded
pagination, and keys queries by organization and all parameters. The surrounding
configured-state filter does not restrict this organization-wide inventory.
The observed-state rollup is intentionally absent while the measurement is
loading or unavailable, and unknown geography remains labeled as unknown instead
of being inferred from configured jurisdictions.

## Deployment and Verification

This release requires no database migrations, encryption keys, or new services.
It uses existing canonical records and never invokes upstream providers. Deploy
the backend and frontend together; an older backend yields an unavailable state,
not fallback or invented counts.

Coverage tests exercise scope, date semantics, empty sources and query bounds.
Frontend tests cover page/filter changes, loading/error/retry and organization
changes. The authenticated browser regression covers a new empty organization;
the CSP smoke test uses synthetic populated data at mobile, tablet and desktop
widths. None of those synthetic counts are production coverage evidence.
The authenticated post-deploy smoke script also checks permit, parcel and
planning measured-inventory responses for the expected shape. That smoke allows
empty responses by design; it proves the deployed API contract is reachable, not
that live records exist.
The focused coverage-panel regression also verifies the production readiness
rollup and observed-state source-page rollup, while guarding against presenting
either as nationwide coverage.

For customer-facing claims, capture an authorized production measurement with
its timestamp, record type, source pages and freshness window. Configured feed
counts alone must not be marketed as live geographic completeness.

This release also changes organization user exports to a profile-field allowlist.
Password hashes, MFA shared secrets, encrypted secret fields, token-revocation
versions and superuser flags are excluded. The serializer and authenticated export
route have regressions for secret omission. MFA encryption at rest is implemented
in the application layer, but production readiness still depends on managed key
provisioning, legacy-secret backfill and disabling legacy plaintext reads.
