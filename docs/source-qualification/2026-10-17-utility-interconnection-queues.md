# Grid Interconnection Queues — Source Qualification (PJM, ERCOT)

Date: 2026-10-17. Scope: bounded, read-only inspection to qualify whether a
reliable, recurring, rights-clean **public machine interface** exists for grid
interconnection / generation queue data relevant to the power-constraint thesis
(PJM serves Northern Virginia / data-center alley; ERCOT serves Dallas–Fort
Worth). Mirrors the MDEQ method: establish the contract or report a concrete
blocker. **No connector was built, no queue export was downloaded, no credential
was obtained, and nothing was bypassed.** Evidence is the published API guide,
the operators' data-product / terms pages, and a few single read-only probes.
Third-party endpoint claims are flagged as such.

---

## PJM

PJM runs two distinct public data surfaces. The interconnection queue is **not**
on the documented one.

### A. Data Miner 2 API — documented, but no queue feed + redistribution ban

- **Base endpoint:** `https://api.pjm.com/api/v1/<feed>` (production);
  `https://api-train.pjm.com` is the training mirror. Azure APIM gateway.
- **Auth / key:** free API key, but **registration required** — a PJM Tools
  account (`accountmanager.pjm.com`) then a subscription at
  `https://apiportal.pjm.com/`. Key is passed as the
  `Ocp-Apim-Subscription-Key` request header.
- **Format:** JSON (default), `format=csv`, or XML; responses gzip-encoded.
- **Pagination / bounding:** `rowCount` (**max 50,000**, required when other
  params are set) + one-based `startRow`; `sort`/`order`; date-window params
  (`datetime_beginning_ept`, etc.).
- **Control total:** yes — with `download=true` the total is returned in the
  `X-TotalRows` HTTP header (also `totalRows` in the body otherwise).
- **Rate limits:** per the portal, 600 data connections/min for PJM Members,
  **6/min for non-members**.
- **Queue coverage:** **none.** The feed catalogue in the API guide is
  operational/market data only (LMPs, `gen_by_fuel`, `solar_gen`, `wind_gen`,
  outages, reserves, billing determinants, etc.). There is **no**
  interconnection / new-services-queue / generation-queue feed. ~160 feeds were
  scanned; zero match queue/interconnection/new-service.
- **Terms (hard blocker):** the guide states that data in or **derived from**
  Data Miner is "for internal use only and redistribution ... is strictly
  prohibited without a PJM membership." That is a direct commercial-reuse /
  redistribution bar for any Data Miner feed.

### B. Planning "New Services Queue" export — the actual queue, but semi-public

- **Endpoint (third-party-sourced, not PJM-documented):**
  `https://services.pjm.com/PJMPlanningApi/api/Queue/ExportToXls`. This is the
  backend the public interconnection-queues page calls client-side. A direct
  read-only GET returned **HTTP 405 Method Not Allowed** (endpoint exists but
  expects a specific method/body, consistent with a filtered POST), and the
  page supplies the APIM subscription key client-side rather than per-user.
- **Format / volume:** XLSX; reported ~9.3k rows covering full queue history
  since 1997 (per a third-party scraper's docs — unverified against PJM).
- **Identity:** source-assigned **Queue Number / project (GI serial) id** — a
  durable per-request key, unlike MDEQ.
- **Application vs decision:** derivable from the request's **status**
  (e.g. Active / Under Construction / In Service / Withdrawn) plus request type,
  not a separate event stream.
- **Cadence:** reported ~daily refresh (third-party).
- **Rights:** governed by PJM.com legal terms (not confirmed here); given the
  Data Miner redistribution ban above, commercial redistribution of PJM queue
  data should be treated as **unestablished and likely restricted** until a
  written PJM position or membership is confirmed.

### PJM recommendation — (c) concrete blocker (with a narrow (b) path)

No reliable, documented, rights-clean public machine interface for the PJM queue
exists today:
1. The **documented** API (Data Miner 2) does **not** expose the interconnection
   queue at all, and its terms forbid redistribution without membership.
2. The queue **is** reachable only via an **undocumented** Planning APIM
   endpoint that depends on a rotating subscription key embedded in the public
   page (not issued to us) — a fragile, unsupported contract, and the 405 on a
   plain request confirms a non-trivial request shape.
3. Commercial-reuse rights are unestablished and the one explicit PJM statement
   points the wrong way.
Narrow viable-with-credential path (b): obtain a PJM Tools account and confirm
in writing whether queue data is offered under a redistribution-permitting
licence; if pursued, adapter fit is a **new connector** (XLSX fetch), not
`json_array`/`csv`.

---

## ERCOT

ERCOT is the cleaner of the two. Two public surfaces exist; the GIS report is
reliably reachable via the MIS report list.

### A. Monthly Generator Interconnection Status (GIS) Report — primary

- **Product:** EMIL id **PG7-200-ER**, Report Type Id **15933**
  ("Monthly GIS Report"). Data-product page lists **Audience: Public**,
  **Security Classification: Public**, **Channel: Public, EWS**.
- **Download mechanism:** the public MIS report list,
  `https://misapp.ercot.com/misapp/GetReports.do?reportTypeId=15933` (returns an
  XML index of documents) → per-document download via the `mirDownload` servlet.
  The data-product page itself shows "MIS Posting Location: N/A" and an empty
  Available Files list, so the GetReports list is the resolution point. The
  individual file URL **changes each month** (new document id), but the
  `reportTypeId=15933` list is **stable** and resolvable on each run — exactly
  what a recurring fetch needs.
- **Format:** XLSX, with "Large Gen" and "Small Gen" tabs (reported ~1.85k
  rows). Since 2026-03 the series also includes a Transmission Interconnection
  Costs Report.
- **Identity:** source-assigned **INR** (e.g. `24INR0080` = year prefix +
  sequence) — a durable per-request key.
- **Application vs decision:** derivable from the per-row **status** and
  interconnection-agreement / COD milestone columns (historically: unit/project
  name, county, region, fuel, MW, status, projected COD), not a separate stream.
- **Cadence:** `Generation Frequency: Chron – Monthly` (EMIL last updated
  2026-02-09; first run 2017-02-01).
- **Control total:** none per se; the GetReports XML index is the bound, and row
  counts come from the file itself.
- **Technical note / uncertainty:** a direct read-only probe of the MIS host
  over TLS failed with an SSL handshake error (`SSLV3_ALERT_HANDSHAKE_FAILURE`)
  on one hostname variant, and `misapp.ercot.com` vs `mis.ercot.com` resolution
  differs; the exact host + TLS profile must be validated when a fetch is
  actually implemented. This is a config detail, not a rights blocker.

### B. ERCOT Public API (`api.ercot.com`) — exists, but GIS not clearly exposed

- **Base:** `https://api.ercot.com/api/public-reports`. JSON (HAL
  `_embedded`/`_links`); report files carry `fileType` zip/csv/xml.
- **Auth:** `Ocp-Apim-Subscription-Key` header **plus** a Bearer ID token
  (OAuth/B2C); **free registration** required; bot-created accounts barred by
  API terms. Listing/pagination endpoints documented as "Coming Soon."
- **GIS coverage:** not evidenced — the PG7-200-ER data-product page lists no
  API artifact id and no posting location, so the queue is **not confirmed** on
  the public-reports API. The MIS GetReports path (A) is the dependable route.

### ERCOT rights (rights-clean)

Website User Agreement, Clause 5: publicly available contents "may be used,
reproduced, and redistributed, provided that the contents are not modified," and
**raw data** "may be used, reproduced, and redistributed in compilations,
charts, and analyses" (expressly without maintaining notices). Commercial use is
not restricted; only the ERCOT logo/marks (Clause 9) need prior permission. No
attribution is explicitly mandated for raw data. Treated as **rights-clean** for
compilations/analyses — materially better than PJM.

### ERCOT recommendation — (a) viable recurring interface

The Monthly GIS Report is a genuine reliable recurring public contract: a public
monthly XLSX with a durable per-request identity (INR), derivable application-vs-
decision semantics, and permissive reuse terms. Adapter fit: a **new connector**
("ercot_mis_xlsx" — resolve the stable `reportTypeId=15933` GetReports index,
pick the newest document id, download + parse the two gen tabs). It is not a
`json_array` or native `csv` source (source is XLSX, monthly, not JSON/CSV).
Closest existing precedent is the `manual_export` adapter. Remaining work before
activation: confirm the MIS host/TLS profile and the current column headers from
one live file.

---

## Honesty / limits

- PJM §B endpoint, row counts, key behaviour and cadence come from a
  third-party scraper's documentation plus one 405 probe; they are **not**
  confirmed from PJM's own pages (the current PJM interconnection-queues page was
  under maintenance / 404 at inspection time).
- No queue export was downloaded for either operator; column lists are from
  historical/secondary sources and must be re-read from a live file before any
  field mapping.
- ERCOT MIS fetch host/TLS needs validation (one probe failed the TLS
  handshake).
- Neither source should be activated on this evidence alone: ERCOT is
  qualify-to-build (rights-clean, durable identity) pending a live-file schema
  read; PJM is blocked on rights + an undocumented, key-dependent endpoint.
