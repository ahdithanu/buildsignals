from copy import deepcopy
from datetime import datetime, timezone

import httpx
import pytest

from scripts import verify_ingestion_runs as verifier

NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def coverage(sources, **patch):
    return {"measured_at": NOW.isoformat(), "sources": sources, "has_more": False,
            "record_type": "permit", "freshness_hours": 36, "offset": 0, "limit": 100, **patch}


def evidence():
    return ({"source_id": "s1", "source_key": "reviewed_feed", "configured_active": True,
             "stored_records": 12, "observed_states": []},
            {"id": "r1", "source_id": "s1", "status": "completed", "trigger": "scheduled",
             "started_at": "2026-10-24T10:00:00Z", "completed_at": "2026-10-24T10:01:00Z",
             "records_failed": 0, "records_seen": 0, "checkpoint": {"keyset": "terminal"}})


def test_completed_quiet_run_with_terminal_cursor_is_healthy():
    source, run = evidence()
    result = verifier.evaluate_source(source, run, now=NOW, freshness_hours=36)
    assert result["passed"]
    assert result["stored_records"] == 12


@pytest.mark.parametrize("field,value", [("status", "partial_with_errors"), ("records_failed", 1),
    ("records_failed", False), ("records_seen", -1), ("trigger", "manual"),
    ("source_id", "other"), ("completed_at", None),
    ("started_at", "2026-10-20T10:00:00Z"), ("completed_at", "2026-10-25T10:00:00Z"),
    ("started_at", "2026-10-24T10:02:00Z")])
def test_unhealthy_or_inconsistent_run_fails(field, value):
    source, run = evidence()
    run[field] = value
    assert not verifier.evaluate_source(source, run, now=NOW, freshness_hours=36)["passed"]


def test_inactive_missing_empty_and_malformed_inventory_fail():
    source, run = evidence()
    assert not verifier.evaluate_source(source, None, now=NOW, freshness_hours=36)["passed"]
    for patch in [{"configured_active": False}, {"stored_records": 0}, {"stored_records": True}]:
        altered = {**deepcopy(source), **patch}
        assert not verifier.evaluate_source(altered, run, now=NOW, freshness_hours=36)["passed"]


def test_live_disabled_and_missing_token_never_make_requests():
    def forbidden(*args):
        pytest.fail("No request allowed")
    args = dict(api_base="https://example.com", organization_id="org", source_keys=["reviewed_feed"],
                token=None, allow_live=False, get=forbidden)
    assert verifier.verify(**args)["status"] == "blocked"
    args["allow_live"] = True
    assert verifier.verify(**args)["status"] == "blocked"


def test_wrong_workspace_or_demo_stops_before_inventory():
    for actor in [{"is_demo": True, "organization_id": "org"},
                  {"is_demo": False, "organization_id": "other"}]:
        calls = []
        def get(path):
            calls.append(path)
            return actor
        result = verifier.verify(api_base="https://example.com", organization_id="org",
            source_keys=["reviewed_feed"], token="private", allow_live=True, get=get, now=NOW)
        assert result["status"] == "blocked"
        assert calls == ["/v1/auth/me"]


def test_live_gate_uses_latest_run_and_never_emits_error_text():
    source, run = evidence()
    run["error_message"] = "SECRET raw source data"
    def get(path):
        if path.endswith("/auth/me"):
            return {"is_demo": False, "organization_id": "org"}
        if "/runs?" in path:
            return [run]
        return coverage([source])
    report = verifier.verify(api_base="https://example.com", organization_id="org",
        source_keys=["reviewed_feed"], token="private", allow_live=True, get=get, now=NOW)
    assert report["status"] == "passed"
    assert "SECRET" not in str(report) and "private" not in str(report)


def test_missing_source_and_unbounded_pages_fail_closed():
    def get(path):
        if path.endswith("/auth/me"):
            return {"is_demo": False, "organization_id": "org"}
        return coverage([], has_more=True)
    report = verifier.verify(api_base="https://example.com", organization_id="org",
        source_keys=["reviewed_feed"], token="private", allow_live=True, get=get, now=NOW)
    assert report["status"] == "blocked"


@pytest.mark.parametrize("url", ["http://example.com", "https://user:secret@example.com", "https://example.com?token=private", "https://example.com/v1"])
def test_unsafe_origin_is_rejected(url):
    with pytest.raises(ValueError):
        verifier.validate_origin(url)


@pytest.mark.parametrize("bad_id", [{"sensitive": "PRIVATE_MARKER"}, True, " ", "x" * 101])
def test_invalid_run_identity_cannot_pass_or_be_echoed(bad_id):
    source, run = evidence()
    run["id"] = bad_id
    report = verifier.evaluate_source(source, run, now=NOW, freshness_hours=36)
    assert not report["passed"]
    assert report["latest_run_id"] is None
    assert "PRIVATE_MARKER" not in str(report)


@pytest.mark.parametrize("patch", [{"record_type": "parcel"}, {"offset": 999}, {"limit": 200}, {"freshness_hours": 72}])
def test_mismatched_measurement_scope_is_rejected(patch):
    def get(path):
        if path.endswith("/auth/me"):
            return {"is_demo": False, "organization_id": "org"}
        return coverage([], **patch)
    assert verifier.verify(api_base="https://example.com", organization_id="org",
        source_keys=["reviewed_feed"], token="private", allow_live=True, get=get, now=NOW)["status"] == "blocked"


@pytest.mark.parametrize("response", [httpx.Response(302, headers={"Location": "https://other.example/"}),
    httpx.Response(401, text="SECRET private data"), httpx.Response(200, content=b"x" * 2_000_001)])
def test_live_transport_rejects_redirects_errors_and_oversize_without_leaking(monkeypatch, response):
    requests = []
    def handler(request):
        requests.append(request)
        return response
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    monkeypatch.setattr(verifier.httpx, "Client", lambda **kwargs: client)
    report = verifier.verify(api_base="https://example.com", organization_id="org",
        source_keys=["reviewed_feed"], token="private", allow_live=True, now=NOW)
    assert report["status"] == "blocked"
    assert len(requests) == 1
    assert "private" not in str(report) and "SECRET" not in str(report)


def test_coverage_measurement_future_or_stale_fails():
    for measured in ["2026-10-25T12:00:00Z", "2026-10-24T11:00:00Z"]:
        def get(path):
            if path.endswith("/auth/me"):
                return {"is_demo": False, "organization_id": "org"}
            return coverage([], measured_at=measured)
        assert verifier.verify(api_base="https://example.com", organization_id="org",
            source_keys=["reviewed_feed"], token="private", allow_live=True, get=get, now=NOW)["status"] == "blocked"
