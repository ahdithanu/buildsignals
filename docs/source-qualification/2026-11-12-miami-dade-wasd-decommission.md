# Miami-Dade WASD permit source — upstream decommission (2026-11-12)

**Source key:** `miami_dade_fl_wasd_unincorporated_permits_narrow`
**Status finding:** the publisher endpoint is **gone**; this is why the source's
production job fails (`ValueError` — ArcGIS "service not found"). This is an
upstream decommission, **not** a code bug and **not** a URL-swap fix.

## Live evidence (read-only, this date)
Catalog `base_url`:
`https://gisweb.miamidade.gov/arcgis/rest/services/Wasd/Permits_4_v1/MapServer/1/query`

- `GET …/Wasd/Permits_4_v1/MapServer?f=json` → `{"error":{"code":404,"message":"Service Wasd/Permits_4_v1/MapServer not found"}}`.
- `GET …/Wasd?f=json` now lists only `GovBound_8_v1`, `WASDCustomers_1_v1`,
  `WaterAndSewerServiceAreas_3_v1` — **no permit-process service**.
- Scanned every folder on the server (`311, RER, EnerGov, LandManagement, …`).
  The closest candidates — `EnerGov/MD_LandMgtViewer`, `LandManagement/*` — are
  **zoning / land-use / property viewers** whose layers (Governmental
  Boundaries, Land Records, Planning & Zoning, …) do **not** expose the WASD
  permit-process schema (`BLDPRCNO`, `BLDPRMNO`, `PROJDESC`, `BLDPRMSTAT`, …)
  this source maps. **No compatible drop-in replacement exists.**

## Why there is no in-place fix
Pointing the entry at any surviving service would ingest an incompatible schema
under this source's identity — a fabricated "fix." The honest options are:

1. **Retire the source.** Remove/hold `miami_dade_fl_wasd_unincorporated_permits_narrow`
   so it stops failing every cycle. This is a **gated, deployment-coupled**
   change: editing `catalog.json` regenerates the signed `production_rollout.json`
   (`catalog_fingerprint` / `manifest_digest`) that is embedded in `render.yaml`
   worker definitions, and drops `source_count` 134→133. It must go through the
   rollout-regeneration tooling + review, not a hand-edit. **Preserve already
   stored Miami-Dade rows** (do not silently delete historical evidence).
2. **Re-qualify a replacement** Miami-Dade permit feed as a *new source* (e.g. the
   county's EnerGov/CSS permit portal or an open-data permit dataset) — requires
   its own commercial-reuse basis, field mapping, canary, and activation
   authorization. Not implied by this finding.

## Recommendation
Until retirement/replacement is actioned through the proper tooling, keep the
existing **quarantine/freshness gate** doing its job (the failing receipt is
correct behavior, not a regression). Do not weaken source gates to silence it.

_Evidence gathered read-only; no catalog activation, manifest regeneration,
render.yaml change, or data write performed by this note._
