# Build Signals Knowledge Graph

## Purpose

The graph layer connects opportunity records to reusable real estate intelligence entities: permits, parcels, properties, developers, owners, general contractors, architects, engineers, cities, lenders, brokers, and source records. It is intentionally generic so permit feeds, county records, CRM imports, broker emails, and future enrichment jobs can all write to the same graph without embedding source-specific logic in the core model.

## Minimal Schema

### `graph_entities`

Canonical nodes scoped by `organization_id`.

Important fields:

- `entity_type`: typed node, for example `property`, `developer`, `owner`, `permit`, `parcel`, `broker`.
- `display_name`: human-readable label.
- `normalized_name` and `normalized_address`: deterministic resolution keys.
- `source_system` and `source_id`: optional external identity.
- `confidence`: confidence in the entity itself.
- `created_at`, `updated_at`, `last_verified_at`: lifecycle and freshness.
- `attributes`: source-neutral JSON for sparse properties.

### `graph_entity_aliases`

Alternate names and source ids for an entity. This lets the graph keep "ACME Dev LLC", "Acme Development", and a feed-specific owner name tied to the same canonical entity.

### `graph_entity_source_identities`

First-class external identities attached to a canonical entity. Unlike the
single primary `source_system` / `source_id` pair on `graph_entities`, this
table preserves every registry, permit-feed, assessor, CRM, or enrichment ID
that resolves to the node. Resolution checks these identities before name or
address matching, so a previously merged source record cannot recreate its
retired duplicate.

### `graph_entity_merges`

Immutable provenance for reviewer-approved deduplication. Each row records the
survivor, retired entity ID and display name, entity type, review reason,
timestamp, and a JSON snapshot of the retired node's fields, aliases, source
identities, record links, and relationship IDs.

### `graph_entity_links`

Bridge table from graph nodes to app records. Today it links `record_type='deal'` to the property entity for an opportunity. Future importers can link `permit`, `contact`, `document`, or other records without changing the graph model.

### `graph_relationships`

Directed typed edges between entities.

Every relationship stores:

- `relationship_type`
- `source_entity_id`
- `target_entity_id`
- `confidence`
- `source_system` and `source_id`
- `created_at`
- `updated_at`
- `last_verified_at`
- `verification_due_at`, indexed with organization and current-state fields for scalable review queues
- optional `attributes`

### `graph_relationship_evidence`

Evidence rows attached to a relationship. Each row stores source system/id/url, evidence type, excerpt, observed timestamp, payload JSON, confidence, and creation timestamp.

The graph evidence API also returns a lightweight related-entity summary and a
short evidence preview for reviewer-facing surfaces, so UI panels can render
the actual node being connected instead of only the relationship type.

## Entity Resolution

Resolution is implemented in `app/services/graph_service.py` and runs in this order:

1. Exact match on `entity_type + source_system + source_id`.
2. Exact first-class source identity match.
3. Exact alias match by source identity.
4. Exact normalized name match, optionally constrained by normalized address.
5. Exact normalized alias match.
6. Conservative fuzzy match by normalized name, with address support for properties and parcels.

Structured source attributes are also folded into the same resolution pass
when they look like alternate names or identity strings. That includes common
generic fields such as `aliases`, `legal_name`, `company_name`, `display_name`,
`alternate_names`, and similar name-bearing payload fields. For address-aware
entities, unit markers are normalized so `Suite 200`, `Unit 200`, and `#200`
can resolve to the same canonical address string.

Normalization removes punctuation, common company suffixes, and common address expansions. The resolver is deliberately cautious: false merges are more expensive than duplicate nodes in an enterprise intelligence product.

## API Surface

- `POST /graph/entities`: create or resolve an entity.
- `GET /graph/entities/{entity_id}`: entity detail, aliases, links, related entities.
- `GET /graph/entities/{entity_id}/related`: adjacent graph entities.
- `GET /graph/entities/{entity_id}/merge-candidates`: likely same-type duplicates for human review.
- `POST /graph/entities/{entity_id}/merge`: retire a reviewed duplicate into the selected canonical entity while preserving provenance.
- `POST /graph/relationships`: create/update a relationship with evidence.
- `GET /graph/relationships/{relationship_id}`: relationship detail with source
  and target entities plus full evidence.
- `GET /graph/relationships/review-queue`: current relationships that are due or overdue for evidence review.
- `POST /graph/relationships/{relationship_id}/verify`: renew a relationship with required source evidence, a review reason, confidence, and the next verification interval.
- `GET /graph/paths`: find short relationship paths between two entities.
- `GET /opportunities/{opportunity_id}/graph-context`: opportunity context grouped by role.
- `GET /deals/{deal_id}/graph-context`: alias used by the current frontend.

## Opportunity Context

When a deal is created or updated, the backend creates or refreshes a property entity and links it to the deal. The frontend panel reads graph context for that linked property and groups adjacent entities into developers, parcels, owners, contractors, architects, engineers, permits, cities, lenders, brokers, and other.

Two important projected sources now feed that context:

- Permit-brand matches create `company` nodes for retailer and chain names, then relate them back to the opportunity property with evidence-backed `related_to` edges.
- Deal contacts with broker, lender, owner, developer, architect, engineer, or contractor roles are projected into the graph as typed entities, with evidence attached to the relationship.
- Approved opening signals and pre-approval signals share the same graph
  vocabulary, so the reviewer sees both early-warning chain movement and
  post-approval openings in one consistent opportunity context.
- Confirmed opportunity creation and confirmation now seed nearby parcel
  searches when a geocoded signal is available, and the API returns that
  parcel context immediately instead of hiding it behind a second user action.
- Human-confirmed direct brand matches also build state-scoped project-party
  fingerprints. Two independent repeated parties can surface an unnamed filing
  as a conservative stealth-retailer candidate; the scoring and safeguards are
  documented in `docs/stealth_retailer_detection.md`.

The graph context route also backfills existing deal contacts on read, so older opportunities pick up contact-derived graph nodes even if the contact predates the projection logic.

Official parcel split, merge, replat, and correction events are stored in a
separate temporal lineage model and projected into the graph once both sides
resolve to canonical parcel records. The graph edge remains generic
`related_to`; `lineage_event_type`, event identity, predecessor/successor parcel
IDs, confidence, timestamps, and raw-record evidence preserve its precise
meaning. Keeping lineage as its own event model supports one-to-many and
many-to-one changes without making the generic graph schema parcel-specific.

Entity review now also exposes a merge-candidate endpoint for cautious deduping.
It scores same-type entities by normalized name, aliases, shared addresses, and
location signals, then surfaces the top likely duplicates in the entity detail
view. That keeps review human-driven while still giving operators a fast path
for cleanup.

Editors and admins can complete that review from the entity page. A merge is a
single transaction: aliases, source identities, record links, relationships,
and relationship evidence move to the survivor; equivalent edges collapse and
combine their evidence; direct survivor-to-duplicate edges are removed; entity
attributes are combined with survivor values taking precedence; and the
retired entity is deleted only after its merge snapshot is durable. Cross-type
and self-merges are rejected. The audit log records the review reason and merge
provenance ID.

## Relationship Verification

Relationship freshness is explicit rather than inferred from a page view. New
edges receive a default 90-day verification window. Editors and admins can
renew an edge with a source-specific interval from one day to ten years, but a
renewal is rejected unless it includes new source evidence and a review reason.
The service records the evidence, updates confidence when supplied, advances
`last_verified_at` and `verification_due_at`, and writes an audit event.

Responses classify current edges as `fresh`, `due` (within 14 days), or
`stale`; expired historical edges remain `historical`. The opportunity graph
panel exposes due and stale warnings, while the indexed review-queue endpoint
orders overdue relationships before lower-confidence due relationships. This
policy is generic: source adapters choose an appropriate interval without the
graph layer knowing whether the evidence came from a permit, assessor, filing,
CRM record, or another source.

## Tradeoffs

This implementation keeps graph traversal in the service layer using bounded breadth-first search. That keeps the first version portable across SQLite tests and Postgres production, and it avoids adding a graph database before query patterns are proven.

The cost is that deep traversal and global graph analytics are not optimized yet. The API is shaped so those internals can later move to recursive SQL, materialized graph projections, pgvector-assisted entity resolution, or a dedicated graph engine.

## Scaling Path

Near-term improvements:

- Add importer-specific services for permit feeds, assessor records, and broker intelligence.
- Store geocoded parcel/property keys and normalized APNs.
- Add relationship merge jobs for duplicate edges with complementary evidence.
- Add scheduled verification assignments and reviewer ownership on top of the indexed queue.
- Materialize current parcel ancestry and descendant closures if lineage path
  traffic outgrows bounded graph traversal.

Mid-term improvements:

- Add Postgres recursive CTE queries for paths.
- Add trigram indexes or vector embeddings for higher-quality entity resolution.
- Add batch review queues and reversible adjudication for low-confidence merges.
- Add graph snapshots or materialized neighborhood tables for high-traffic opportunity pages.

Long-term improvements:

- Move heavy graph analytics to a specialized graph store if query patterns justify it.
- Add temporal relationship validity windows.
- Add organization-specific resolution policies and source reliability weighting.
