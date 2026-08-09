# Stealth Retailer Detection

## Purpose

Direct brand aliases remain the strongest permit signal, but early filings often name only a shell owner or the professionals building the site. The stealth detector uses repeated project-party history from human-confirmed brand permits to identify those unnamed filings without presenting a shared contractor as proof.

## Data Flow

1. Normal ingestion stores the immutable source record and canonical permit.
2. Direct brand aliases create reviewable permit-brand candidates.
3. When an operator confirms a direct match, the service rebuilds that brand's materialized party fingerprints.
4. Fingerprints count confirmed occurrences by normalized party name, party role, brand, organization, and state.
5. A later unnamed filing can become a candidate only when at least two distinct party roles match active fingerprints for the same brand.
6. The candidate keeps the new filing as its source evidence and projects the same evidence-backed graph relationship used by direct matches.

The initial party vocabulary is applicant, owner, developer, contractor, architect, and engineer. It is permit-neutral at the graph boundary: fingerprints reference canonical entities and roles rather than connector-specific fields.

## Confidence And Safeguards

- Each fingerprint needs at least two confirmed direct matches.
- At least two distinct party roles must support an inferred candidate.
- A party pattern associated with more than one brand is discarded as ambiguous.
- History is state-scoped to reduce nationwide professional reuse false positives.
- A single contractor, architect, owner, or shell company never surfaces a prediction.
- Inferred confidence is capped at 86%, below strong direct alias evidence.
- Inferred matches never train new fingerprints, preventing feedback loops.
- Existing retail context, stable-location, pre-approval, terminal-status, and negative-context gates still apply.
- Manual confirmation and dismissal remain mandatory before the retailer is treated as verified.

## Storage And Provenance

`brand_party_fingerprints` is an organization-scoped materialized lookup table. Each row stores the normalized and display names, party role, state, evidence count, contributing confirmed match IDs, confidence, first-seen timestamp, and last-verified timestamp. It is rebuilt from confirmed direct matches when review state changes, so retractions and dismissals remove stale support.

The resulting `PermitBrandMatch` stores `historical_parties` as the matched field, the contributing party fields, versioned rule IDs, `stealth-retailer-v1`, a human-readable explanation, confidence, and immutable first/latest raw-record references. Graph edges retain their normal relationship evidence and verification timestamps.

## API And Review Workflow

`GET /permit-brand-matches` accepts `detection_method=direct_alias|historical_party`. Responses expose the computed detection method and label historical matches as `Stealth party inference`. The existing Permit Brand Review page adds Direct and Stealth filters, a stealth count, row badges, and detailed inference rules in the evidence sheet.

## Tradeoffs And Scaling Path

Materializing fingerprints adds a small write cost when reviewers change a decision, but keeps nationwide ingestion reads indexed and bounded. State scoping is intentionally conservative and may miss a highly distinctive national team operating in a new state.

Future iterations should add source-independent corporate shell evidence, temporal and distance decay, professional license IDs, equipment and signage vocabularies with explicit catalog provenance, reviewer decision reasons, and offline precision/recall evaluation. Large deployments can move rebuilds to an event-driven worker and maintain fingerprints incrementally while preserving the same service and API contracts.
