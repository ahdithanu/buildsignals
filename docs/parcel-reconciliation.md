# Parcel Source Reconciliation

Generate the offline backlog with:

```sh
python scripts/parcel_readiness_report.py --output /tmp/parcel-readiness.json
```

The report compares the configured catalog, candidate catalog, and historical
decision ledger. It does not contact providers, activate sources, change rights,
or measure imported records. Unknown live validation and record counts remain
explicitly unknown. Configured activity must not be presented as live coverage.

## Baseline

On September 9, 2026, the local configuration contained 41 parcel sources,
zero parcel candidates, and 64 ledger sections. Of those sections, 26 did not
contain an explicit backticked configured source key. This is a reconciliation
queue, not 26 missing connectors: aliases, overlapping geographies, and older
decisions require manual inspection. For example, San Diego has a configured
source even though its ledger section has no explicit key reference.

## Completion Gates

1. Resolve each ledger section to source keys or an explicitly held candidate.
2. Revalidate the official source, permitted fields, reuse scope, and attribution.
3. Implement any missing adapter using existing ingestion interfaces and fixtures.
4. Run a bounded canary, checking stable parcel IDs, coordinates, acreage units,
   source dates, duplicate handling, and jurisdiction coverage.
5. Measure imported unique parcels and run history in the target environment.
6. Exercise the evidence-to-nearby-parcel-to-saved-opportunity workflow.

Pinellas is a priority discrepancy: its ledger records admission for a bulk-file
cohort, but the catalog has no corresponding source. This historical decision
does not authorize automatic activation. Its manifest, current terms, and
coherent release handling must be revalidated first.

Mississippi and other rights-held sources remain held. Missing owner, access,
or zoning fields must remain unknown rather than receiving inferred facts.
Nearby candidates must remain separate from verified for-sale inventory;
assessor records alone do not establish sale availability.

## Limits

The ledger parser recognizes level-two headings and bold Decision paragraphs.
An absent decision is reported as null. Exact key references are intentionally
conservative; this report does not perform fuzzy source admission. Regenerate
the report after catalog or ledger edits. Production verification and deployment
remain separate from this offline reconciliation.

## CSV Release Integrity

CSV connectors now support `verify_snapshot: true` in connector configuration.
Each page records a SHA-256 fingerprint of the decoded CSV content. With this
option enabled, resumed pages must match the checkpoint fingerprint; a changed
release or legacy checkpoint without a fingerprint fails explicitly. Restart
the import from its first page against the new release rather than advancing an
offset into different data. Existing connectors retain their default behavior
until explicitly migrated. This is a decoded-content fingerprint, not an archive
checksum, and does not verify coherence across multiple tables or shapefiles.

The September 9 live check of the official Pinellas website returned HTTP 403.
The current manifest and download schema remain unverified. No Pinellas source
was activated and no access controls were bypassed.
