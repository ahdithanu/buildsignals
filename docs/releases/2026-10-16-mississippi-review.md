# Mississippi Source Review

Owner authorized continued source review on 2026-10-16. This does not establish
agency permission or a legal opinion. Missing affirmative license language alone
is not proof that extracting public factual metadata is prohibited.

## D'Iberville: Express Restriction

The live [Terms of Service](https://diberville.ms.us/terms-of-service/) returned
HTTP 200 and explicitly restrict commercial use and copying without written
permission. This is stronger evidence than the previously recorded copyright
footer. Production remains off. Obtain written permission or qualify a separately
authorized official channel; do not bypass the restriction. The site's robots
file also requests a 20-second crawl delay.

## Biloxi: Technical Qualification

Reviewed the official [public meetings page](https://biloxi.ms.us/residents/public-meetings/),
[privacy policy](https://biloxi.ms.us/privacy-policy/) and
[DRC archive](https://biloxi.ms.us/category/agendas-drc/). Those pages did not
identify an express commercial-reuse prohibition; no affirmative license grant
or broader legal clearance is claimed. Robots excludes wp-admin, not this archive.

`scripts/qualify_biloxi.py --live` is a bounded, non-publishing check: at most
four HTML pages, three PDFs, two MB per response, 25 items/document and 75 total.
It reuses the existing document extractor/item segmenter, preserves PDF hashes,
page references, meeting dates and official case IDs, and suppresses individual
representative lines in its source-specific parsing rules. It writes no database
rows, enables no scheduler and calls no LLM.

Observed official documents: DRC-10-21-26.pdf, DRC-10-14-26.pdf, DRC-09-30-26.pdf
under `https://biloxi.ms.us/agendas/DRC/2026/`.

- Ten extracted project items; no missing required project/address/evidence fields.
- Seven single-format parcel references, **not verified parcel matches**.
- Two compound references retained unresolved; one parcel reference unknown.
- Intersection addresses retained without inventing a street number.
- Future meeting dates retained as planned hearings, not future filing timestamps.
- These are proposed development-review items, not permit submissions, approvals,
  construction starts, verified businesses opening, or land for sale.

Initial strict decoding failed on mixed Windows-1252 bytes in the UTF-8 archive.
A source-specific qualification client preserves valid UTF-8 and decodes only
legacy escaped bytes; the production connector has not been changed. Initial
field checks also caught compound references, an intersection and a railroad
right-of-way project. Tests now cover these distinctions and multiline contact
suppression. Live rerun passed after those changes.

Remaining implementation before production: admit the bounded source configuration
through normal ingestion, provide tested source-specific decoding in the deployed
worker, validate additional document layouts/contact suppression, and record
revision/deletion semantics and unavailable provider totals honestly. No new
Mississippi production source or coverage is claimed by this qualification.

## MDEQ: No Prohibition Established, Contract Unqualified

The official [EPD page](https://www.mdeq.ms.gov/permits/environmental-permits-division/)
links permit applications/public notices to enSearch. Its
[disclaimer](https://www.mdeq.ms.gov/disclaimer/) warns about incomplete/inaccurate
web records and identifies administrative files as authoritative. The reviewed
disclaimer did not establish a commercial-use ban, but is not a license grant.
The ASP.NET query/pagination contract, durable event IDs, source totals and
corrections/withdrawals remain unqualified. Production remains off; do not call
this a confirmed legal prohibition.

## Verification

`OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/test_biloxi_qualification.py tests/test_planning_document_connector.py tests/test_planning_items.py -q`

Result: 15 passed. Synthetic unit cases are not golden source labels. Live
qualification performed separately against the three documents above. Existing
four-state production schedules were not changed during this review.

Expanded check including `tests/test_ingestion_catalog.py` and
`tests/test_recurring_regions.py`: 219 passed in 3.63s. Ruff and `git diff --check`
passed. No full-suite result is claimed.
