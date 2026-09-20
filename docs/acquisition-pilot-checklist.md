# Acquisition pilot checklist

## Local implementation, not deployed

- [x] Empty-map workspace diagnostics: authenticated tenant-scoped active permit,
  coordinate-bearing permit, active parcel, coordinate-bearing parcel, and saved
  search counts. Invalid geographic ranges excluded. Failed requests are not zeros.
- [ ] Verify these diagnostics against the authenticated production workspace.
- [ ] Replace schematic acquisition grid with a geographic map and independent
  geocoded signal layer. Current map still requires saved parcel candidates.
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
