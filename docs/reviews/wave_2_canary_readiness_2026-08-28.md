# Wave 2 canary readiness - 2026-08-28

## Scope

The manifest-pinned Wave 2 readiness gate ran against all four deterministic
shards using the reviewed 22-host outbound policy. The wave covers 26 production
sources in California, Florida, and North Carolina.

## Initial result

The first bounded run reached every source. Twenty-two passed and four exposed
actionable issues:

- Hillsborough County parcels required the public Tampa ArcGIS browser request
  profile.
- Florida DEP's commercial ERP filter produced a URL the publisher rejected;
  the filter was shortened while retaining its commercial project terms.
- Wake County returned repeated ArcGIS rows with one official object ID because
  of a publisher-side address join.
- San Francisco's primary-address view had stopped refreshing in August 2025.

## Repairs

ArcGIS keyset pages now collapse repeated rows with the same publisher cursor,
preserving the first public record and a monotonic checkpoint. Tampa's source
uses the narrowly required public headers. Florida DEP retains commercial
matching across project and site names plus high-value description terms.

San Francisco now reads the official nightly DBI Building Permits dataset
`i98e-djp9` and filters to `primary_address_flag = 'Y'`, preserving the prior
one-primary-address behavior. Its durable history remains oldest-first, while a
separate newest-first canary proves the publisher's current refresh without
changing ingestion checkpoints.

## Final result

- Sources reached: 26
- Sources passed: 26
- Sources blocked: 0
- Records fetched: 169
- Records normalized successfully: 169
- Record validation failures: 0
- Shard results: `5/5`, `7/7`, `8/8`, and `6/6`

The successful samples included building permit applications and approvals,
planning and rezoning applications, environmental-resource permits, commercial
site plans, and county and statewide parcel context.

The canary staged catalog rows only inside its transaction and rolled them back
after each shard. It did not persist sources, runs, mappings, permits, parcels,
graph relationships, or opportunities.
