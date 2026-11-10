"""Current-vintage 2025 public inputs, not point-in-time historical evidence."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from datetime import datetime, timezone

from app.services.ingestion.connectors.base import RetryingHttpClient

YEAR = 2025
MAX_BYTES = 12_000_000
HPI_URL = "https://www.fhfa.gov/hpi/download/quarterly_datasets/hpi_at_metro.csv"
POP_URL = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/metro/totals/cbsa-est2025-alldata.csv"
PERMIT_URLS = {year: f"https://www2.census.gov/econ/bps/County/co{year}a.txt"
               for year in range(2022, 2026)}
OFFICIAL_HOSTS = frozenset({"www.fhfa.gov", "www2.census.gov"})


def _rows(data: bytes, encoding: str):
    if len(data) > MAX_BYTES:
        raise ValueError("Input exceeds byte budget")
    return csv.reader(io.StringIO(data.decode(encoding), newline=""))


def _code(value: str, width: int) -> str:
    value = value.strip()
    if not re.fullmatch(rf"\d{{{width}}}", value, flags=re.ASCII):
        raise ValueError("Invalid geographic code")
    return value


def _integer(value: str, *, signed: bool = False) -> int | None:
    value = value.strip()
    if not re.fullmatch(r"-?\d+" if signed else r"\d+", value, flags=re.ASCII):
        return None
    return int(value)


def parse_hpi(data: bytes) -> dict[str, dict[int, float]]:
    """Annual means only for complete, unique four-quarter metro series."""
    quarters, seen = {}, set()
    for row in _rows(data, "utf-8"):
        if not row or not any(cell.strip() for cell in row):
            continue
        if len(row) != 6:
            raise ValueError("Expected six FHFA columns")
        _name, cbsa, year, quarter, index, _se = (cell.strip() for cell in row)
        cbsa = _code(cbsa, 5)
        year, quarter = int(year), int(quarter)
        if quarter not in (1, 2, 3, 4):
            raise ValueError("Invalid HPI quarter")
        key = (cbsa, year, quarter)
        if key in seen:
            raise ValueError("Duplicate HPI quarter")
        seen.add(key)
        if year not in (2023, 2025):
            continue
        try:
            value = float(index)
        except ValueError:
            continue
        if math.isfinite(value) and value > 0:
            quarters.setdefault((cbsa, year), {})[quarter] = value
    result = {}
    for (cbsa, year), values in sorted(quarters.items()):
        if len(values) == 4:
            result.setdefault(cbsa, {})[year] = math.fsum(values.values()) / 4
    return result


def parse_population(data: bytes) -> tuple[dict[str, dict], dict[str, str], frozenset[str]]:
    """2025 metro attributes and county-to-CBSA mapping on the same geography."""
    rows = _rows(data, "cp1252")
    header = next(rows, [])
    required = {"CBSA", "MDIV", "STCOU", "NAME", "LSAD", "POPESTIMATE2024",
                "POPESTIMATE2025", "NETMIG2025"}
    if len(set(header)) != len(header) or not required <= set(header):
        raise ValueError("Invalid Census population header")
    metros, counties, county_populations = {}, {}, {}
    for values in rows:
        if not values or not any(value.strip() for value in values):
            continue
        if len(values) != len(header):
            raise ValueError("Invalid population row width")
        row = dict(zip(header, (value.strip() for value in values)))
        if not row["CBSA"]:
            continue
        cbsa = _code(row["CBSA"], 5)
        if row["STCOU"]:
            county = _code(row["STCOU"], 5)
            if county in counties:
                raise ValueError("Duplicate county crosswalk")
            counties[county] = cbsa
            county_populations.setdefault(cbsa, []).append((
                _integer(row["POPESTIMATE2024"]), _integer(row["POPESTIMATE2025"])))
        elif not row["MDIV"] and row["LSAD"] == "Metropolitan Statistical Area":
            if cbsa in metros:
                raise ValueError("Duplicate metropolitan area")
            metros[cbsa] = {
                "name": row["NAME"],
                "population_2024": _integer(row["POPESTIMATE2024"]),
                "population_2025": _integer(row["POPESTIMATE2025"]),
                "net_migration_2025": _integer(row["NETMIG2025"], signed=True),
            }
    # Reconcile constituent population against both published metro totals.
    # A truncated crosswalk must not silently shrink the unit denominator.
    complete = frozenset(cbsa for cbsa, metro in metros.items()
        if county_populations.get(cbsa) and all(
            metro[f"population_{year}"] is not None
            and all(values[index] is not None for values in county_populations[cbsa])
            and sum(values[index] for values in county_populations[cbsa]) == metro[f"population_{year}"]
            for index, year in enumerate((2024, 2025))))
    return metros, counties, complete


def parse_county_permits(data: bytes, year: int) -> dict[str, int | None]:
    """Sum unit columns, never the adjacent building-count columns."""
    rows = _rows(data, "cp1252")
    if not next(rows, None) or not next(rows, None):
        raise ValueError("Missing two Census permit header rows")
    result = {}
    for row in rows:
        if not row or not any(value.strip() for value in row):
            continue
        if len(row) < 3 or row[0].strip() != str(year):
            raise ValueError("Unexpected county permit year/schema")
        state, county = row[1].strip(), row[2].strip()
        if not state.isascii() or not state.isdigit() or not county.isascii() or not county.isdigit():
            raise ValueError("Invalid county FIPS")
        fips = _code(state.zfill(2), 2) + _code(county.zfill(3), 3)
        if fips in result:
            raise ValueError("Duplicate county permit row")
        units = [_integer(row[i]) if i < len(row) else None for i in (7, 10, 13, 16)]
        result[fips] = sum(units) if all(value is not None for value in units) else None
    return result


def get_snapshot(http_client=None, now=None) -> dict:
    """At most six bounded fetch calls; no cache, DB, environment or model calls."""
    timestamp = now if now is not None else datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Timezone-aware capture timestamp required")
    captured_at = timestamp.astimezone(timezone.utc).isoformat()
    client = http_client if http_client is not None else RetryingHttpClient(
        timeout=20, max_retries=0, allowed_hosts=OFFICIAL_HOSTS)
    provenance = []

    def fetch(url, period):
        data, _headers = client.get_bytes(url, max_bytes=MAX_BYTES,
                                          headers={"Accept": "text/csv,text/plain"})
        if not isinstance(data, bytes) or len(data) > MAX_BYTES:
            raise ValueError("Invalid or oversized source bytes")
        provenance.append({"url": url, "sha256": hashlib.sha256(data).hexdigest(),
                           "captured_at": captured_at, "period": period})
        return data

    hpi = parse_hpi(fetch(HPI_URL, "2023,2025"))
    population, crosswalk, complete = parse_population(fetch(POP_URL, "2025 vintage; 2024-2025"))
    permits = {year: parse_county_permits(fetch(url, str(year)), year)
               for year, url in PERMIT_URLS.items()}
    members = {}
    for county, cbsa in sorted(crosswalk.items()):
        members.setdefault(cbsa, []).append(county)
    metros = []
    for cbsa in sorted(population):
        counties = members.get(cbsa, [])
        if cbsa not in complete or not counties or set(hpi.get(cbsa, {})) != {2023, 2025}:
            continue
        if any(permits[year].get(county) is None for year in PERMIT_URLS for county in counties):
            continue
        metros.append({"cbsa": cbsa, **population[cbsa], "hpi": hpi[cbsa],
                       "units": {year: sum(permits[year][county] for county in counties)
                                 for year in PERMIT_URLS}, "counties": counties})
    identity = {"version": "official-current-vintage-2025-v2", "year": YEAR,
                "sources": [{"url": p["url"], "sha256": p["sha256"]} for p in provenance],
                "metros": metros}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False,
                                       separators=(",", ":")).encode()).hexdigest()
    return {"year": YEAR, "captured_at": captured_at, "snapshot_id": digest,
            "provenance": provenance, "metros": metros, "context_metros": population}
