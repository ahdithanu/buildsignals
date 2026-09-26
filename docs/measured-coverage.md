# Measured Ingestion Inventory

The Coverage page (`/source-health`) now distinguishes configured sources from
canonical records stored for the signed-in organization. The report supports
permits, parcels and planning records, with 25 sources per page and adjustable
freshness windows. Summary numbers apply only to the current source page, across
all observed states, not to the whole organization or the nation.

## API and Semantics

`GET /v1/ingestion/coverage/measured` requires authentication and returns
`Cache-Control: no-store`. Parameters are `record_type` (parcel, permit, planning),
`limit` (1-100), `offset` (nonnegative), and `freshness_hours` (1-8760).

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

The UI hides unconfirmed totals when measurement fails, provides retry and bounded
pagination, and keys queries by organization and all parameters. The surrounding
configured-state filter does not restrict this organization-wide inventory.

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

For customer-facing claims, capture an authorized production measurement with
its timestamp, record type, source pages and freshness window. Configured feed
counts alone must not be marketed as live geographic completeness.

This release also changes organization user exports to a profile-field allowlist.
Password hashes, MFA shared secrets, encrypted secret fields, token-revocation
versions and superuser flags are excluded. The serializer and authenticated export
route have regressions for secret omission. MFA encryption at rest is still a
separate gated release; export filtering does not resolve plaintext storage.
