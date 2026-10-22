"""Offline count-only preflight: no rows, database, or implicit network."""
from datetime import date

import pytest

from app.services.ingestion.connectors.base import ConnectorError
from scripts.columbus_corpus_preflight import build_report, main

KEY = "columbus_oh_site_engineering_applications"
TODAY = date(2026, 10, 20)


class Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get_json(self, url, *, params):
        self.calls.append((url, params))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def test_default_is_offline_monthly_plan_with_pinned_scope():
    report = build_report(KEY, date(2024, 1, 1), date(2024, 4, 1), today=TODAY)
    assert report["mode"] == "plan_only"
    assert report["date_field"] == "B1_FILE_DD"
    assert len(report["months"]) == 3
    month = report["months"][1]
    assert month["start_inclusive"] == "2024-02-01"
    assert month["end_exclusive"] == "2024-03-01"
    assert "B1_FILE_DD" in month["query"]["where"]
    assert month["count"] is None
    assert month["status"] == "not_probed"
    assert len(month["scope_sha256"]) == 64
    assert report["coverage_verified"] is False
    assert report["known_then_verified"] is False


@pytest.mark.parametrize("start,end", [
    (date(2024, 1, 2), date(2024, 2, 1)),
    (date(2024, 1, 1), date(2024, 2, 2)),
    (date(2024, 1, 1), date(2024, 1, 1)),
    (date(2026, 10, 1), date(2026, 11, 1)),
    (date(2020, 1, 1), date(2024, 1, 1)),
])
def test_rejects_partial_future_empty_or_oversized_intervals(start, end):
    with pytest.raises(ValueError):
        build_report(KEY, start, end, today=TODAY)


def test_probe_distinguishes_zero_oversized_and_unavailable_months():
    client = Client([{"count": 0}, {"count": 1001}, ConnectorError("sensitive response")])
    report = build_report(KEY, date(2024, 1, 1), date(2024, 4, 1), today=TODAY, client=client)
    assert [m["status"] for m in report["months"]] == ["count_observed", "split_required", "unavailable"]
    assert [m["count"] for m in report["months"]] == [0, 1001, None]
    assert report["months"][2]["error"] == "ConnectorError"
    assert len(client.calls) == 3
    assert all(p["returnCountOnly"] == "true" for _, p in client.calls)
    assert "sensitive" not in str(report)


@pytest.mark.parametrize("payload", [{}, {"count": True}, {"count": 3, "error": {}}, []])
def test_invalid_count_is_unavailable_not_zero(payload):
    report = build_report(KEY, date(2024, 1, 1), date(2024, 2, 1), today=TODAY, client=Client([payload]))
    assert report["months"][0]["count"] is None
    assert report["months"][0]["status"] == "unavailable"


def test_cli_refuses_existing_output_before_network(tmp_path, monkeypatch):
    output = tmp_path / "receipt.json"
    output.write_text("preserve")
    monkeypatch.setattr("sys.argv", ["preflight", "--source-key", KEY, "--start", "2024-01-01", "--end", "2024-02-01", "--probe", "--output", str(output)])
    with pytest.raises(FileExistsError):
        main()
    assert output.read_text() == "preserve"


def test_maximum_span_is_36_queries_with_one_issued_series():
    key = "columbus_oh_commercial_building_permits"
    client = Client([{"count": 1000}] * 36)
    report = build_report(key, date(2023, 10, 1), date(2026, 10, 1), today=TODAY, client=client)
    assert len(client.calls) == report["maximum_count_queries"] == 36
    assert report["date_field"] == "ISSUED_DT"
    assert all(m["status"] == "count_observed" for m in report["months"])
    assert all("ISSUED_YEAR" not in m["query"]["where"] for m in report["months"])
    offline = build_report(key, date(2023, 10, 1), date(2026, 10, 1), today=TODAY)
    assert offline["plan_sha256"] == report["plan_sha256"]
