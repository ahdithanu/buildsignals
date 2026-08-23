# Brand Intelligence Cohorts

Build Signals uses bounded commercial watchlists to identify expansion activity in
permit filings and planning records. The catalog is an evidence-matching input, not
a claim that a company is expanding. A surfaced match still carries the underlying
record, matched field, confidence, and source provenance.

## National retail

The `national_retail` cohort contains the existing retail, restaurant, grocery,
fitness, and other customer-facing commercial brands in `brand_catalog.json`.
Regional operators remain in this national monitoring cohort because the cohort
describes nationwide collection coverage, not each company's operating footprint.

Every entry retains its existing category, scale, priority, aliases, and attributes.
The cohort adds:

- `attributes.signal_cohort = national_retail`
- `national_retail`, `retail_expansion`, and the existing category in
  `attributes.watchlist_tags`

Technology and data-center entries are explicitly tagged `data_center` and are not
mixed into the retail or builder views.

## Major builders

The `major_builder` cohort is a high-priority seed list of large residential builders
whose subdivision, entitlement, land-development, and homebuilding records can signal
future demand and nearby land opportunities. It starts with Toll Brothers, D.R.
Horton, Lennar, PulteGroup/Pulte Homes, NVR/Ryan Homes, KB Home, Taylor Morrison,
Meritage Homes, Century Communities, M/I Homes, Tri Pointe Homes, and Dream Finders
Homes.

All builder entries use national scale, priority 5, and the tags `major_builder`,
`homebuilder`, and `residential_development`. Aliases are limited to conservative
corporate or named-division forms. Ambiguous short forms such as `NVR` require
residential-builder context; broad initials such as `DR`, `KB`, or `MI` are excluded.

## Why this is not the Fortune 500

Fortune 500 membership is a revenue ranking, not a useful proxy for observable real
estate expansion. Importing the full list would add banks, insurers, manufacturers,
and holding companies whose names commonly appear in records for reasons unrelated
to a new site. That would increase false positives and review volume while weakening
the product's early-warning value.

These cohorts instead represent businesses with a clear commercial-location or
residential-development footprint and aliases that can be matched conservatively.
Additional companies should be added when there is a defined real-estate signal,
reliable aliases, and enough source evidence to measure precision.

## Scaling path

Future cohorts can be versioned by use case, such as industrial developers, hotel
operators, healthcare systems, and senior housing. Expansion should remain bounded:
add candidates, replay them against historical records, measure false positives,
then promote only aliases that meet the review threshold. Cohort metadata enables
ranking and filtering without hardcoding company-specific behavior into ingestion,
detection, APIs, or the frontend.

## Historical backfill

New source runs apply company detection automatically. After deploying catalog or
detection changes, replay existing active permits in bounded batches:

```bash
python -m app.services.ingestion.cli brands backfill \
  --organization <id-or-slug> \
  --batch-size 500
```

Use `--dry-run --max-records 1000` for a production sample before writing. The
summary prints a `next_cursor`; pass it back with `--after-id` to resume a capped or
interrupted run. Each completed batch commits independently, and detection remains
idempotent for permits that already have matches.

Scheduled ingestion synchronizes the company catalog before collecting records, so
new filings always use the deployed cohort definitions. Historical replay remains an
explicit operator action because its scope and write volume should be reviewed.
