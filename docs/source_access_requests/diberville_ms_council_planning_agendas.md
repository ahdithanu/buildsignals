# D'Iberville Council And Planning Agendas Access Request

## Source

- Candidate key: `diberville_ms_council_planning_agendas`
- Public archive: https://diberville.ms.us/council-committee-center/
- Planning department: https://diberville.ms.us/departments/planning-zoning/
- Current BuildSignals status: `legal_hold`

## Requested Scope

BuildSignals is evaluating City of D'Iberville public council, committee, and planning records for early development-intelligence signals. The intended use is bounded storage of public agenda/minute metadata, exact official source links, short attributed excerpts, and derived customer-facing signals for items such as development agreements, tax-sharing votes, rezonings, conditional uses, subdivisions, business openings, and infrastructure commitments.

The requested field scope is:

- meeting date
- meeting type
- document type
- official document URL
- agenda item or case number when present
- action type and decision when present
- project, business, or development name
- applicant or entity name when it is a public business/entity field
- address or parcel identifier when present
- zoning district and short project description

BuildSignals does not request personal phone numbers, emails, signatures, non-public records, or permission to redistribute raw agenda packets as a document repository.

## Questions For The City

1. Do the city's public-record terms allow commercial storage of agenda/minute metadata, source-linked excerpts, and derived customer-facing development intelligence?
2. Is there a supported archive feed, API, export, or document index for recurring access?
3. What attribution language and official-link requirements should be shown in customer-facing records?
4. Are revised, removed, replaced, or corrected agendas and minutes identified in the archive?
5. Should BuildSignals suppress any categories of names or documents beyond personal contact details?
6. Are there request-rate, caching, or access-window requirements for the public archive?

## Production Acceptance Criteria

- Written permission or published terms covering commercial storage and derived display.
- Supported recurring archive access or an agreed bounded retrieval schedule.
- Stable document identity using official URL, meeting date, document type, and content hash.
- Agenda proposals and final minutes/votes are stored as separate lifecycle evidence.
- Personal contact details are suppressed.
- Raw document redistribution is excluded unless explicitly allowed.

## BuildSignals Handling

Until the criteria above are met, D'Iberville remains candidate-only. News articles about BJ's Wholesale Club and I-10 corridor growth can be discovery corroboration, but the city archive must be the primary evidence before production display.
