# ArcGIS snapshot duplicate collapse

## Implementation and operational status

[PR #277](https://github.com/ahdithanu/buildsignals/pull/277) implements an
optional connector mechanism for publishers that import the same business record
as multiple ArcGIS rows. Distinct `OBJECTID` values identify imported rows, not
necessarily distinct permits. Existing keyset deduplication removes repeated
cursor values; it cannot remove snapshots with different cursor values.

As inspected on November 14, 2026, the PR branch contains the mechanism and five
regression tests. The checked in `arlington_tx_commercial_issued_permits` catalog
entry does **not** configure `collapse_duplicates`. This documentation update
does not change the catalog, `production_rollout.json`, `render.yaml`, tenant
source state, worker image, or schedule. Merge and production deployment remain
unapproved. No live canary or production repair is established by these changes.
Earlier Arlington admission and release receipts describe their observation dates;
they do not establish recovery from the reported duplicate identity failure.

## Configuration and applicable sources

`build_connector` accepts the following fragment inside an ArcGIS source's
`settings.connector`. This is a proposed Arlington configuration example only;
it is not applied to the catalog by this PR.

```json
{
  "collapse_duplicates": {
    "identity_fields": ["FOLDERYEAR", "FOLDERSEQUENCE", "FOLDERTYPE"],
    "recency_field": "ImportDate"
  }
}
```

Both `arcgis` and `arcgis_featureserver` factory aliases support it. Omitting the
option or its identity fields leaves collapse disabled. The factory rejects an
explicitly empty identity list. A nonempty identity list requires a recency
field. The constructor validates identity and
recency names as ArcGIS identifiers. All configured fields must be returned by
the source's `out_fields`; configuration does not add them to the query.

Use collapse only after establishing that repeated identities are snapshots of
one record and that the recency field identifies the preferred snapshot. It is
not a remedy for ambiguous permit identities or distinct events that must remain
separate. Preserve the existing source license, scope, field suppression, and
evidence requirements.

## Identity, recency, and pagination semantics

| Concern | Implemented behavior |
| --- | --- |
| Scope | Collapse runs within one fetched page, after existing keyset deduplication. No state is retained between pages, checkpoints, or runs. |
| Identity | Exact tuple of raw configured field values. There is no trimming, case folding, type coercion, or composite string normalization. |
| Incomplete identity | A missing or `None` component causes that row to pass through untouched. Empty strings count as present. Downstream validation can still reject the row. |
| Preferred snapshot | Maximum recency sort key for that tuple within the page. Equal keys select the later encountered row. |
| Recency types | `None` sorts oldest; booleans and numbers compare numerically; other values compare as strings and rank above numbers. Dates are not parsed. Require a consistent, qualified numeric timestamp representation for Arlington `ImportDate`. |
| Output order | Retained rows appear at their winning row positions in the original page, interleaved with untouched rows. This is not first appearance order for each identity. |
| Keyset cursor | Uses the final row of the page after keyset deduplication and before identity collapse. Removing that row during collapse does not reduce the cursor. |
| Offset cursor | Advances by the page length before identity collapse, not the shorter emitted length. |
| More pages | Uses the publisher's `exceededTransferLimit` flag or original raw page count equal to `page_size`. |

The helper's current comments about first seen order and incomparable recency
sorting oldest are broader than its implementation. The table above describes
the code at `f4af204`, not those comments. A latest snapshot on another page may
still be emitted separately. Downstream upserts by `source_record_id` do not
prove a global latest snapshot policy or repair previously stored data.

## Arlington qualification requirements

The issued layer's stable canonical identity remains the joined
`FOLDERYEAR`, `FOLDERSEQUENCE`, and `FOLDERTYPE` values. Do not append `OBJECTID`
or `ImportDate` to make imported snapshots look like new permits. Raw tuple
equality must be checked against the existing `join_fields` normalization before
activation. Import time is dataset refresh evidence, not the filing or issuance
date. Preserve the distinct `InDate` and `ISSUEDATE` lifecycle meanings.

Retain the existing commercial permit, certificate of occupancy, and sign scope
(`CP`, `CO`, `SI`), issued date restriction, approved confirmation stage, CC BY 4.0
attribution, field allowlist, and suppressed personal/geometry/raw export fields.
The applications companion is a separate source; this mechanism does not change
its configuration or establish its health.

Future activation must clear these separate gates in order:

1. Review the issued source catalog option and factory wiring against the actual
   returned identity fields and numeric `ImportDate` values. Check both the main
   keyset sample and the descending import date freshness probe, including their
   inherited connector configuration. Preserve all existing validation gates.
2. With approval for the catalog and rollout change, regenerate and review the
   signed rollout artifacts through the existing tooling in
   [ingestion scheduling](ingestion-scheduling.md#nationwide-rollout-manifest).
   A catalog change invalidates `catalog_fingerprint` and `manifest_digest` even
   if hostnames and wave membership stay unchanged. Review the corresponding
   `render.yaml` digest pins and actual deployed worker configuration together;
   never patch a digest alone or infer deployed state from a Blueprint.
3. With separate bounded source access authorization, run the main normalization
   canary and freshness probe. Retain timestamped receipts for complete required
   fields, unique normalized sample identities, numeric recency selection,
   freshness, approved stage, and advancing pagination. Offline tests are not a
   substitute for this gate or proof of publisher completeness.
4. Resolve cross page snapshots and reconciliation before production acceptance.
   `scripts/recurring_regions.py` compares raw provider counts before and after
   with `records_seen`. Collapse can reduce emitted counts, so a passing sample
   alone does not prove reconciliation will pass. Preserve quarantine and count
   checks; review any required accounting change separately with regression
   evidence. Do not weaken the checks to force a pass.
5. Obtain explicit approval before changing tenant activation/quarantine state,
   deploying a reviewed worker, or starting ingestion. Verify actual bounded run
   receipts, reconciliation, canonical identity/evidence linkage, and subsequent
   scheduled operation before claiming Arlington is repaired. Any stored data
   replay or repair needs its own scope and approval.

None of these operational steps is performed by this documentation change.

## Offline regression evidence and limits

`tests/test_arcgis_identity_collapse.py` contains five tests establishing numeric
latest selection within a page, passthrough of a `None` identity component,
missing recency sorting below a numeric value, one keyset checkpoint example,
and rejection of identity configuration without recency.

The current keyset example retains the maximum cursor row. It does not exercise
discarding that row. The five tests also do not cover factory option wiring,
offset collapse, equal recency ties, mixed recency types, retained row ordering,
or snapshots split across pages. These are coverage limits, not passing claims.
`tests/test_ingestion_connectors.py` provides the existing general connector and
pagination regressions; the Arlington lifecycle catalog test preserves the
stable normalized identity and application stages. Rollout tests check manifest
freshness and deployment digest pins. See the current
[handoff](../agent-handoff.md) for exact commands and dated results.
