# MDEQ enSearch Activity Register — Contract Qualification

Date: 2026-10-16. Scope: bounded, read-only inspection of the publicly available
interface to qualify whether a reliable recurring ingestion contract exists. No
query was submitted, no pagination was exercised, no restriction was bypassed,
and no source was activated. The source remains `legal_hold` and inactive.

## What was inspected

- `GET https://opcgis.deq.state.ms.us/robots.txt` → HTTP 404 (no published
  robots policy at the host root for this path).
- A single `GET https://opcgis.deq.state.ms.us/ensearchonline/epd-activity-search.aspx`
  (production-style client pinned to the one host, 20s timeout). Only the default
  rendered page and its form markup were read; the POST search was not submitted.

## Qualified contract (evidence)

- **Platform:** ASP.NET WebForms. Hidden fields `__VIEWSTATE`,
  `__VIEWSTATEGENERATOR` and `__EVENTVALIDATION` are present.
- **Search form:** `<form name="report_epd" method="post"
  action="epd-activity-search.aspx" id="report_epd">`. Query inputs are
  `uxActionType` (ALL / Receive General Permit Application (NOIs) / Issue General
  Permit Coverage / Receive Individual Permit Application / Issue Individual
  Permit), `uxStartDate`, `uxEndDate`, and `uxSubmit`. Submission is a POST
  back to the same page carrying the viewstate tokens.
- **Pagination:** none. Zero `__doPostBack` references and no pager/grid controls;
  the entire date-window result renders in one response (259 detail links in the
  default view).
- **Control totals:** none. No record/result count is shown.
- **Identity:** the only list identifier is the agency-interest id,
  `ai_info.aspx?ai=<N>`. This is an **entity** id, not a per-activity id: the same
  `ai` recurs across rows with different action text and dates, and identical rows
  are duplicated. A durable per-event identity is not available from the list view.
- **Lifecycle semantics:** application-versus-decision **is** derivable from
  `uxActionType` — "Receive ... Application/NOI" are application events and
  "Issue ... Coverage/Permit" are decision events. The action phrasing is free
  text (with a consistent "constuction" misspelling).
- **Updates/withdrawals:** no update, correction, withdrawal or tombstone signal
  is exposed; the register appears append-only by date. The MDEQ disclaimer warns
  web records may be incomplete/inaccurate and that administrative files are
  authoritative.
- **Machine interface:** no JSON/REST/export/CSV/FeatureServer endpoint is linked.

## Concrete technical blocker

A reliable recurring production interface cannot be established from this contract:

1. The search is a viewstate POST with rotating `__VIEWSTATE`/`__EVENTVALIDATION`
   tokens, requiring a fragile fetch-then-post handshake that breaks when tokens
   or server session state change.
2. No durable per-activity identity exists (the `ai` is an entity id; duplicate
   and repeated-`ai` rows), so change detection and dedupe cannot be grounded in a
   source-assigned key without fetching each detail page.
3. No pagination and no control total, so a bounded window cannot be reconciled
   against an authoritative count.
4. No update/withdrawal/deletion semantics to reconcile amended events.
5. No API/export; only scraped HTML.

Separately, commercial-reuse/derived-display rights are still unestablished.

## What this does and does not support

- **Supported now:** recording the qualified contract and the establishable
  application-versus-decision semantic as durable catalog evidence; keeping the
  source on `legal_hold` with `can_run_canary` false.
- **Not supported / not done:** no connector, probe query, schedule, field
  mapping activation, or coverage claim. Implementing a production connector would
  require a written MDEQ data-use agreement and a supported recurring export/API
  that provides durable activity identity, control totals and
  correction/withdrawal semantics.

## Verification

`OPENROUTER_API_KEY= .venv/bin/python -m pytest tests/test_ingestion_catalog.py -q`
asserts the MDEQ entry keeps `legal_hold`/`can_run_canary` false and records the
qualified blocker. The live inspection above is evidence, not a golden label.
