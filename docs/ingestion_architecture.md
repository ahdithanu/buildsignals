# Permit Ingestion Architecture

## Current Flow

```mermaid
flowchart LR
  A["Official source"] --> B["Connector"]
  B --> C["Raw source record"]
  C --> D["Canonical permit record"]
  D --> E["Permit events"]
  D --> F["Brand detection"]
  D --> G["Graph projection"]
  E --> H["Source health"]
  E --> I["Permit detail page"]
  F --> I
  G --> J["Opportunity graph context"]
  J --> K["Opportunity detail page"]
  I --> K
```

In the current product, the graph context already shows up on the opportunity
detail page, permit detail now exposes source evidence and lifecycle events,
and the source-health view opens into individual filings for troubleshooting.
The current flow is still mostly record-centric: each source lands as a permit
or signal first, then downstream jobs enrich it.

## Proposed Direction

```mermaid
flowchart LR
  A["Official source"] --> B["Connector"]
  B --> C["Raw evidence"]
  C --> D["Canonical permit or parcel record"]
  D --> E["Lifecycle classifier"]
  D --> F["Entity resolution"]
  D --> G["Evidence-backed relationships"]
  F --> H["Shared knowledge graph"]
  G --> H
  E --> H
  H --> I["Pre-approval retailer signals"]
  H --> J["Approved confirmation signals"]
  H --> K["Nearby parcel discovery"]
  H --> L["Permit detail page"]
  H --> M["Opportunity detail page"]
  H --> N["Landing / source-health coverage panels"]
  I --> L
  J --> L
  K --> M
  I --> M
  J --> M
```

## What Changes

The current system already preserves source evidence, permit lifecycle state,
brand matches, and opportunity graph context. The proposed path makes the graph
layer the shared backbone for permits, parcels, organizations, and prospects so
new jurisdictions can be onboarded without teaching each one custom permit
logic.

That means:

- keep raw evidence attached to every relationship
- resolve duplicate entities through names, addresses, source ids, and aliases
- classify pre-approval and approved records separately
- attach nearby parcels and buyer lenses as reusable graph context
- surface the same evidence-backed context on the opportunity and permit detail pages

## Where It Lands In The App

The current landing surface already points into this workflow:

- The dashboard is the first stop and surfaces pre-approval and approved retail
  queues, graph coverage, nearby parcel coverage, and source-health status.
- The opportunity detail page is the working surface and now embeds retail
  permit signals, nearby parcel context, and the graph context panel together.
- The graph context panel can jump back into parcel review, so the same
  evidence-backed entities flow from the dashboard into the opportunity page
  without a separate navigation layer.

## Current Versus Proposed

```mermaid
flowchart LR
  subgraph A["Current"]
    A1["Permit feed or filing"] --> A2["Canonical permit record"]
    A2 --> A3["Brand / opportunity enrichment"]
    A2 --> A4["Opportunity graph context"]
    A4 --> A5["Opportunity detail page"]
  end

  subgraph B["Proposed"]
    B1["Permit feed, parcel feed, assessor feed, CRM, broker intel"] --> B2["Raw evidence + normalization"]
    B2 --> B3["Entity resolution"]
    B3 --> B4["Shared knowledge graph"]
    B4 --> B5["Relationships with provenance"]
    B4 --> B6["Pre-approval and approved signals"]
    B4 --> B7["Nearby parcel discovery"]
    B4 --> B8["Opportunity detail page"]
    B4 --> B9["Landing page coverage"]
  end
```

## Scaling Tradeoffs

- Start with graph writes that are cheap and deterministic.
- Add richer entity resolution only when the source quality supports it.
- Keep permit-specific rules in source adapters or classifiers, not in the graph
  layer itself.
- Prefer a narrow set of high-confidence relationships over a noisy universal
  graph.

## Freshness Contract

Every production permit source declares a positive `freshness_sla_hours`. A
source with a publisher timestamp also classifies that field as one of:

- `record_updated_at`: the publisher says an individual record changed
- `dataset_refreshed_at`: the publisher says the dataset or extract refreshed
- `filing_event_at`: the timestamp is a filing, opening, or publication event

Sources without a trustworthy publisher timestamp use collection time for
operational health and report `ingestion_observed_at` through the health API.
Only record-update and dataset-refresh clocks can degrade source health. Filing
events remain visible as activity context, because a quiet jurisdiction is not
necessarily a broken source. The API retains `source_watermark_at` and
`source_lag_hours` for compatibility,
but also returns `freshness_semantics`, `freshness_label`, and the effective SLA
so operators can interpret those values correctly. Evidence panels call the
immutable raw-row timestamp `Snapshot captured`; it is not presented as proof
that the publisher re-observed an unchanged record.

This contract deliberately stays in source configuration rather than the graph
layer. Graph relationships consume evidence timestamps but do not infer what a
publisher's field means.
