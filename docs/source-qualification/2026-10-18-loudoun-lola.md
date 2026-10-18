# Source Qualification — Loudoun County, VA LOLA Land Applications (ArcGIS)

- **Date:** 2026-10-18
- **Jurisdiction:** Loudoun County, VA
- **Adapter:** `arcgis` (ArcGIS MapServer feature-layer query)
- **Record type:** `planning`
- **Proposed status:** `technical_hold` (NON-activated candidate; `can_run_canary` = false)
- **Rights posture:** Candidate-grade only — GeoHub "public access and use"; linked terms are a liability-only disclaimer, no affirmative commercial reuse grant. Confirm with Loudoun OMAGI before any promotion.

## 1. Confirmed live service / layer

The endpoint guessed from earlier notes (`.../loudoungis/rest/services/Projects/LOLA_DATA/MapServer/0`) 404s. The ArcGIS context path on `logis.loudoun.gov` is `/gis/`, discovered live via the REST services directory (`/gis/rest/services` → folder `Projects` → service `Projects/LOLA_DATA MapServer`).

- **Service:** `https://logis.loudoun.gov/gis/rest/services/Projects/LOLA_DATA/MapServer`
- **Layer 0:** `LOLA_PLANS_POLY` (Feature Layer, `esriGeometryPolygon`)
- **Query endpoint (confirmed):** `https://logis.loudoun.gov/gis/rest/services/Projects/LOLA_DATA/MapServer/0/query`
- **maxRecordCount:** `10000`
- **supportsPagination:** `true` (result-offset + keyset both viable)
- **Geometry:** polygon rings returned; `returnCentroid=true` is **not** honored by this MapServer (verified: a `returnGeometry=true&returnCentroid=true` probe returned `geometry` but no `centroid`). Lat/long-from-centroid mapping is therefore not proposed for the candidate probe.

### Layer 0 fields (name | esri type)

| Field | Type | Candidate? |
|---|---|---|
| `OBJECTID` | esriFieldTypeOID | row key (non-immutable) |
| `PlanGuid` | esriFieldTypeString | **yes — immutable identity** |
| `PlanNumber` | esriFieldTypeString | **yes — human id / keyset** |
| `PlanApplicationDate` | esriFieldTypeDate (epoch ms) | **yes — filed_at** |
| `PlanType` | esriFieldTypeString | **yes** |
| `PlanStatus` | esriFieldTypeString | **yes** |
| `PlanDescription` | esriFieldTypeString | **yes** |
| `PlanName` | esriFieldTypeString | **yes** |
| `AssignedTo` | esriFieldTypeString | staff PII — exclude |
| `AssignedEmail` | esriFieldTypeString | staff PII — exclude |
| `Shp_Source` | esriFieldTypeString | internal — exclude |
| `Shape` / `Shape.STArea()` / `Shape.STLength()` | geometry / double | geometry (not in candidate probe) |

Only `PlanApplicationDate` is a date field. There is **no update-watermark / status-change timestamp and no deletion feed** — a promotion blocker to resolve with OMAGI (watermark semantics + row-grain contract).

### Sample rows (bounded, `where=1=1&resultRecordCount=5&orderByFields=OBJECTID ASC`)

| PlanNumber | PlanType | PlanStatus | PlanName | PlanApplicationDate |
|---|---|---|---|---|
| AGDT-2013-0001 | Agricultural and Forestal District | Approved | WHITE CLOUD NINE VENTURES LP | 2013-06-01 |
| AGDT-2013-0002 | Agricultural and Forestal District | Approved | WHITE CLOUD NINE VENTURES | 2013-06-01 |
| AGDT-2013-0003 | Agricultural and Forestal District | Approved | WHITE CLOUD NINE VENTURES | 2013-06-01 |

`PlanApplicationDate` is epoch-ms (e.g. `1370059200000` → `2013-06-01`), normalizable to ISO.

## 2. Bounded read-only CANARY receipt

Constructed via `app.services.ingestion.connectors.build_connector("arcgis", {...})`, `page_size=3`, read-only single page.

- **Records fetched:** 3
- **Pagination:** `has_more=true`, keyset checkpoint emitted `{"keyset": {"PlanNumber": "AGDT-2013-0003"}}` — keyset field `PlanNumber` paginates cleanly.
- **Source reported:** `arcgis_featureserver`; `exceededTransferLimit=true` on a raw `resultRecordCount=5` probe (layer has many rows).
- **Candidate fields present / normalizable:** all of `PlanGuid, PlanNumber, PlanApplicationDate, PlanType, PlanStatus, PlanName, PlanDescription` present in every returned row; `PlanApplicationDate` epoch-ms normalized to date OK.
- **Centroid:** requested (`include_centroid=true`) but **not returned** by this MapServer — no lat/long produced. Not a blocker for a candidate; geometry available via `Shape` if needed later.
- **Failures:** none. Host reachable (DNS `logis.loudoun.gov` → `142.202.200.89`).

## 3. Proposed `candidate_catalog.json` entry (draft — NOT applied)

```json
{
  "key": "loudoun_county_va_lola_land_applications",
  "name": "Loudoun County LOLA Land Applications",
  "adapter": "arcgis",
  "record_type": "planning",
  "jurisdiction": "Loudoun County, VA",
  "base_url": "https://logis.loudoun.gov/gis/rest/services/Projects/LOLA_DATA/MapServer/0/query",
  "official_landing_page": "https://logis.loudoun.gov/gis/rest/services/Projects/LOLA_DATA/MapServer/0",
  "license": "GeoHub 'public access and use' posture; only linked terms are a liability-only disclaimer. No affirmative commercial SaaS reuse grant documented.",
  "status": "technical_hold",
  "blocker_summary": "Layer is current and lifecycle-rich (plan number, type, status, application date, description, polygon geometry), but there is no update watermark / status-change timestamp, no deletion feed, no documented row-grain/identity contract (PlanGuid appears immutable but is unconfirmed as the official key), and no commercial reuse grant. Rights are candidate-grade pending Loudoun OMAGI confirmation.",
  "early_warning_value": "County land-development applications (Agricultural & Forestal District, rezoning, special exception, site plan, etc.) with application date, type, and status expose commercial and subdivision projects before approval.",
  "candidate_source_fields": [
    "OBJECTID",
    "PlanGuid",
    "PlanNumber",
    "PlanApplicationDate",
    "PlanType",
    "PlanStatus",
    "PlanName",
    "PlanDescription"
  ],
  "probe_settings": {
    "connector": {
      "page_size": 5,
      "where": "PlanNumber IS NOT NULL",
      "out_fields": "OBJECTID,PlanGuid,PlanNumber,PlanApplicationDate,PlanType,PlanStatus,PlanName,PlanDescription",
      "keyset_field": "PlanNumber",
      "order_by_fields": "PlanNumber ASC",
      "include_geometry": false,
      "include_centroid": false,
      "query": {
        "f": "json",
        "outSR": 4326
      }
    },
    "defaults": {
      "county": "Loudoun",
      "state": "VA",
      "jurisdiction": "Loudoun County",
      "permit_type": "land_application",
      "approval_stage": "pre_approval"
    },
    "signal_stage": "pre_approval_and_approved"
  },
  "probe_field_mappings": [
    {
      "source_field": "PlanGuid",
      "canonical_field": "source_record_id",
      "is_required": true,
      "is_active": true
    },
    {
      "source_field": "PlanNumber",
      "canonical_field": "permit_number",
      "is_active": true
    },
    {
      "source_field": "PlanApplicationDate",
      "canonical_field": "filed_at",
      "transform": "epoch_millis_to_datetime",
      "is_active": true
    },
    {
      "source_field": "PlanType",
      "canonical_field": "permit_type",
      "is_active": true
    },
    {
      "source_field": "PlanStatus",
      "canonical_field": "status",
      "is_active": true
    },
    {
      "source_field": "PlanName",
      "canonical_field": "project_name",
      "is_active": true
    },
    {
      "source_field": "PlanDescription",
      "canonical_field": "description",
      "is_active": true
    }
  ],
  "can_run_canary": false,
  "last_checked_on": "2026-10-18",
  "next_audit_on": "2026-11-01",
  "notes": "Live metadata + 3-row read-only canary passed on 2026-10-18 (keyset pagination on PlanNumber, all candidate fields present, PlanApplicationDate normalizable). Keep NON-activated: confirm commercial reuse rights with Loudoun OMAGI and obtain a documented update-watermark/deletion and row-grain/identity contract (confirm PlanGuid as the official immutable key) before promotion. Exclude AssignedTo/AssignedEmail (staff PII). Centroid not returned by this MapServer; use Shape polygon geometry if location is needed later. Verify the `epoch_millis_to_datetime` transform name against the active transform registry before applying."
}
```

> Note: the `transform` names above (`epoch_millis_to_datetime`) should be validated against the live transform registry before this entry is committed; if epoch-ms dates are auto-normalized by the pipeline, drop the explicit transform.

## 4. Rights caveat

Loudoun GeoHub presents a general "public access and use" posture, and the only terms linked from the data are a liability-only disclaimer — there is **no affirmative commercial SaaS reuse grant**. Treat rights as **candidate-grade** and confirm in writing with Loudoun County OMAGI (Office of Mapping and Geographic Information) before promoting past `technical_hold`.

---

## Summary (6 lines)

1. Confirmed endpoint: `https://logis.loudoun.gov/gis/rest/services/Projects/LOLA_DATA/MapServer/0/query` (layer `LOLA_PLANS_POLY`, maxRecordCount 10000, paginated) — the `/loudoungis/...` path in prior notes was wrong; context is `/gis/`.
2. Fields (candidate): `PlanGuid` (immutable id), `PlanNumber` (keyset), `PlanApplicationDate` (epoch-ms date), `PlanType`, `PlanStatus`, `PlanName`, `PlanDescription`; excluded `AssignedTo`/`AssignedEmail` as staff PII.
3. Canary: `build_connector("arcgis", …)`, page_size 3 → 3 records, keyset checkpoint on `PlanNumber`, all candidate fields present, date normalizable, zero failures; host reachable.
4. Gap: this MapServer does not return a centroid (polygon geometry only), so no lat/long in the candidate probe.
5. Blockers for promotion: no update watermark / deletion feed / documented row-grain + identity contract.
6. Rights caveat: candidate-grade GeoHub "public access and use" + liability-only disclaimer, no commercial grant — confirm with Loudoun OMAGI before activation; status stays `technical_hold`, `can_run_canary` false.
