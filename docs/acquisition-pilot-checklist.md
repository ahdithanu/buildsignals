# Acquisition pilot checklist

## Local implementation, not deployed

- [x] Empty-map workspace diagnostics: authenticated tenant-scoped active permit,
  coordinate-bearing permit, active parcel, coordinate-bearing parcel, and saved
  search counts. Invalid geographic ranges excluded. Failed requests are not zeros.
- [ ] Verify these diagnostics against the authenticated production workspace.
- [x] Replace schematic acquisition grid with Leaflet geographic maps and an
  independent geocoded permit/planning layer. Parcel ranking still requires saved
  searches. Verified desktop/mobile with synthetic test data, not live inventory.
- [ ] Qualify a pilot-market parcel source, identifier namespace, and use rights.
  Columbus public candidate query returned 403; historical intake is local only.
- [ ] Verify evidence-backed signal to nearby candidate workflow in that market.
- [ ] Add structured multifamily and small-bay retail buy-box criteria with
  pass/fail/unknown results, provenance, and missing-diligence reasons.
- [ ] Verify source evidence, project timeline, nearby parcels, saved opportunity,
  and export on mobile and desktop with real qualified records.
- [ ] Release and measure live inventory, freshness, and source-specific coverage.

## Interpretation

GET /acquisition-map/readiness is read-only, authenticated, and no-store. Counts
are workspace-wide and not a snapshot transaction, geographic coverage measure,
search eligibility guarantee, unique-project count, or for-sale inventory. Valid
coordinate ranges do not independently establish geocoding accuracy. Saved
search counts include historical searches; no absence of commercial opportunity
can be inferred from an empty ranked candidate list.

## Geographic map contract

GET /acquisition-map/signals requires authentication and returns no-store,
tenant-scoped records independent of nearby searches. Each layer is capped at
100 records, ordered by canonical update time and ID, with explicit truncation.
Optional two-letter state filtering narrows the query. Permit retirement is
respected. Null/out-of-range coordinates are omitted; the map uses a conservative
Web Mercator latitude range of -85 to 85. Records are not unique projects or
confirmed brand expansions. Evidence IDs and original source links remain visible.
Planning links currently open the planning workspace, not a record detail page.

Leaflet is lazy-loaded. OpenStreetMap raster tiles load only for the visible map,
with attribution and an origin referrer. There is no bulk fetch or offline cache.
Tile failures show a notice without hiding source records. Public tiles have no
SLA: before a larger paid rollout, select a suitably licensed managed tile service.
See https://operations.osmfoundation.org/policies/tiles/ and
https://leafletjs.com/reference.html for the basemap policy and library reference.

Remaining pilot gaps: production counts and auth verification, qualified nearby
parcel inventory, reliable geocoding, reviewed brand relevance, richer geography
filters/pagination, and unified signal-to-parcel selection. Two maps currently
separate source-record geography from saved ranked parcel results.
