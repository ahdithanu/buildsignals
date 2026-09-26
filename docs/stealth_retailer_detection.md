# Stealth Retailer Detection

## Purpose

Direct brand aliases remain the strongest permit signal, but early filings often name only a shell owner or the professionals building the site. The stealth detector uses repeated project-party history from human-confirmed brand permits to identify those unnamed filings without presenting a shared contractor as proof.

Direct alias detection also evaluates the canonical applicant name using the source mapping's declared value semantics. Explicit DBA fields receive 97% base confidence and authoritative legal-entity fields receive 92%. Person and unknown fields cannot create an applicant-only brand match, though they remain available as supporting evidence and for human-confirmed historical-party patterns. This retains the same retail-context and lifecycle gates as project-name detection.
Applicant detections retain the general `exact_alias` rule, add `exact_applicant_alias`, and record an `applicant_<semantic>_source` rule so evidence consumers can distinguish the source field's meaning without a new workflow.

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
- Applicant fields declared as personal names cannot create a direct brand candidate.
- Unclassified applicant fields remain available as supporting context but cannot create a retailer candidate by themselves.
- Manual confirmation and dismissal remain mandatory before the retailer is treated as verified.

## Storage And Provenance

`brand_party_fingerprints` is an organization-scoped materialized lookup table. Each row stores the normalized and display names, party role, state, evidence count, contributing confirmed match IDs, confidence, first-seen timestamp, and last-verified timestamp. It is rebuilt from confirmed direct matches when review state changes, so retractions and dismissals remove stale support.

The resulting `PermitBrandMatch` stores `historical_parties` as the matched field, the contributing party fields, versioned rule IDs, `stealth-retailer-v1`, a human-readable explanation, confidence, and immutable first/latest raw-record references. Graph edges retain their normal relationship evidence and verification timestamps.

## API And Review Workflow

`GET /permit-brand-matches` accepts `detection_method=direct_alias|historical_party`. Responses expose the computed detection method and label historical matches as `Stealth party inference`. The existing Permit Brand Review page adds Direct and Stealth filters, a stealth count, row badges, and detailed inference rules in the evidence sheet.

### Signal freshness

Retailer-match responses expose a freshness date, age in days, tier, and label. The date uses the permit's source-reported status update when available, then the filing date, then the first detection timestamp. This prevents a routine ingestion refresh from making an old filing look new.

The review queue groups lifecycle activity into broad bands, then ranks confidence within each band. It shows `Fresh filing` (0-30 days), `Active filing` (31-90), `Aging filing` (91-180), or `Dormant filing` (over 180 days). Responses separately expose the permit's last-observed timestamp, so an old filing that remains published is not presented as a new event or confused with source health. Freshness is an operational ranking signal only: it does not reduce stored confidence, rewrite evidence, retract a relationship, or override a human confirmation.

When a full source snapshot no longer contains a permit, machine-generated candidates are retracted but human-confirmed matches remain confirmed. The permit becomes inactive, its current source relationships expire with snapshot-retirement provenance, and the response exposes `needs_reverification`. Retired permits are excluded from party-fingerprint training until they reappear, preventing stale confirmed evidence from driving new stealth inferences.

## Tradeoffs And Scaling Path

Materializing fingerprints adds a small write cost when reviewers change a decision, but keeps nationwide ingestion reads indexed and bounded. State scoping is intentionally conservative and may miss a highly distinctive national team operating in a new state.

Future iterations should add source-independent corporate shell evidence, temporal and distance decay, professional license IDs, equipment and signage vocabularies with explicit catalog provenance, reviewer decision reasons, and offline precision/recall evaluation. Field semantics can later move from mapping-level declarations to per-value classifier output when mixed source fields need finer precision. Large deployments can move rebuilds to an event-driven worker and maintain fingerprints incrementally while preserving the same service and API contracts.
