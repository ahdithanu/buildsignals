# Acquisition Radar

Acquisition Radar turns opportunity-level nearby-parcel searches into one
organization-wide acquisition queue. It answers a different question from the
opportunity panel: not "what is near this project?" but "which parcels deserve
attention across every active signal?"

## Read Model

`GET /acquisition-radar` reads canonical `parcel_acquisition_cases` together
with nearby-parcel candidates, searches, parcels, deals, permit brand matches,
and permit records. It groups candidates by canonical parcel ID, so a parcel
appearing in multiple searches is returned once while retaining every
contributing opportunity and candidate ID.

Supported filters are free-text query, two-letter state, buyer persona, review
status, assignment state, limit, and offset. All source queries use the active
organization context before aggregation.

## Ranking

The explainable 0-100 score is:

| Component | Points | Meaning |
| --- | ---: | --- |
| Best parcel fit | 45 | Highest versioned buyer-lens candidate score |
| Parcel score confidence | 15 | Completeness and reliability of ranking evidence |
| Connected signal confidence | 15 | Strongest evidence-backed retailer or development signal |
| Opportunity overlap | 15 | Repeated appearance across one, two, or three-plus opportunities |
| Team shortlist | 5 | Explicit operator interest |
| Evidence freshness | 5 | Parcel verification within 30 or 90 days |

Responses include the case ID and status, score reasons, cautions inherited
from parcel ranking, personas, assignment, outreach and follow-up timestamps,
promotion state, evidence freshness, and links to each contributing deal.
Radar scoring never changes retailer identity confidence and never treats
proximity or long ownership tenure as evidence that an owner intends to sell.

## UI Workflow

The authenticated `/acquisition-radar` workspace provides portfolio counts,
market, buyer-lens, case-status, and assignment filters; a paginated,
deduplicated priority queue; parcel and contributing-opportunity links; team
assignment; follow-up dates; outreach history; and explicit promotion. Viewers
receive the same context without mutation controls.

## Canonical Case And Provenance

`parcel_acquisition_cases` stores one organization-scoped workflow per parcel.
It prevents a parcel found around several opportunities or buyer lenses from
having conflicting assignment and outreach states. Its lifecycle is
`candidate`, `shortlisted`, `contacted`, `dismissed`, or `promoted`.

`parcel_acquisition_sources` preserves every candidate and search that caused
the parcel to enter the queue. `parcel_acquisition_activities` is the immutable
call, email, text, meeting, or note history, including actor, occurrence time,
optional follow-up, and audit entry. Promotion preserves the originating
candidate evidence and stores the resulting opportunity on the case.

Case APIs are:

- `GET /parcel-acquisition-cases/{case_id}`
- `PATCH /parcel-acquisition-cases/{case_id}`
- `POST /parcel-acquisition-cases/{case_id}/activities`

Case mutation and outreach endpoints require editor or administrator access.
The migration backfills one case and all source links for existing candidates.
Legacy candidate review and assignment calls synchronize the canonical case;
new Radar work uses the case endpoints directly.

## Scaling Path

The first version uses a database-side grouped query and paginates canonical
parcel rows. Durable workflow lives in normalized case tables while the ranking
response remains a computed read model.
When candidate volume or filter concurrency justifies it, move the same contract
behind a PostgreSQL materialized view or incrementally maintained projection
keyed by organization and parcel. Refresh that projection from candidate,
signal-confidence, review, assignment, and parcel-verification events. The API
and frontend contract can remain unchanged.

Cross-source parcel resolution is intentionally upstream of Radar. Future
parcel aliases, boundary lineage, and assessor-source merges should resolve to
one canonical parcel before ranking rather than embedding identity heuristics in
this read model.
