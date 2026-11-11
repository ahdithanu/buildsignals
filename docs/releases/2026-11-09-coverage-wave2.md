# Coverage wave 2

November 9, 2026, America/Los_Angeles. Existing production tenant and regional
image retained; no demo copy, migration, paid model call or paid-plan change.

| City | Source | Live canary | First scheduled run |
|---|---|---|---|
| Cary | `cary_nc_development_applications` | 27 records, 10 valid samples | 27 inserted, 0 failed; 27/27/27 before/seen/after |
| Detroit | `detroit_mi_bseed_building_plan_reviews` | 254 records, 10 valid samples | 254 inserted, 0 failed; 254/254/254 |
| Raleigh | `raleigh_nc_development_plans` | 113 records, 30 valid samples | 113 inserted, 0 failed; 113/113/113 |
| Bend | `bend_or_permit_applications_point` | FAILED publisher-update freshness | Not activated |
| Tacoma | `tacoma_wa_commercial_permit_lifecycle` | ArcGIS token required (499) | Not activated; needs supported authorized access |

Three new daily regional schedules are enabled. All three actual Scheduler tasks
stopped with exit 0. Source-local counts describe 394 newly stored records, not
394 unique projects, retailer expansions or verified for-sale properties.

| City | Task ID | Run ID |
|---|---|---|
| Cary | `904f7248c9f140b7802afbdb4a0e0abf` | `30a8225c-93ba-4603-9e88-53734e97404c` |
| Detroit | `398a0d1bcc294e8a9dfbc8ff14ff804c` | `c86532e5-e324-4834-8651-36caa551a388` |
| Raleigh | `09b36120d7a3454393f55cc08701617e` | `997e2086-64d3-48e6-981b-6c00e0392cd7` |

Receipts: `/ecs/buildsignals-ingestion`, stream `<schedule-name>/worker/<task-id>`.
Each new task uses revision 1 and the existing regional image
`sha256:3115a8ca51aedabbe52b640b607fe39a3aea6219564ccbf351b8edbd6e0bc8b2`.

## Contracts And Limits

New date scopes combine application/submission and action/update dates over a
half-open UTC 31-calendar-day window. Detroit date-only fields use DATE literals;
the others use TIMESTAMP. Bend's cursor is ascending OBJECTID; layer URLs receive
the same `/query` suffix for count requests as the fetch connector.
Existing reviewed fields, source predicates, geometry permissions and suppression
remain. No full-snapshot retirement is performed on bounded windows.

These windows are not complete lifecycle reconciliation: status filters can hide
records that leave the admitted status set, and changes outside exposed date
fields can be missed. Those records are not inferred deleted or retired. Do not
call stored statuses current beyond their evidence timestamps. Source timezone
interpretation and publisher completeness are not independently attested.

The upgrader now enumerates existing schedules instead of treating every canary
eligible key as deployed. Bend/Tacoma remain canary eligible but unscheduled.
The clearer authentication-error message in local code was added after the three
revision-1 jobs were provisioned; it is not claimed as deployed in those jobs.

## Parcel And Retail Readiness

An aggregate-only read-only production audit, task
`0732df439abe4fe4b9c1af06ef6f0b08`, found 0 brand profiles, 0 structured brand
matches and 0 active parcels. Miami-Dade has 295 stored/geocoded permit records;
Orlando has 1,443 stored and 0 geocoded. This is not proof that no filings mention
brands. It establishes missing structured catalog/match materialization.

Qualified retail anchors are not yet established. Do not choose a fabricated
anchor, auto-confirm a retailer match, claim mapped parcels or enable broad
county snapshots. Parcel qualification tooling is read-only and default-inactive;
publisher freshness and actual retail anchor acceptance remain explicit gates.
