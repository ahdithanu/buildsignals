# Mississippi MDEQ Permit Activity Search Access Request

## Source

- Candidate key: `mississippi_mdeq_permit_activity`
- Public surface: https://opcgis.deq.state.ms.us/ensearchonline/epd-activity-search.aspx
- Official landing page: https://www.mdeq.ms.gov/permits/environmental-permits-division/
- Current BuildSignals status: `legal_hold`

## Requested Scope

BuildSignals is evaluating the Mississippi Department of Environmental Quality permit activity register for a commercial development-intelligence workflow. The intended use is bounded storage of public permit activity metadata, source evidence links, and derived customer-facing intelligence about physical-economy development signals.

The requested field scope is:

- county
- agency interest number
- agency interest or facility/project name
- city and state
- permit or activity number
- permit type
- activity action
- activity date
- official detail URL

BuildSignals does not request personal contact information, private correspondence, raw document redistribution, or a replacement export of the MDEQ register.

## Questions For MDEQ

1. Which official endpoint, export, feed, or data request process should a commercial SaaS product use for recurring access to the activity register?
2. Are commercial storage, source-linked derived display, and customer-facing search allowed for the field scope above?
3. What attribution, disclaimer, retention, and redistribution requirements apply?
4. What durable identifier should be used for change detection: activity number, agency interest number, permit number, detail URL, or another key?
5. Are activity corrections, withdrawals, superseded actions, and deletions exposed through a change feed or update timestamp?
6. What request-rate, pagination, batch-size, or scheduling limits should BuildSignals follow?

## Production Acceptance Criteria

- Written permission or published terms covering commercial storage and derived display.
- Supported recurring access path with documented request limits.
- Durable source identity and source URL retained per observation.
- Application-stage versus granted/approved lifecycle can be distinguished.
- Corrections, withdrawn actions, duplicate activity rows, and deleted records have a documented reconciliation path.
- Personal contacts and non-required details are excluded.

## BuildSignals Handling

Until the criteria above are met, this source remains candidate-only. It can inform market research and outreach prioritization, but it must not be represented as production Mississippi coverage, customer-visible inventory, or verified parcel availability.
