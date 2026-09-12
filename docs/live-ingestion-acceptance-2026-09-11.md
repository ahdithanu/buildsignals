# Local Live-Source Ingestion Acceptance

Observed September 11, 2026, America/Los_Angeles (September 12 UTC).
This is evidence from a local customer-preview database, not a production
deployment, a nationwide coverage claim, or a recurring-worker acceptance.

## Initial Failure

The customer workspace had no configured sources, enrollment, ingestion runs,
or imported records. Other test tenants did not represent customer inventory.
The main Signals view queried saved analyst signals only, which also meant
successful raw imports would not automatically populate that page.

A private SQLite backup was taken before activation. The existing tenant admin
and onboarding service activated a reviewed FL/TX/WA scope for permit, planning,
and parcel records in waves 1 and 2. Thirty sources were enrolled, but only the
four below were fetched. Enrollment is not evidence of live coverage.

## Measured Inventory

| Reviewed source key | Stored records | With coordinates | Latest bounded run |
| --- | ---: | ---: | --- |
| `orlando_fl_permit_applications` | 1,500 permits | 0 | Partial, zero failed rows |
| `seattle_wa_land_use_permits` | 182 permits | 182 | Completed, zero failed rows |
| `dallas_tx_legistar_planning_agendas` | 185 planning records | 0 | Completed after retry, zero failed rows |
| `orange_county_fl_property_appraiser_parcels` | 1,000 parcels | 1,000 | Partial, zero failed rows |

These are canonical records, not unique development projects. A partial run
means its page budget ended while more provider pages remained. Completed means
the connector exhausted its configured window, not that the jurisdiction has
no other records. Earlier failed attempts remain in history.

- Orlando: 675 pre-approval and 825 approved records. Filing dates in this batch
  range from July 28 through September 11, 2026.
- Seattle: 53 pre-approval and 129 approved records. Historical applications are
  included; a publisher-provided 1900 date needs source-specific date-quality
  review. A recent fetch does not make every underlying filing recent.
- Dallas: meetings from August 3 through September 17, 2026. Agenda inclusion
  or a staff recommendation does not prove a final vote or approval.
- Graph: 5,599 entities and 7,020 relationships. Every relationship has evidence,
  confidence, creation time, and last-verification time. This validates storage
  integrity, not independent factual verification or extraction precision.
- Raw versions: 2,867. No fabricated signals, deals, coordinates, or sale listings
  were inserted to populate the preview.

## Reviewable Findings

- Dallas record `26-2866A`, case `PLAT-26-000193`, identifies Kroger Texas, L.P.
  as applicant/owner for a 5.413-acre replat. The company-name match remains an
  unreviewed candidate at 0.95 confidence. The document is evidence of a replat
  application, not confirmation of a new store or an investment return.
- Orlando permit `BLD2026-17380` names Walmart at 6095 S Goldenrod Road and is
  classified as signage, not new construction.
- The Wawa record at 3100 S Orange Avenue is an alteration. Walmart and Wawa
  both remain candidate company matches; 0.98 match confidence does not measure
  the probability of a new opening.

The Dallas source is the [official meeting record](https://cityofdallas.legistar.com/MeetingDetail.aspx?LEGID=4473&GID=713&G=FA9AD36F-9FB5-4633-8A99-4487E4A1114C).
Orlando records come from the [official permit dataset](https://data.cityoforlando.net/resource/ryhf-m453.json).
Evidence links and raw version lineage remain attached in the application.

## Fixes From Live Acceptance

1. Long planning titles no longer fail graph display-name validation. Compact
   labels retain the full title in graph attributes and canonical evidence.
2. Source-record IDs are authoritative for graph resolution. Distinct agenda
   items cannot merge solely because their titles and addresses match.
3. Oversized parcel references are preserved in
   `attributes._unresolved_parcel_reference`, without truncating an assemblage
   into a false single-parcel identity or rejecting the entire permit.
4. Planning company matching now works with the worker's `autoflush=False`.
5. Migration `20260911_0001` widens planning titles to PostgreSQL `TEXT`.
   A downgrade refuses to discard titles longer than 1,000 characters.
6. Operator onboarding now requires a validated existing tenant-admin actor,
   retains atomic audit context, and offers non-writing plan/dry-run commands.
7. Empty states distinguish unpopulated inventory from filtered results and
   inventory-query failures. The unfiltered initial Signals view can display
   bounded incoming planning and permit-match activity without manufacturing
   saved analyst assessments.
8. Permit-match responses expose the optional permit subtype, and incoming
   activity shows the work description rather than only a matched company name.
   Older API responses still display signage/alteration context when the
   canonical description supplies it.
9. An organization with no saved deals now sees bounded detected activity on
   both the default post-login Dashboard and Deal Inbox. The compact saved-deal
   empty state no longer hides imported evidence behind a manual-entry prompt.
   Saved-deal filters remain scoped to saved deals; displaying source activity
   does not create deals, confirm company matches, or publish assessments.

## Verification

The signed-in customer preview was checked at 390px and 1440px widths. Incoming
records rendered without horizontal overflow; permit details opened with their
lifecycle and graph links; the Brands page linked to Kroger's filtered planning
record, including its candidate status and expandable full source text.

The PostgreSQL upgrade/downgrade/re-upgrade test passed on a new disposable local
PostgreSQL 17 database and explicitly checked the planning-title `TEXT` type.
The temporary server was stopped afterward. This is migration verification, not
a production restore or production tenant-isolation drill.

Targeted regression tests cover long titles, source-ID isolation, oversized
parcel references, worker autoflush behavior, safe title downgrades, onboarding
authorization/dry-run/auditing, and permit-subtype serialization. Frontend tests
cover empty/error distinctions, bounded read-only activity, tenant query keys,
long evidence text, and unreviewed company-match labels.

The Inbox follow-up passed 334 frontend tests, typecheck, the production build,
and all nine Chromium workflow tests. The create-deal browser test verifies that
activity is available on the empty Dashboard and Inbox, then gives way to the
saved-deal list after an explicit creation. The actual customer Inbox displayed
Walmart and Wawa candidate permit matches and Dallas planning evidence locally;
390px and 1440px layout checks found no horizontal document overflow.

## Reproduction And Release Gates

Use the documented [operator onboarding workflow](customer_ingestion_onboarding.md)
with the intended database, organization, and existing admin. Verify the current
reviewed rollout manifest and source-host policy. Apply migrations before
running imports that may contain long titles.

```bash
python -m alembic upgrade head
python -m app.services.ingestion.cli run \
  --organization "$ORGANIZATION_ID" \
  --source-key dallas_tx_legistar_planning_agendas --max-pages 10 --resume-latest
```

Run source canaries, then bounded persistent imports; normalization-only canaries
do not exercise database limits, graph projection, or company-match persistence.
Inspect measured coverage and the signed-in tenant's actual pages afterward.

Still pending:

- Deploy the reviewed application and migration to the intended production
  database; this local import does not populate production.
- Validate scheduled dispatch, retry recovery, source freshness, and measured
  inventory in production before claiming continuous coverage.
- Acquire verified anchor coordinates for the Orlando company matches and
  import the relevant surrounding parcel inventory. The first 1,000 Orange
  County parcels do not contain those exact anchor parcel IDs. No ranked nearby
  candidates or verified-for-sale status can be inferred from this batch alone.
- Review company identity, project intent, historical date quality, and source
  decisions before publishing an analyst assessment.
- Audit previously merged source-record entities before claiming historical
  identity repair. The resolution fix prevents new title-only merges; it does
  not automatically split existing merges or rewrite stored review decisions.
- Complete production recovery, tenant-isolation, key-management, and shared
  authentication-store evidence separately. Local acceptance is not enterprise
  security certification.
