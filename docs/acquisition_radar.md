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
status, assignment state, follow-up state, signal overlap, verified
availability state, ZIP3 market cluster, limit, and offset. All source queries
use the active organization context before aggregation.

Filter query parameters are intentionally stable enough for analyst handoff and
demo links:

| Parameter | Values | Meaning |
| --- | --- | --- |
| `q` | text | Search parcel address, parcel ID, owner, market, or connected signal text. |
| `state` | two-letter state | Limit to a market state. |
| `persona` | `developer`, `investor`, `broker`, `realtor` | Buyer lens used by the originating candidate ranking. |
| `review_status` | case status | Canonical acquisition case lifecycle. |
| `assignment` | `assigned`, `unassigned` | Whether a teammate owns the case. |
| `follow_up` | `due`, `scheduled`, `none` | Due/overdue, any scheduled, or no next action. |
| `signal_overlap` | `multi`, `single` | Cross-signal parcels versus parcels found from one signal. |
| `availability` | `verified`, `unverified` | Source-backed availability evidence versus discovery-only candidates. |
| `zip3` | three digits | Parcels whose postal code begins with the selected ZIP3 heat cluster. |
| `offset` | integer | Current page offset. |

The frontend mirrors these parameters into the URL, so a reviewer can copy a
filtered queue such as due follow-ups, promoted parcels, cross-signal
candidates, or verified availability without creating a separate saved view.

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

Verified availability is separate from the ranking score. A parcel receives the
`Verified availability` badge or matches `availability=verified` only when it
has a current source-backed parcel fact with an availability or listing fact
type, recognized available/listed status, confidence of at least 0.70, and a
source URL or excerpt. Nearby candidates without that evidence remain
`Candidate only`, even if they rank highly or sit beside a strong development
signal.

## UI Workflow

The authenticated `/acquisition-radar` workspace provides portfolio counts,
market, buyer-lens, case-status, assignment, follow-up, signal-overlap, and
verified-availability filters; clickable ZIP3 opportunity heat clusters; a
paginated, deduplicated priority queue; parcel and contributing-opportunity
links; team assignment; follow-up dates; outreach history; and explicit
promotion. Viewers receive the same context without mutation controls.

The workflow strip above the queue is the daily operating path:

| Step | Backing count or filter |
| --- | --- |
| Alert | total ranked parcels |
| Evidence | cross-signal parcels through `signal_overlap=multi` |
| Review | shortlisted parcels through `review_status=shortlisted` |
| Owner | assigned parcels through `assignment=assigned` |
| Outreach | contacted parcels through `review_status=contacted` |
| Follow-up | due or overdue parcels through `follow_up=due` |
| Saved | promoted parcels through `review_status=promoted` |

Each step is clickable and resets the queue into the corresponding work mode.
This keeps the intended workflow visible: signal evidence, project context,
nearby parcels, owner/outreach work, follow-up, then saved opportunity.

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
