# ERCOT Monthly GIS Report — Contract Spec (interconnection queue)

Date: 2026-10-17. Scope: live verification of the public ERCOT Monthly GIS
Report contract (the interconnection / generation-interconnection queue) so a
connector can be built against a known shape. Read-only: the index was listed
and **one** latest XLSX was downloaded (a read); nothing was written to ERCOT,
no credential was used, nothing was bypassed. Evidence is live probes on
2026-10-18 UTC plus the parsed workbook. Fixtures captured from this run:
`tests/fixtures/ercot/gis_report_index_sample.json` and
`tests/fixtures/ercot/gis_report_tabs_sample.json`.

- **EMIL / product:** `PG7-200-ER`, "GIS Report" (Generation Interconnection
  Status), ERCOT MIS **reportTypeId `15933`**. Monthly cadence.

## Live access — DID IT WORK? Yes (on a corrected host)

Live access **worked**, but only after two corrections to the host assumed in
the earlier qualification:

1. **`misapp.ercot.com` is dead (NXDOMAIN).** It no longer resolves. Do not use
   it.
2. **`mis.ercot.com` is the authenticated mirror, not the public one.** It
   resolves (CNAME `mis-t.ercot.com`, 66.128.17.84) and presents a valid
   GlobalSign cert for `CN=mis.ercot.com`, but every `/misapp/GetReports.do` and
   `/misdownload/...` request **302-redirects to a CA SiteMinder SSO gateway**
   (`https://mis.ercot.com/siteminderagent/cert/.../smgetcred.scc?SMQUERYDATA=...`).
   That is the login wall — anonymous callers get the redirect, never the data.
3. **The public, anonymous host is `www.ercot.com`.** Both the index and the
   document download return HTTP 200 with no auth there.

### TLS / host caveats (exact errors)

- Python stdlib `urllib` against `https://mis.ercot.com/...` failed with
  `ssl.SSLError: [SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] ssl/tls alert handshake
  failure (_ssl.c:2559)` — this reproduces the earlier "SSL handshake failure on
  the MIS host" note. It is **the local Python's bundled OpenSSL (anaconda)**,
  not the server: `curl` to the same host completed a clean TLS 1.2 handshake
  (`ECDHE-RSA-AES256-GCM-SHA384`, cert verify ok). `www.ercot.com` served over
  HTTP/2 with no handshake issue. Mitigation for a connector: fetch via a
  modern TLS stack (`requests`/`httpx`/`curl`), or a Python linked against
  current OpenSSL; do not rely on the anaconda-bundled interpreter.
- `www.ercot.com` is fronted by **Imperva/Incapsula** (`x-cdn: Imperva`, sets
  `visid_incap_*` / `incap_ses_*` cookies). Send a normal browser-like
  `User-Agent`; a bot-detector challenge is possible under heavy automation.

## The list → download recipe (public, no auth)

1. **Index (list):**
   `GET https://www.ercot.com/misapp/GetReports.do?reportTypeId=15933`
   - Returns **HTML** (`text/html;charset=ISO-8859-1`), ~100 KB, *not* the XML
     listing some other MIS reports expose. `cache-control: max-age=60`.
   - Each report is a table row: the **filename** sits in a
     `<td class='labelOptional_ind'>…</td>` cell, and the download link is an
     `<a href='…'>xlsx</a>` in the "Other" column.
2. **Download URL pattern (confirmed real):**
   `https://www.ercot.com/misdownload/servlets/mirDownload?mimic_duns=000000000&doclookupId=<id>`
   - `<id>` = `doclookupId`, a durable integer per posted document
     (e.g. `1281327706`). Response is the XLSX directly with
     `content-disposition: attachment; filename=<the RPT filename>`.
   - (The `misdownload/servlets/mirDownload?doclookupId=<id>` shape from the task
     is correct; the real query string also carries `mimic_duns=000000000`.)

### Filename convention & picking the latest month

Filenames encode everything needed:
`RPT.00015933.0000000000000000.<YYYYMMDD postDate>.<HHMMSSmmm>.<Descriptive_Month_Year>.xlsx`
e.g. `RPT.00015933.0000000000000000.20261001.160829144.GIS_Report_September2026.xlsx`.

- **reportTypeId 15933 mixes two document families** in one listing:
  `GIS_Report_*` (the interconnection queue — what we want) and
  `Co-located_Battery_Identification_Report_*`. **Filter to descriptive segment
  starting `GIS_Report`.**
- Report-month naming is inconsistent across years (`GIS_Report_September2026`,
  `GIS_Report_April_2024`, `GIS_Report_Jun2026`, plus `_revised` / `_Corrected`
  / `_CORRECTION` variants). Do **not** parse the month from the name for
  "latest". Instead pick the row with the greatest **`postDate`** (the
  `YYYYMMDD` segment), tie-broken by greatest `doclookupId`. Prefer a
  `_revised`/`_Corrected` row when it shares the latest postDate.
- Latest at capture: `GIS_Report_September2026`, postDate `20261001`,
  `doclookupId=1281327706` (673 KB XLSX). Monthly files are posted ~1st of the
  following month.

## Workbook shape (parsed with stdlib zipfile + xml.etree only)

14 sheets. The two queue tabs are **`Project Details - Large Gen`** and
**`Project Details - Small Gen`** (others: Contents, Disclaimer and References,
Acronyms, Summary, GIM Trends + `data_GIM Trends_1..4`, Commissioning Update,
Inactive Projects, Cancellation Update).

Each tab has banner/NOTES rows first, then a header, then a secondary label row,
then data. **Find the header row dynamically** as the first row whose column A
== `INR`; data rows are the following rows whose column A is populated and not
the `Change indicators…` label row.

### `Project Details - Large Gen` (header at row 23, 27 columns)

`INR`, `Project Name`, `GIM Study Phase`, `Interconnecting Entity`,
`POI Location`, `County`, `CDR Reporting Zone`, `Projected COD`, `Fuel`,
`Technology`, `Capacity (MW)`, `Screening Study Started`,
`Screening Study Complete`, `FIS Requested`, `FIS Approved`,
`Economic Study Required`, `IA Signed`, `Air Permit`, `GHG Permit`,
`Water Availability`, `Meets Planning`, `Meets All Planning`,
`Construction Start`, `Construction End`, `Approved for Energization`,
`Approved for Synchronization`, `Comment`.

### `Project Details - Small Gen` (header at row 12, 17 columns)

`INR`, `Project Name`, `Model Ready Date`, `Interconnecting Entity`,
`POI Location`, `County`, `CDR Reporting Zone`, `Projected COD`, `Fuel`,
`Technology`, `Capacity (MW)`, `Change indicators: Proj Name, MW`, `IA Signed`,
`Financial Security`, `Approved for Energization`, `Approved for
Synchronization`, `Comment`.

### Field mapping (DealSignal semantics)

- **Durable identity (INR):** column `INR` — the per-request interconnection
  number, e.g. `15INR0064b`, `22INR0596`. Stable across monthly reports; use as
  the primary key. (`b` / letter suffixes and repowering variants occur.)
- **Project name:** `Project Name`. **County:** `County` (plus `POI Location`,
  `CDR Reporting Zone` for geography). **Fuel/tech:** `Fuel` (coded: `WIN`,
  `SOL`, `OTH`, …) + `Technology` (`WT`, `BA` battery, …).
- **Capacity MW:** `Capacity (MW)` (net-change basis for repowering; may be 0 or
  negative — see tab NOTES).
- **Date cells are Excel 1900-system serials** (epoch 1899-12-30), **not**
  strings. e.g. `46359 → 2026-12-03`, `44805 → 2022-09-01`. Decode:
  `date(1899,12,30) + timedelta(days=int(n))`.

### Status → stage (application vs decision / in-service)

There is no single "status" string; stage is derived from the milestone columns,
each of which is a **date** (when reached) or a word like `Yes` / `Not Required`.

- **Application side (in queue, pre-decision):** INR assigned +
  `GIM Study Phase` text (Large Gen, e.g. "SS Completed, FIS Completed, IA") /
  `Model Ready Date` (Small Gen), through `Screening Study Started/Complete`,
  `FIS Requested`, `FIS Approved`, `IA Signed`. These are the *application /
  study* progression.
- **Decision / approaching in-service:** `Approved for Energization` and
  `Approved for Synchronization` dates are the operator's go-ahead decisions;
  `Construction Start`/`Construction End` (Large Gen) and the permit columns
  (`Air Permit`, `GHG Permit`, `Water Availability`) mark build readiness.
- **Projected in-service:** `Projected COD` (commercial operation date, a
  future-dated serial). Treat `Projected COD` as the forecast in-service and the
  `Approved for Synchronization` date (once present) as the realized/near-term
  decision milestone. The `GIM Study Phase` free-text on Large Gen is the most
  compact single-column stage label.

## Cadence, rights, blockers

- **Update cadence:** monthly; a new `GIS_Report_<Month><Year>.xlsx` posts
  ~1st–3rd of the following month; occasional same-month `_revised`/`_Corrected`
  reposts.
- **Rights:** ERCOT MIS public reports are freely downloadable, public-domain
  reuse (no login, no redistribution gate on `www.ercot.com`). Keep ERCOT
  attribution; re-check the site terms before redistribution.
- **Concrete blockers / cautions:**
  - **BLOCKER (host):** `misapp.ercot.com` is gone; `mis.ercot.com` is
    SiteMinder-gated (302 to `smgetcred.scc`). **Only `www.ercot.com` is
    anonymous.** A connector pointed at either old host will silently fail or
    collect a login page.
  - **CAUTION (TLS):** anaconda-bundled Python throws
    `SSLV3_ALERT_HANDSHAKE_FAILURE` against ERCOT; use a modern TLS stack.
  - **CAUTION (CDN):** Imperva front — browser-like `User-Agent`, be ready for a
    bot challenge under volume.
  - **CAUTION (parsing):** two document families share reportTypeId 15933;
    header row position differs per tab and spans two rows; dates are serials.
