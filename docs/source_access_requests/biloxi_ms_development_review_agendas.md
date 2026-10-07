# Biloxi Development Review Agenda Access Request

## Source

- Candidate key: `biloxi_ms_development_review_agendas`
- Public meetings page: https://biloxi.ms.us/residents/public-meetings/
- Community development page: https://biloxi.ms.us/departments/community-development/
- Current BuildSignals status: `legal_hold`

## Requested Scope

BuildSignals is evaluating Biloxi development-review agenda records for early commercial and mixed-use development signals. The intended use is bounded storage of public agenda metadata, official source links, short attributed excerpts, and derived signals about proposed stores, restaurants, site work, signs, applicant activity, parcels, and development-review decisions.

The requested field scope is:

- meeting date
- appointment time
- project number
- lifecycle label such as new, resubmitted, sign-off, approved, or deferred
- project or business name
- address
- parcel number
- applicant or public business/entity name
- ward or district
- decision when present
- official agenda URL

BuildSignals does not request personal contact data, private plans, non-public correspondence, raw packet redistribution, or a replacement archive.

## Questions For The City

1. Do public meeting or public-record terms allow commercial storage of agenda metadata and derived customer-facing development intelligence?
2. Is there a supported index, feed, API, export, or recurring publication list for development-review agendas?
3. What identifier should BuildSignals treat as durable when project numbers repeat, agenda items are resubmitted, or decisions are revised?
4. Are cancellations, deferrals, approvals, withdrawals, and corrected agendas published with stable change semantics?
5. What attribution, retention, and redistribution limits apply?
6. What request-rate, caching, or access-window requirements should BuildSignals follow?

## Production Acceptance Criteria

- Written permission or published terms covering commercial storage and derived display.
- Supported recurring archive access or an agreed bounded retrieval schedule.
- Stable item identity using project number, meeting date, document URL, and content hash.
- Lifecycle stage and decision text can be separated from agenda proposal text.
- Personal contact details are suppressed.
- Raw agenda packets are not redistributed unless explicitly permitted.

## BuildSignals Handling

Until the criteria above are met, Biloxi remains candidate-only. It may be used for research prioritization, but not as production Mississippi coverage or customer-visible inventory.
