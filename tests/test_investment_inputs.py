import csv
import io
from datetime import datetime, timezone

import pytest

from app.services import investment_inputs as inputs


def encoded(rows, encoding="cp1252"):
    stream = io.StringIO(newline="")
    csv.writer(stream).writerows(rows)
    return stream.getvalue().encode(encoding)


def hpi_rows():
    return [["Metro, Test", "12345", year, quarter, 100 + quarter, "-"]
            for year in (2023, 2025) for quarter in range(1, 5)]


def population_rows():
    header = ["CBSA", "MDIV", "STCOU", "NAME", "LSAD", "POPESTIMATE2024",
              "POPESTIMATE2025", "NETMIG2025"]
    return [header, ["12345", "", "", "M\xe9tro, Test", "Metropolitan Statistical Area", "100", "110", "-3"],
            ["12345", "", "01001", "County One", "County", "50", "55", "1"],
            ["12345", "", "01003", "County Two", "County", "50", "55", "2"],
            ["12345", "12346", "", "Division", "Metropolitan Division", "9", "9", "0"]]


def county_rows(year):
    rows = [["first", "header"], ["second", "header"], []]
    for county in ("001", "003"):
        row = [str(year), "01", county, "", "", "County", "999", "1", "999", "0",
               "2", "999", "0", "3", "999", "0", "4"]
        rows.append(row)
    return rows


class Client:
    def __init__(self):
        self.calls = []
        self.bodies = {inputs.HPI_URL: encoded(hpi_rows(), "utf-8"),
                       inputs.POP_URL: encoded(population_rows())}
        self.bodies.update({url: encoded(county_rows(year)) for year, url in inputs.PERMIT_URLS.items()})

    def get_bytes(self, url, *, max_bytes, headers):
        assert max_bytes == inputs.MAX_BYTES
        assert url in self.bodies
        self.calls.append(url)
        return self.bodies[url], {}


def test_snapshot_aggregates_units_on_current_counties_and_binds_provenance():
    client = Client()
    now = datetime(2026, 11, 9, tzinfo=timezone.utc)
    result = inputs.get_snapshot(client, now)
    assert len(client.calls) == len(set(client.calls)) == 6
    assert result["year"] == 2025 and result["captured_at"] == now.isoformat()
    metro, = result["metros"]
    assert metro == {"cbsa": "12345", "name": "M\xe9tro, Test", "hpi": {2023: 102.5, 2025: 102.5},
                     "units": {year: 20 for year in range(2022, 2026)},
                     "population_2024": 100, "population_2025": 110,
                     "net_migration_2025": -3, "counties": ["01001", "01003"]}
    assert len(result["provenance"]) == 6
    for source in result["provenance"]:
        assert set(source) == {"url", "sha256", "captured_at", "period"}
        assert len(source["sha256"]) == 64 and source["captured_at"] == now.isoformat()
    assert inputs.get_snapshot(Client(), datetime(2026, 11, 10, tzinfo=timezone.utc))["snapshot_id"] == result["snapshot_id"]
    client.bodies[inputs.PERMIT_URLS[2025]] += b"\n"
    assert inputs.get_snapshot(client, now)["snapshot_id"] != result["snapshot_id"]


@pytest.mark.parametrize("value", ["-", "nan", "inf", "-inf", "0", "-1", "garbage"])
def test_invalid_hpi_quarter_cannot_form_complete_annual_mean(value):
    rows = hpi_rows()
    rows[-1][4] = value
    assert inputs.parse_hpi(encoded(rows, "utf-8")) == {"12345": {2023: 102.5}}


def test_missing_or_duplicate_hpi_quarters():
    assert 2025 not in inputs.parse_hpi(encoded(hpi_rows()[:-1], "utf-8"))["12345"]
    with pytest.raises(ValueError, match="Duplicate HPI"):
        inputs.parse_hpi(encoded(hpi_rows() + [hpi_rows()[0]], "utf-8"))


@pytest.mark.parametrize("mode", ["missing", "invalid", "incomplete_hpi"])
def test_snapshot_excludes_metro_with_any_incomplete_constituent(mode):
    client = Client()
    rows = county_rows(2022)
    if mode == "missing":
        rows.pop()
    elif mode == "invalid":
        rows[-1][13] = "-"
    else:
        client.bodies[inputs.HPI_URL] = encoded(hpi_rows()[:-1], "utf-8")
    client.bodies[inputs.PERMIT_URLS[2022]] = encoded(rows)
    assert inputs.get_snapshot(client)["metros"] == []


def test_population_filters_divisions_and_preserves_unknown_optional_values():
    rows = population_rows()
    rows[1][-3:] = ["-", "", "NaN"]
    metros, counties, complete = inputs.parse_population(encoded(rows))
    assert complete == frozenset()
    assert set(metros) == {"12345"} and len(counties) == 2
    assert all(metros["12345"][key] is None for key in (
        "population_2024", "population_2025", "net_migration_2025"))
    with pytest.raises(ValueError, match="Duplicate county"):
        inputs.parse_population(encoded(rows + [rows[2]]))


def test_county_units_not_building_counts_and_schema_guards():
    assert inputs.parse_county_permits(encoded(county_rows(2025)), 2025) == {"01001": 10, "01003": 10}
    with pytest.raises(ValueError, match="Duplicate county"):
        inputs.parse_county_permits(encoded(county_rows(2025) + [county_rows(2025)[-1]]), 2025)
    with pytest.raises(ValueError, match="year/schema"):
        inputs.parse_county_permits(encoded(county_rows(2024)), 2025)


@pytest.mark.parametrize("column", [7, 10, 13, 16])
@pytest.mark.parametrize("value", ["-", "NaN", "inf", "-1", "1.5"])
def test_any_invalid_unit_component_invalidates_county(column, value):
    rows = county_rows(2025)
    rows[-1][column] = value
    assert inputs.parse_county_permits(encoded(rows), 2025)["01003"] is None


def test_population_excludes_micropolitan_and_county_rows_from_metro_universe():
    rows = population_rows()
    rows += [["54321", "", "", "Micro", "Micropolitan Statistical Area", "10", "11", "1"],
             ["54321", "", "02001", "Micro county", "County", "10", "11", "1"]]
    metros, counties, complete = inputs.parse_population(encoded(rows))
    assert complete == frozenset({"12345"})
    assert set(metros) == {"12345"}
    assert counties["02001"] == "54321"


def test_strict_encodings_and_byte_budget(monkeypatch):
    with pytest.raises(UnicodeDecodeError):
        inputs.parse_hpi(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        inputs.parse_population(b"\x81")
    client = Client()
    monkeypatch.setattr(inputs, "MAX_BYTES", 10)
    with pytest.raises(ValueError, match="oversized"):
        inputs.get_snapshot(client)


@pytest.mark.parametrize("mode", ["missing_county", "unknown_population", "mismatched_population"])
@pytest.mark.parametrize("year_index", [-3, -2])
def test_incomplete_crosswalk_retains_context_but_cannot_produce_rank(mode, year_index):
    client = Client()
    rows = population_rows()
    if mode == "missing_county":
        rows.pop(3)
    elif mode == "unknown_population":
        rows[3][year_index] = "-"
    else:
        rows[3][year_index] = "49"
    client.bodies[inputs.POP_URL] = encoded(rows)
    result = inputs.get_snapshot(client)
    assert result["metros"] == []
    assert result["context_metros"]["12345"]["population_2025"] == 110


def test_counties_with_division_codes_are_included_in_complete_metro_crosswalk():
    client = Client()
    rows = population_rows()
    rows[3][1] = "12346"
    client.bodies[inputs.POP_URL] = encoded(rows)
    assert inputs.get_snapshot(client)["metros"][0]["counties"] == ["01001", "01003"]


def test_default_transport_is_bounded_to_official_hosts_without_retries(monkeypatch):
    client = Client()
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return client

    monkeypatch.setattr(inputs, "RetryingHttpClient", factory)
    inputs.get_snapshot()
    assert calls == [{"timeout": 20, "max_retries": 0,
                      "allowed_hosts": frozenset({"www.fhfa.gov", "www2.census.gov"})}]
    assert len(client.calls) == 6
    with pytest.raises(ValueError, match="Timezone-aware"):
        inputs.get_snapshot(client, datetime(2026, 11, 9))
