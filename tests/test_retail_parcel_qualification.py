import json

import pytest

from scripts import retail_parcel_refresh as worker

KEY = "orange_county_fl_property_appraiser_parcels"
SCOPE = dict(anchor_id="real-anchor-required", latitude=28.5, longitude=-81.4, radius_miles=1)


class PublicClient:
    def __init__(self, rows=None, before=None, after=None):
        self.rows = rows if rows is not None else [self.row(1)]
        self.before = len(self.rows) if before is None else before
        self.after = self.before if after is None else after
        self.calls = []
        self.count_calls = 0

    @staticmethod
    def row(i):
        return {"attributes": {"OBJECTID": i, "PARCEL": f"{i:015d}",
                               "LATITUDE": 28.5, "LONGITUDE": -81.4,
                               "PARENT_ID": "parent", "SITUS": "Public situs"}}

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append(dict(params))
        if params.get("returnCountOnly"):
            self.count_calls += 1
            return {"count": self.before if self.count_calls == 1 else self.after}
        offset = 0
        if "OBJECTID > " in params["where"]:
            offset = int(params["where"].rsplit("OBJECTID > ", 1)[1].rstrip(")"))
        rows = [r for r in self.rows if r["attributes"]["OBJECTID"] > offset]
        return {"features": rows[:params["resultRecordCount"]],
                "exceededTransferLimit": len(rows) > params["resultRecordCount"]}


@pytest.mark.parametrize("key", worker.FIELDS)
def test_scopes_are_private_inactive_and_preserve_provenance(key):
    original = next(e for e in worker.load_catalog() if e.key == key)
    snapshot = original.model_dump()
    entry = worker.scoped_entry(key, **SCOPE)
    assert not entry.is_active
    assert len(entry.key) <= 100
    for name in ("rights_basis", "license", "official_landing_page", "export_policy"):
        assert entry.settings.get(name) == original.settings.get(name)
    assert entry.settings["defaults"] == original.settings["defaults"]
    assert {m.canonical_field for m in entry.field_mappings} <= worker.CANONICAL
    config = entry.settings["connector"]
    assert config["page_size"] == 250
    assert config["include_geometry"] == (key != KEY)
    assert json.loads(config["query"]["geometry"]) == {
        "x": -81.4, "y": 28.5, "spatialReference": {"wkid": 4326}}
    assert "mapID" not in json.dumps(entry.field_mappings, default=str)
    assert worker.scoped_entry(key, **{**SCOPE, "radius_miles": 1.0}).key == entry.key
    assert original.model_dump() == snapshot


@pytest.mark.parametrize("change", [dict(anchor_id=" "), dict(anchor_id=None),
    dict(latitude=float("inf")), dict(longitude=float("nan")), dict(radius_miles=True),
    dict(latitude=True), dict(radius_miles=0.249), dict(radius_miles=3.01)])
def test_invalid_scopes_fail(change):
    with pytest.raises(ValueError):
        worker.scoped_entry(KEY, **{**SCOPE, **change})


@pytest.mark.parametrize("key", worker.FIELDS)
@pytest.mark.parametrize("restriction", ["inactive", "absent", None, "", "  ", False, {}])
def test_catalog_holds_and_missing_rights_fail_before_requests(monkeypatch, key, restriction):
    entry = next(e for e in worker.load_catalog() if e.key == key).model_copy(deep=True)
    if restriction == "inactive":
        entry.is_active = False
    elif restriction == "absent":
        entry.settings.pop("rights_basis")
    else:
        entry.settings["rights_basis"] = restriction
    monkeypatch.setattr(worker, "load_catalog", lambda: [entry])
    with pytest.raises(ValueError, match="active|rights"):
        worker.scoped_entry(key, **SCOPE)
    client = PublicClient()
    with pytest.raises(ValueError, match="active|rights"):
        worker.verify_scope(key, **SCOPE, http_client=client)
    assert client.calls == []


def test_report_uses_normalization_but_does_not_publish_records():
    client = PublicClient()
    report = worker.verify_scope(KEY, **SCOPE, http_client=client)
    assert report["records_valid"] == report["distinct_parcels"] == 1
    assert report["publisher_freshness"] == "unknown"
    assert report["production_anchor_verified"] is False
    assert report["production_qualified"] is False
    assert "Public situs" not in json.dumps(report)
    for call in client.calls:
        assert call["distance"] == 1
        assert call["inSR"] == call["outSR"] == 4326


def test_full_budget_uses_250_row_pages_and_single_exhaustion_probe():
    client = PublicClient([PublicClient.row(i) for i in range(1, 2001)])
    report = worker.verify_scope(KEY, **SCOPE, http_client=client)
    assert report["records_valid"] == 2000
    pages = [c for c in client.calls if "resultRecordCount" in c]
    assert [p["resultRecordCount"] for p in pages] == [250] * 8 + [1]


@pytest.mark.parametrize("count", [0, 2001, True, -1, "1"])
def test_bad_counts_fail_before_canary(count):
    client = PublicClient(before=count)
    with pytest.raises(ValueError):
        worker.verify_scope(KEY, **SCOPE, http_client=client)
    assert len(client.calls) == 1


@pytest.mark.parametrize("field,value", [("NAME1", "private"), ("LATITUDE", None),
                                       ("LATITUDE", 95), ("OBJECTID", True)])
def test_bad_rows_fail_closed(field, value):
    row = PublicClient.row(1)
    row["attributes"][field] = value
    with pytest.raises(ValueError):
        worker.verify_scope(KEY, **SCOPE, http_client=PublicClient([row]))


def test_count_drift_fails():
    with pytest.raises(ValueError, match="reconcile"):
        worker.verify_scope(KEY, **SCOPE, http_client=PublicClient(after=2))


@pytest.mark.parametrize("key", [k for k in worker.FIELDS if k != KEY])
def test_point_and_polygon_normalize_with_existing_transforms(key):
    if key.startswith("collin"):
        row = {"attributes": {"OBJECTID": 1, "PROP_ID": 123, "geoID": "group"},
               "geometry": {"rings": [[[-81.41, 28.49], [-81.39, 28.49],
                                         [-81.39, 28.51], [-81.41, 28.51],
                                         [-81.41, 28.49]]],
                            "spatialReference": {"wkid": 4326}}}
    elif key.startswith("new_jersey"):
        row = {"attributes": {"OBJECTID": 1, "PIN_NODUP": "0817_TEST_1"},
               "geometry": {"rings": [[[-81.41, 28.49], [-81.39, 28.49],
                                         [-81.39, 28.51], [-81.41, 28.51],
                                         [-81.41, 28.49]]],
                            "spatialReference": {"wkid": 4326}}}
    else:
        row = {"attributes": {"OBJECTID": 1, "FOLIO": "0000000000001"},
               "geometry": {"x": -81.4, "y": 28.5, "spatialReference": {"wkid": 4326}}}
    assert worker.verify_scope(key, **SCOPE, http_client=PublicClient([row]))["records_valid"] == 1
    row["geometry"]["spatialReference"]["wkid"] = 2236
    with pytest.raises(ValueError, match="WGS84"):
        worker.verify_scope(key, **SCOPE, http_client=PublicClient([row]))


def test_private_payload_cannot_hide_in_allowed_attributes():
    row = PublicClient.row(1)
    row["attributes"]["SITUS"] = {"owner": "private"}
    with pytest.raises(ValueError, match="nested"):
        worker.verify_scope(KEY, **SCOPE, http_client=PublicClient([row]))


def test_cli_redacts_provider_failure(monkeypatch, capsys):
    def failure(*args, **kwargs):
        raise ValueError("private upstream payload")
    monkeypatch.setattr(worker, "verify_scope", failure)
    assert worker.main(["--source-key", KEY, "--anchor-id", "required-anchor",
                        "--latitude", "28.5", "--longitude", "-81.4",
                        "--radius-miles", "1", "--verify"]) == 1
    assert "private upstream" not in capsys.readouterr().out


def test_duplicate_parcel_rows_are_reported_not_unique_inventory():
    rows = [PublicClient.row(1), PublicClient.row(2)]
    rows[1]["attributes"]["PARCEL"] = rows[0]["attributes"]["PARCEL"]
    report = worker.verify_scope(KEY, **SCOPE, http_client=PublicClient(rows))
    assert report["distinct_parcels"] == report["duplicate_parcel_rows"] == 1


def test_cli_default_is_offline(monkeypatch, capsys):
    def denied(*args, **kwargs):
        raise AssertionError("Offline CLI must not use network")
    monkeypatch.setattr(worker, "_BoundedClient", denied)
    assert worker.main(["--source-key", KEY, "--anchor-id", "required-anchor",
                        "--latitude", "28.5", "--longitude", "-81.4",
                        "--radius-miles", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["is_active"] is False


@pytest.mark.parametrize("budget", [0, 2001, True, 1.5])
def test_invalid_budget_never_requests(budget):
    client = PublicClient()
    with pytest.raises(ValueError):
        worker.verify_scope(KEY, **SCOPE, max_records=budget, http_client=client)
    assert not client.calls
