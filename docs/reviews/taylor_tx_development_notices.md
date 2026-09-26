# Taylor Development Notices Promotion Review

## Status

Approved by the Build Signals owner on August 14, 2026 for the narrow production
rights and data-minimization scope below. The machine-readable approval is in
`docs/reviews/taylor_tx_development_notices_approval.json`.

## Source

- Candidate: `taylor_tx_development_notices`
- Official feed: `https://www.taylortx.gov/RSSFeed.aspx?ModID=1&CID=31`
- Official page: `https://www.taylortx.gov/1386/Development-News-and-Notices`
- Publisher: City of Taylor, Texas
- Published purpose: public before-action development notices and alert
  subscriptions

## Technical Review

The feed was empty during the August 1, 2026 audit. On August 14 it returned a
current item published August 7: PZ 2026-2715, an employment-center plan public
hearing notice for Project Mustang. A bounded no-write canary fetched one row,
validated one row as `pre_approval`, and reported zero errors.

The proposed source identity is the stable RSS `guid`. The PZ application
number is extracted from the title. `published_at` is filing/activity context,
not a publisher data-refresh watermark. RSS-window disappearance must not be
interpreted as withdrawal, denial, or deletion.

## Proposed Production Scope

Allow only:

- `guid`
- `title`
- `link`
- `published_at`
- short RSS `description`

Map those fields to source identity, application number, project name,
description, filing time, and official evidence URL. Default all records to the
exact source category's `pre_approval` stage and preserve the source title.

Suppress and do not fetch:

- individual names, email addresses, phone numbers, or mailing addresses
- linked application packets, staff reports, plans, and document bodies
- enclosures and attachment contents
- raw feed replacement downloads or customer-facing raw exports

Recommended export policy:
`derived_development_notice_context_only_no_raw_document_export`.

## Rights Review

The City intentionally publishes the category as an official RSS feed and
offers public alert subscriptions. That supports a narrow syndication use for
attributed notice metadata and official links, similar to the reviewed Everett
notice source. Before promotion, an authorized reviewer must still explicitly
approve commercial storage and customer-facing derived intelligence under the
minimized scope above.

## Approval Record

The Build Signals owner approved both statements on August 14, 2026:

1. Build Signals may store and process the official Taylor RSS notice metadata
   for commercial, customer-facing derived development intelligence with City
   attribution and no raw-feed replacement export.
2. The allowlist and suppression policy above are sufficient for production
   data minimization.
