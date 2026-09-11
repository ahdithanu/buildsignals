# Bounded Organization Export

`GET /v1/organizations/{org_id}/export` returns one downloadable JSON document.
The unversioned compatibility route uses the same implementation. This is a
reviewed inventory of organization data, **not a complete account copy, database
backup, or claim of GDPR compliance**. It is not a deployment or publication.

## Access and Bounds

- The caller must have an active account, active organization, and current admin
  membership. The requested organization must also be the caller's active one.
  Membership removal or demotion takes effect even for an older access token.
- Successful downloads and route errors use `Cache-Control: no-store`.
- At most **10,000 exported database rows total** and **20 MiB (20,971,520 bytes)
  of UTF-8 JSON** are allowed. These are shared budgets, never per-table limits.
- The organization counts as one row. Each member item counts as two rows
  (membership and allowlisted profile), even though the profile is nested.
  Every graph, assessment, and audit row counts once. Nested snapshot contents
  count toward bytes, not as extra database rows.
- Every table read has a remaining-budget limit plus one overflow sentinel.
  Excluded graph payloads, merge snapshots, and document storage paths are not
  selected. Polymorphic link ownership checks read only IDs in bounded batches;
  they do not export or hydrate the referenced ingestion records.
- JSON keys, arrays, timestamps, and the entire manifest count toward the byte
  cap. Overflow returns `413`, never truncation, pagination, or a partial file.
  Client pagination parameters cannot override this behavior. Larger exports
  require a separately implemented background workflow.
- Query, integrity, schema, serialization, and audit-commit failures return a
  generic `500` without record details or an attachment. The successful audit
  receipt is written only after serialization and final size validation.

## Schema Version 2

Existing top-level collection names remain. A new `manifest` describes the
scope, schema version, explicit columns, per-section counts, total row count,
budget limits, redaction counts, and exclusions. Empty registered collections
are present. Collection order is stable and each collection is ordered by ID.
The timestamp describes generation time, not a point-in-time backup guarantee.

| Scope | Included Data |
| --- | --- |
| Organization | Organization metadata and current membership/profile pairs |
| Deal workflows | Deals, assumptions, outputs, contacts, outreach activities, signals, document metadata, memos, pipeline events, buy boxes, distributions |
| Audit metadata | Existing audit row ID, organization, entity type/ID, action, member actor ID, timestamp |
| Knowledge graph | Entities, aliases, source identities, links, merge metadata, relationships including historical edges, evidence metadata and excerpts |
| Saved assessments | All saved revisions and their strict V1 snapshots, review decisions/rationales, publication and withdrawal history |

The explicit table/column registry is in
`app/services/organization_export.py`. New model columns are excluded by default.
This registry does not drive or expand organization deletion.

Soft-deleted rows from registered tables are included with `deleted_at` intact.
Assessment snapshots retain their saved values, citations, confidence,
implications, source-version preconditions, and review flags; the export does
not regenerate assessments using current evidence. Legacy V1 snapshots without
source preconditions remain supported. Unknown snapshot schemas or additional
unreviewed nested fields fail closed instead of being blindly serialized.

## References and Redaction

All collection queries filter by the requested organization. Registered foreign
keys are checked against the bounded tenant-owned collections. A missing or
cross-tenant required target fails the entire export; child rows are never
silently filtered out. Nullable references remain null. Publication review IDs
must refer to the same revision as their publication.

Graph links recognize `deal`, `contact`, `document`, `signal`, `permit`, `parcel`,
and `planning`. Each known target must belong to this organization. The last
three target tables are not exported: their IDs are validated only. Unknown
record types keep their link row and type, but `record_id` is null and the
manifest increments `unsupported_graph_link_targets`.

User ownership and assessment actor/reviewer references resolve only to current
members. Other user IDs, including former members, become null and increment
`nonmember_user_references`; no extra user profiles are fetched. This does not
erase the historical revision, review, or publication row.

Merge metadata preserves retired identities; merge chains must terminate at an
owned live entity. Cycles and invalid survivor references fail. Historical
assessment entity references can use this tenant's merge history. Saved
evidence and relationship references must still resolve to owned graph rows.
If a merge or another operation removed an old referenced edge/evidence row,
this synchronous export fails closed. There is no inferred reconstruction of
deleted evidence or silent removal of citations.

**Retired identity trust boundary:** ownership of retired identifiers is taken
from the tenant-owned merge history written by the merge workflow. A defensive
lookup rejects collisions with visible foreign live entities in plain SQLite
or unrestricted database reads. Under PostgreSQL forced RLS, foreign rows are
invisible, so that negative lookup is **not proof of historical ownership**.
This export does not claim it can detect a corrupt tenant-owned merge record
that names a hidden foreign retired/live ID. Stronger guarantees require a
separate, enforced provenance contract in the merge model/workflow.

Source-system identifiers, audit entity labels, and user-authored prose are
stored tenant data, not instructions to fetch other records or external URLs.
Source metadata is not recursively expanded. The exporter is not a general
secret scanner for arbitrary user-entered text.

## Deliberate Exclusions

- Credential columns, MFA secrets/ciphertext, sessions, reset tokens, and other
  operational security records.
- Ingestion sources/configuration, runs, raw records, observations, and blobs.
- Normalized permit, parcel, planning, brand, acquisition, onboarding, and all
  other unlisted tables, even when some are tenant-owned.
- Unstructured graph entity/relationship `attributes`, graph evidence `payload`,
  and graph merge `snapshot`. These can contain unreviewed source blobs and
  references. Curated evidence excerpts and source metadata remain included.
- Document file contents and `file_path`; filenames and other registered
  metadata remain included.
- Audit `old_values`, `new_values`, and `request_id`. Removing these unstructured
  payloads and storage paths is an intentional narrowing from the former
  mapper-wide serializer, disclosed by schema version 2 and the column manifest.
- This export's own success receipt, since it is recorded after the snapshot.
  Previous receipts appear only as audit metadata. The persisted receipt records
  schema version, scopes, total row count, and exact response byte count.

## Verification

The export tests use isolated synthetic SQLite databases, never production:

```sh
REDIS_URL='' PYTHONPATH=/private/tmp/buildsignals-security-pg.clHLMu/crypto-runtime:. \
  /opt/anaconda3/bin/python -m pytest \
  tests/test_data_export.py tests/test_data_export_bounds.py \
  tests/test_data_export_graph_assessments.py tests/test_user_export_security.py \
  tests/test_data_erasure.py -q
```

Coverage includes every new table, frozen and legacy snapshots, cross-tenant
rows and references (including nested source preconditions), merge chains,
redacted actor IDs and unsupported links, authorization revocation, explicit
exclusions, bounded reads, aggregate row/byte caps, manifest overhead, failure
responses, and unchanged deletion behavior. PostgreSQL/RLS integration tests
remain separate and require an explicitly isolated test database.
