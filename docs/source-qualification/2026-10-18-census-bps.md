# Source Qualification — US Census Building Permits Survey (BPS), Place file

- **Date:** 2026-10-18
- **Status:** `technical_hold` (NON-activated candidate; `can_run_canary: false`)
- **Adapter:** `csv` (requires a small, backward-compatible `CSVConnector` enhancement — see §3)
- **Record type:** `permit` (with an important semantic caveat — see §6)
- **License:** US Census Bureau data is a work of the US federal government and is in the **public domain** (no copyright; attribution appreciated but not required).

---

## 1. Exact file used

```
https://www2.census.gov/econ/bps/Place/South%20Region/so2025a.txt
```

- Verified live on 2026-10-18 via bounded `Range` requests (HTTP `206 Partial Content`).
- Total size: **692,949 bytes** (≈693 KB). Read-only; only bounded ranges were fetched (head ~20 KB + two ~40 KB windows to confirm state coverage).
- Landing/index page: `https://www2.census.gov/econ/bps/Place/South%20Region/` — the current annual place file follows the `so<YYYY>a.txt` pattern (`so2025a.txt` is the current annual file as of this check). Monthly files use other suffixes; the `a` suffix is the year-to-date annual place file.

## 2. Format / header structure (the blocker)

- **Delimiter:** comma (`,`). Fields are **not** quoted; several code fields carry trailing/leading spaces (e.g. `00124 `, `36310      `).
- **Encoding:** parses cleanly as `latin-1` (ASCII in practice). Recommend `latin-1` rather than the connector default `utf-8-sig`.
- **Header is TWO rows plus a blank separator line, then data:**
  - Line 0 (0-based): group labels — `Survey,State,6-Digit,County,...,Place,,1-unit,,,2-units,,,...` (**40 fields**).
  - Line 1: sub-labels — `Date,Code,ID,Code,...,Name,Bldgs,Units,Value,Bldgs,Units,Value,...` (**41 fields**).
  - Line 2: a **blank separator line** containing a single space `" "`.
  - Line 3+: data rows (**41 fields** each).
- The two header rows do not align 1:1 (40 vs 41 fields) and the sub-labels repeat (`Bldgs`/`Units`/`Value` recur for each unit-size group), so neither row alone yields usable, unique column names. The repo `CSVConnector` uses `csv.DictReader` with a single header row, so it would (a) treat line 0 as the header, (b) emit the second header row and the blank line as bogus data rows, and (c) collapse the repeated `Bldgs/Units/Value` names. **It cannot parse this file as-is.**

**Merged, de-duplicated column names (41), left-to-right:**

```
survey_date, state_code, six_digit_id, county_code, census_place_code,
fips_place_code, fips_mcd_code, population, csa_code, cbsa_code,
footnote_code, central_city, zip_code, region_code, division_code,
number_of_months_reported, place_name,
1unit_bldgs, 1unit_units, 1unit_value,
2units_bldgs, 2units_units, 2units_value,
34units_bldgs, 34units_units, 34units_value,
5punits_bldgs, 5punits_units, 5punits_value,
1unit_rep_bldgs, 1unit_rep_units, 1unit_rep_value,
2units_rep_bldgs, 2units_rep_units, 2units_rep_value,
34units_rep_bldgs, 34units_rep_units, 34units_rep_value,
5punits_rep_bldgs, 5punits_rep_units, 5punits_rep_value
```

(The `*_rep` groups are the "reported" / imputation-adjusted counterparts of the first four unit-size groups. `state_code` = state FIPS: `01`=AL, `48`=TX, `51`=VA, `54`=WV.)

## 3. Proposed minimal `CSVConnector` enhancement (NOT yet applied)

Two new, optional, **backward-compatible** options (defaults preserve current behavior exactly):

- `skip_leading_lines: int = 0` — drop N raw lines from the top of the fetched text before parsing (skips extra header rows / blank separators).
- `fieldnames: Sequence[str] | None = None` — explicit, unique column names. When set, `DictReader` takes the first *remaining* line (after `skip_leading_lines`) as data, not as a header.

For BPS: `skip_leading_lines = 3` (drop both header rows + the blank line) **and** supply the 41 `fieldnames` from §2.

### File: `app/services/ingestion/connectors/csv.py`

**`__init__` — add parameters and store them** (after the existing `delimiter`/`encoding` handling):

```python
# new parameters in the signature, with defaults that keep current behavior:
skip_leading_lines: int = 0,
fieldnames: Sequence[str] | None = None,

# new validation/storage in the body:
if skip_leading_lines < 0:
    raise ValueError("skip_leading_lines must be >= 0")
self.skip_leading_lines = skip_leading_lines
self.fieldnames = list(fieldnames) if fieldnames is not None else None
```

(Add `Sequence` to the `from typing import ...` import.)

**`fetch` — skip leading lines and pass explicit fieldnames.** The fingerprint is still computed on the *full* `text` (snapshot semantics unchanged); only the parsed body is trimmed:

```python
text = self._read_text()
fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
# ... existing verify_snapshot block ...

if self.skip_leading_lines:
    # keepends=True preserves the source newline style so the dialect
    # sniff and row offsets stay consistent with the original file.
    body = "".join(text.splitlines(keepends=True)[self.skip_leading_lines:])
else:
    body = text

reader = csv.DictReader(
    io.StringIO(body, newline=""),
    fieldnames=self.fieldnames,          # None => header read from first line (unchanged)
    dialect=self._dialect(body),
)
if not reader.fieldnames:
    raise ConnectorResponseError("CSV source is missing a header row")
```

(Replace the two existing lines that build `reader` from `text`; everything else in `fetch` is unchanged. The existing `if None in row:` guard still catches rows that have *more* values than the supplied `fieldnames`.)

### Factory wiring — `app/services/ingestion/connectors/factory.py`, `connector_type == "csv"` branch

Add two lines to the `CSVConnector(...)` call so the new config keys flow through (the implementer applies this; this doc does not edit it):

```python
skip_leading_lines=int(config.get("skip_leading_lines", 0)),
fieldnames=_string_list(config.get("fieldnames"), "fieldnames"),
```

`_string_list` already exists and returns `None` when the key is absent, so defaults are preserved.

## 4. Draft `candidate_catalog.json` entry

```json
{
  "key": "census_bps_place_south",
  "name": "US Census Building Permits Survey — Place file (South Region)",
  "adapter": "csv",
  "record_type": "permit",
  "jurisdiction": "US South Region (incl. TX, VA)",
  "base_url": "https://www2.census.gov/econ/bps/Place/South%20Region/so2025a.txt",
  "official_landing_page": "https://www.census.gov/construction/bps/",
  "license": "US Census Bureau; work of the US federal government, public domain (no copyright). Attribution to the US Census Bureau is customary.",
  "status": "technical_hold",
  "blocker_summary": "The BPS place .txt has TWO header rows plus a blank separator line before data, so the current CSVConnector (single-row csv.DictReader) cannot parse it. Requires the backward-compatible skip_leading_lines + explicit fieldnames enhancement (see 2026-10-18-census-bps.md). Values are also aggregate monthly permit COUNTS by place, not individual permits.",
  "early_warning_value": "Monthly residential building-permit counts and valuations by place reveal where new-construction activity is accelerating or stalling across the South (TX/VA included) weeks before project-level permits surface, a leading indicator for market-wedge targeting.",
  "candidate_source_fields": [
    "survey_date",
    "state_code",
    "six_digit_id",
    "county_code",
    "place_name",
    "number_of_months_reported",
    "1unit_bldgs",
    "1unit_units",
    "1unit_value",
    "5punits_bldgs",
    "5punits_units",
    "5punits_value"
  ],
  "probe_settings": {
    "connector": {
      "source": "https://www2.census.gov/econ/bps/Place/South%20Region/so2025a.txt",
      "delimiter": ",",
      "encoding": "latin-1",
      "skip_leading_lines": 3,
      "fieldnames": [
        "survey_date", "state_code", "six_digit_id", "county_code", "census_place_code",
        "fips_place_code", "fips_mcd_code", "population", "csa_code", "cbsa_code",
        "footnote_code", "central_city", "zip_code", "region_code", "division_code",
        "number_of_months_reported", "place_name",
        "1unit_bldgs", "1unit_units", "1unit_value",
        "2units_bldgs", "2units_units", "2units_value",
        "34units_bldgs", "34units_units", "34units_value",
        "5punits_bldgs", "5punits_units", "5punits_value",
        "1unit_rep_bldgs", "1unit_rep_units", "1unit_rep_value",
        "2units_rep_bldgs", "2units_rep_units", "2units_rep_value",
        "34units_rep_bldgs", "34units_rep_units", "34units_rep_value",
        "5punits_rep_bldgs", "5punits_rep_units", "5punits_rep_value"
      ],
      "verify_snapshot": true,
      "page_size": 500,
      "timeout": 30.0,
      "max_retries": 3
    },
    "defaults": {
      "country": "US",
      "region": "South",
      "source_url": "https://www2.census.gov/econ/bps/Place/South%20Region/so2025a.txt"
    },
    "signal_stage": "permit_issued_aggregate",
    "refresh_frequency": "monthly",
    "freshness_sla_hours": 1080
  },
  "probe_field_mappings": [
    {
      "source_field": "__source_record_id",
      "canonical_field": "source_record_id",
      "transform": "join_fields",
      "transform_options": {
        "fields": ["survey_date", "state_code", "six_digit_id"],
        "separator": "|"
      },
      "is_required": true
    },
    {
      "source_field": "place_name",
      "canonical_field": "title",
      "is_required": true
    },
    {
      "source_field": "county_code",
      "canonical_field": "county"
    },
    {
      "source_field": "1unit_units",
      "canonical_field": "units"
    },
    {
      "source_field": "1unit_value",
      "canonical_field": "valuation"
    }
  ],
  "can_run_canary": false,
  "last_checked_on": "2026-10-18",
  "next_audit_on": "2026-11-18",
  "notes": "NON-activated candidate. Blocked on the CSVConnector skip_leading_lines + fieldnames enhancement. SEMANTIC CAVEAT: BPS place rows are aggregate monthly permit COUNTS/valuations by census place (per unit-size group), NOT individual permit records with addresses or permit numbers; map accordingly and do not present as project-level permits. probe_field_mappings above are illustrative aggregate mappings. Fixture for a parser unit test: tests/fixtures/bps/place_sample.txt. TX (state_code 48) and VA (51) rows confirmed present in the South Region file."
}
```

## 5. Fixture

Saved `tests/fixtures/bps/place_sample.txt` — the exact 2 header rows + the blank separator line + 5 real data rows (3 AL, 1 TX `48`, 1 VA `51`). A parser unit test should assert that with `skip_leading_lines=3` and the 41 `fieldnames`, it yields 5 records, each with 41 populated keys and no `None` key (restkey), and that `state_code` values `48` and `51` are present.

## 6. Semantic caveat (important)

BPS place-file rows are **aggregate monthly permit counts and valuations by census place**, broken out by structure size (1-unit, 2-units, 3–4 units, 5+ units, and their "reported"/imputation-adjusted counterparts). They are **not** individual permit records — there are no addresses, permit numbers, applicants, or parcels. Treat this as an area-level market-activity signal, not as project-level permit intelligence; the `record_type: permit` classification is about domain, not granularity.

## 7. TX / VA coverage confirmation

- `state_code` `48` (**TX**) confirmed present — e.g. place "Lago Vista" (and "Robinson").
- `state_code` `51` (**VA**) confirmed present — e.g. place "Madison County" (and "York County").
- Rows are ordered by state FIPS then place; the file also contains `54` (WV) and other South-Region states. Both TX and VA rows are included in the fixture.
