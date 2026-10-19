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

## ERCOT (updated 2026-10-18)

This section supersedes the original design-only recommendation. PR #252 now
implements `ercot_mis_xlsx` on the PR #251 stack, with review corrections
implemented and verified offline. The candidate remains `technical_hold` and `can_run_canary=false`;
no live ingestion or promotion is authorized.

The dated manual evidence and actual workbook headers are recorded in
`2026-10-17-ercot-contract-spec.md`. They identify the public **HTML** report
index at `https://www.ercot.com/misapp/GetReports.do?reportTypeId=15933` and
`Project Details - Large Gen` / `Project Details - Small Gen` XLSX tabs. The
original `misapp.ercot.com`/XML assumption is superseded. Read the current
connector design for implemented bounds, stage contracts and normalization.

INR is the durable request identity. The report label supplies the snapshot
month; the publication date selects the newest document. A September report
posted October 1 remains a September snapshot. Operator energization or
synchronization milestones can support decision classification; study/FIS
completion, signed IA and projected COD alone cannot. Interconnection events
remain explicitly identified even though the supported storage class is
`permit`.

Commercial reuse is **not cleared**: the original rights-clean interpretation
of Website User Agreement Clause 5 is provisional and does not replace written
confirmation. Public download does not establish public-domain status. Required
before promotion: written commercial-reuse confirmation, separately authorized
live host/TLS/workbook verification using the supported connector, and a bounded
canary receipt. Historical manual downloads are not a successful connector
canary. No new live access was performed for this documentation update.


## Honesty / limits

- PJM §B endpoint, row counts, key behavior and cadence remain based on the
  original third-party documentation plus one 405 probe, not a qualified
  supported public queue contract.
- The initial qualification did not download either operator's queue export.
  A later historical manual ERCOT read is documented in the companion contract
  spec; no current supported-connector live run has been qualified here.
- Neither operator is activated by these reports. PJM retains its documented
  rights/interface blockers; ERCOT retains its technical hold and written
  commercial-reuse/live-contract/canary gates.
