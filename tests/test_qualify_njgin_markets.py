import json
import socket
from copy import deepcopy

import pytest

from scripts import qualify_njgin_markets as nj


class Client:
    def __init__(self, *, centroid=True):
        self.calls = []
        self.meta = {
            "fields": [
                {"name": "OBJECTID", "type": "esriFieldTypeOID"},
                {"name": "PIN_NODUP", "type": "esriFieldTypeString"},
                {"name": "PCL_MUN", "type": "esriFieldTypeString", "length": 4},
                {"name": "PAMS_PIN", "type": "esriFieldTypeString"},
                {"name": "PCL_PBDATE", "type": "esriFieldTypeDate"},
                {"name": "PCLLASTUPD", "type": "esriFieldTypeDate"},
            ],
            "geometryType": "esriGeometryPolygon",
            "advancedQueryCapabilities": {
                "supportsReturningGeometryCentroid": centroid,
                "supportsOrderBy": True,
            },
        }
        self.count = 20
        self.features = [
            {"attributes": {"OBJECTID": i, "PIN_NODUP": f"PRIVATE-PIN-{i}",
                            "PCL_MUN": "0817", "PCL_PBDATE": 1767225600000,
                            "PCLLASTUPD": None},
             "centroid": {"x": -75.31, "y": 39.74}}
            for i in range(1, 4)
        ]
        if not centroid:
            for feature in self.features:
                feature.pop("centroid")
                feature["geometry"] = {"rings": [[
                    [-75.32, 39.73], [-75.30, 39.73], [-75.30, 39.75],
                    [-75.32, 39.75], [-75.32, 39.73],
                ]]}

    def get_bytes(self, url, *, params=None, headers=None, max_bytes):
        self.calls.append((url, dict(params), max_bytes))
        if url == nj.LAYER:
            body = self.meta
        elif params.get("returnCountOnly") == "true":
            body = {"count": self.count}
        else:
            features = deepcopy(self.features)
            code = next(code for code in nj.MARKETS if f"'{code}'" in params["where"])
            for feature in features:
                if feature["attributes"]["PCL_MUN"] == "0817":
                    feature["attributes"]["PCL_MUN"] = code
            body = {"features": features, "spatialReference": {"wkid": 4326},
                    "exceededTransferLimit": True}
        return json.dumps(body).encode(), {}


def test_default_never_constructs_transport(monkeypatch):
    def forbidden(**kwargs):
        pytest.fail("offline mode constructed HTTP transport")

    monkeypatch.setattr(nj, "RetryingHttpClient", forbidden)
    client = Client()
    assert nj.qualify(http_client=client)["network_requests"] == 0
    assert client.calls == []
    assert nj.qualify()["is_active"] is False
    assert nj.qualify()["metadata_observed"] is False
    assert nj.qualify()["metadata_flags"] == {
        "supportsQueryWithDistance": None,
        "supportsQueryWithHistoricMoment": None,
        "supportsReturningGeometryCentroid": None,
    }


def test_live_is_seven_bounded_requests_with_aggregate_output_only():
    client = Client()
    report = nj.qualify(live=True, http_client=client)
    assert report["technical_qualification_passed"] is True
    assert report["catalog_contract_verified"] is False
    assert report["schema"]["missing_optional_fields"] == ["PCL_GUID"]
    assert report["schema"]["legacy_optional_fields_missing"] == ["PCL_GUID"]
    assert report["schema"]["required_schema_valid"] is True
    assert report["identity_field"] == "PIN_NODUP"
    assert report["network_requests"] == len(client.calls) == 7
    assert report["is_active"] is False
    assert all(size == nj.MAX_BYTES for _, _, size in client.calls)
    for code, result in report["markets"].items():
        assert result["provider_count"] == 20
        assert result["sample_rows"] == result["sample_unique_ids"] == 3
        assert result["sample_valid_wgs84_centroids"] == 3
        assert result["sample_dates"]["PCL_PBDATE"]["max"] == "2026-01-01"
        queries = [p for _, p, _ in client.calls if f"'{code}'" in p.get("where", "")]
        assert len(queries) == 2
        assert all("PIN_NODUP <> 'XXXNLL'" in p["where"] for p in queries)
        sample = next(p for p in queries if "outFields" in p)
        assert sample["resultRecordCount"] == 3
        assert sample["resultOffset"] == 0
        assert sample["returnGeometry"] == "false"
        assert sample["returnCentroid"] == "true"
        assert sample["outSR"] == 4326
        assert set(sample["outFields"].split(",")) == {
            "OBJECTID", "PIN_NODUP", "PCL_MUN", "PCL_PBDATE", "PCLLASTUPD"}
    output = json.dumps(report)
    for private in ("PRIVATE-PIN", "-75.31", "39.74", "features", "attributes", "rings"):
        assert private not in output


def test_temporary_polygons_use_local_centroid_without_claiming_server_support():
    client = Client(centroid=False)
    report = nj.qualify(live=True, http_client=client)
    assert report["technical_qualification_passed"] is True
    assert report["schema"]["supports_centroid"] is False
    assert report["geometry_mode"] == "local_polygon_centroid"
    assert report["schema"]["missing_optional_fields"] == ["PCL_GUID"]
    assert len(client.calls) == 7
    for _, params, _ in client.calls:
        if "outFields" in params:
            assert params["returnGeometry"] == "true"
            assert "returnCentroid" not in params
            assert params["outSR"] == 4326
            assert params["resultRecordCount"] == 3
    assert all(row["sample_valid_wgs84_centroids"] == 3 for row in report["markets"].values())
    assert report["centroid_method"] == "existing_arcgis_polygon_centroid_first_ring"
    for private in ("rings", "PRIVATE-PIN", "-75.32", "39.73", "attributes", "features"):
        assert private not in json.dumps(report)


@pytest.mark.parametrize("codes", [(), ("0820",), ("0817", "0817"),
                                   (817,), ("0817' OR 1=1",), "0817", (True,)])
def test_invalid_municipalities_rejected_before_network(codes):
    client = Client()
    with pytest.raises(ValueError, match="municipalit"):
        nj.qualify(live=True, municipalities=codes, http_client=client)
    assert client.calls == []


def test_single_municipality_has_one_count_and_one_sample():
    client = Client()
    report = nj.qualify(live=True, municipalities=("0409",), http_client=client)
    assert set(report["markets"]) == {"0409"}
    assert len(client.calls) == 3


@pytest.mark.parametrize("mutation", ["missing", "numeric", "wrong_length"])
def test_municipality_schema_is_verified_not_assumed(mutation):
    client = Client()
    field = client.meta["fields"][2]
    if mutation == "missing":
        client.meta["fields"].remove(field)
    elif mutation == "numeric":
        field["type"] = "esriFieldTypeInteger"
    else:
        field["length"] = 5
    report = nj.qualify(live=True, http_client=client)
    assert report["failure_reason"] == "schema_mismatch"
    assert len(client.calls) == 1


@pytest.mark.parametrize("field", ["OWNER_NAME", "LAND_VAL", "SALE_PRICE", "geometry"])
def test_unrequested_fields_fail_without_echoing_values(field):
    client = Client()
    client.features[0]["attributes"][field] = "Sensitive Synthetic Person"
    report = nj.qualify(live=True, http_client=client)
    assert report["failure_reason"] == "sample_field_scope"
    assert "Sensitive" not in json.dumps(report)
    assert len(client.calls) == 3


def test_raw_polygon_rejected_before_connector_discards_it():
    client = Client()
    client.features[0]["geometry"] = {"rings": [[[1, 2], [3, 4]]]}
    report = nj.qualify(live=True, http_client=client)
    assert report["failure_reason"] == "sample_geometry_scope"
    assert "rings" not in json.dumps(report)


@pytest.mark.parametrize("count", [True, -1, "20", None])
def test_invalid_count_fails_before_sample(count):
    client = Client()
    client.count = count
    report = nj.qualify(live=True, http_client=client)
    assert report["failure_reason"] == "invalid_count"
    assert len(client.calls) == 2


def test_overlarge_sample_is_rejected():
    client = Client()
    client.features *= 2
    assert nj.qualify(live=True, http_client=client)["failure_reason"] == "sample_record_scope"


@pytest.mark.parametrize("pin", [None, "", "XXXNLL", 123])
def test_identity_never_falls_back_to_objectid(pin):
    client = Client()
    client.features[0]["attributes"]["PIN_NODUP"] = pin
    assert nj.qualify(live=True, http_client=client)["failure_reason"] == "invalid_identity"


def test_foreign_municipality_row_rejected():
    client = Client()
    client.features[0]["attributes"]["PCL_MUN"] = "0820"
    assert nj.qualify(live=True, http_client=client)["failure_reason"] == "municipality_mismatch"


@pytest.mark.parametrize("centroid", [None, {"x": 200, "y": 39},
                                       {"x": True, "y": 39},
                                       {"x": -75, "y": float("nan")},
                                       {"x": -75, "y": 39, "spatialReference": {"wkid": 3424}}])
def test_invalid_centroid_is_not_a_success(centroid):
    client = Client()
    client.features[0]["centroid"] = centroid
    report = nj.qualify(live=True, http_client=client)
    assert report["technical_qualification_passed"] is False
    assert report["failure_reason"] == "invalid_centroid"


def test_empty_count_skips_sample_and_does_not_establish_coverage():
    client = Client()
    client.count = 0
    report = nj.qualify(live=True, http_client=client)
    assert len(client.calls) == 4
    assert report["technical_qualification_passed"] is False
    assert all(row["sample_skipped"] == "empty_scope" for row in report["markets"].values())


def test_byte_limit_and_transport_failure_are_sanitized():
    class Oversize(Client):
        def get_bytes(self, *args, **kwargs):
            return b"x" * (nj.MAX_BYTES + 1), {}

    assert nj.qualify(live=True, http_client=Oversize())["failure_reason"] == "response_byte_budget"

    class Broken(Client):
        def get_bytes(self, *args, **kwargs):
            self.calls.append(args[0])
            raise socket.gaierror("Sensitive Synthetic Error")

    client = Broken()
    report = nj.qualify(live=True, http_client=client)
    assert report["failure_reason"] == "dns_resolution_failed"
    assert report["network_requests"] == len(client.calls) == 1
    assert report["metadata_observed"] is False
    assert all(value is None for value in report["metadata_flags"].values())
    assert "Sensitive" not in json.dumps(report)


def test_cli_default_is_offline(capsys):
    assert nj.main([]) == 0
    assert json.loads(capsys.readouterr().out)["network_requests"] == 0


def test_default_transport_has_no_retries(monkeypatch):
    options = {}
    client = Client(centroid=False)

    def factory(**kwargs):
        options.update(kwargs)
        return client

    monkeypatch.setattr(nj, "RetryingHttpClient", factory)
    nj.qualify(live=True)
    assert options["max_retries"] == 0
    assert options["allowed_hosts"] == frozenset({"maps.nj.gov"})


def test_missing_primary_schema_never_uses_optional_guid():
    client = Client()
    client.meta["fields"] = [field for field in client.meta["fields"]
                             if field["name"] != "PIN_NODUP"]
    client.meta["fields"].append({"name": "PCL_GUID", "type": "esriFieldTypeGUID"})
    report = nj.qualify(live=True, http_client=client)
    assert report["failure_reason"] == "schema_mismatch"
    assert report["schema"]["required_fields_missing"] == ["PIN_NODUP"]
    assert report["identity_field"] == "PIN_NODUP"
    assert len(client.calls) == 1


def test_duplicate_primary_ids_rejected():
    client = Client()
    client.features[1]["attributes"]["PIN_NODUP"] = client.features[0]["attributes"]["PIN_NODUP"]
    assert nj.qualify(live=True, http_client=client)["failure_reason"] == "duplicate_identity"


def test_count_smaller_than_sample_rejected():
    client = Client()
    client.count = 1
    assert nj.qualify(live=True, http_client=client)["failure_reason"] == "sample_record_scope"


def test_byte_boundary_rejects_unknown_endpoint_and_eighth_request():
    client = Client()
    bounded = nj._BoundedClient(client)
    with pytest.raises(ValueError, match="endpoint_scope"):
        bounded.get_json(nj.LAYER + "/other")
    assert client.calls == [] and bounded.requests == 0
    for _ in range(nj.MAX_REQUESTS):
        bounded.get_json(nj.LAYER, params={"f": "json"})
    with pytest.raises(ValueError, match="request_budget"):
        bounded.get_json(nj.LAYER, params={"f": "json"})
    assert len(client.calls) == bounded.requests == nj.MAX_REQUESTS


@pytest.mark.parametrize("payload", [b"not json", b"[]",
                                     b'{"error":{"message":"Sensitive Error"}}'])
def test_malformed_or_error_response_is_sanitized(payload):
    class Invalid(Client):
        def get_bytes(self, *args, **kwargs):
            return payload, {}

    report = nj.qualify(live=True, http_client=Invalid())
    assert report["failed"] is True
    assert "Sensitive" not in json.dumps(report)
    assert report["network_requests"] == 1


def test_cli_live_failure_is_nonzero_and_sanitized(monkeypatch, capsys):
    class Broken(Client):
        def get_bytes(self, *args, **kwargs):
            raise RuntimeError("Sensitive Provider Body")

    monkeypatch.setattr(nj, "RetryingHttpClient", lambda **kwargs: Broken())
    assert nj.main(["--live", "--municipality", "0817"]) == 1
    output = capsys.readouterr().out
    assert "Sensitive" not in output
    assert json.loads(output)["failure_reason"] == "transport_or_response_error"


def test_cli_duplicate_municipality_exits_without_transport(monkeypatch, capsys):
    monkeypatch.setattr(nj, "RetryingHttpClient", lambda **kwargs: pytest.fail("network access"))
    with pytest.raises(SystemExit) as error:
        nj.main(["--live", "--municipality", "0817", "--municipality", "0817"])
    assert error.value.code == 2
    assert capsys.readouterr().out == ""


def test_neither_mode_opens_database_connections_or_sessions(monkeypatch):
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session

    def forbidden(*args, **kwargs):
        pytest.fail("qualifier attempted database access")

    monkeypatch.setattr(Engine, "connect", forbidden)
    monkeypatch.setattr(Engine, "raw_connection", forbidden)
    monkeypatch.setattr(Session, "__init__", forbidden)
    assert nj.qualify()["network_requests"] == 0
    assert nj.qualify(live=True, http_client=Client())["technical_qualification_passed"] is True
    assert nj.qualify(live=True, http_client=Client(centroid=False))["technical_qualification_passed"] is True


@pytest.mark.parametrize("geometry", [None, {}, {"rings": []},
                                      {"rings": [[[True, 39], [-75, 39], [-75, 40]]]},
                                      {"rings": [[[200, 39], [-75, 39], [-75, 40]]]},
                                      {"rings": [[[-75, float("nan")], [-75, 39], [-75, 40]]]},
                                      {"rings": [[[-75, 39], [-74, 39], [-74, 40]]],
                                       "spatialReference": {"wkid": 3424}}])
def test_invalid_temporary_polygons_fail_without_output(geometry):
    client = Client(centroid=False)
    client.features[0]["geometry"] = geometry
    report = nj.qualify(live=True, http_client=client)
    assert report["failure_reason"] == "invalid_polygon"
    assert report["technical_qualification_passed"] is False
    assert "rings" not in json.dumps(report)


def test_polygon_mode_rejects_unrequested_owner_fields():
    client = Client(centroid=False)
    client.features[0]["attributes"]["OWNER_NAME"] = "Sensitive Synthetic Owner"
    report = nj.qualify(live=True, http_client=client)
    assert report["failure_reason"] == "sample_field_scope"
    assert "Sensitive" not in json.dumps(report)


def test_local_centroid_uses_existing_polygon_transform():
    client = Client(centroid=False)
    point = nj._local_centroid(client.features[0]["geometry"], {"wkid": 4326})
    assert point["x"] == pytest.approx(-75.31)
    assert point["y"] == pytest.approx(39.74)
    assert point["spatialReference"] == {"wkid": 4326}


@pytest.mark.parametrize("value", [True, False, None, "true", 1,
                                   {"message": "Sensitive Synthetic Metadata"}])
def test_safe_metadata_flags_preserve_only_observed_booleans(value):
    client = Client(centroid=False)
    client.meta["advancedQueryCapabilities"].update(
        supportsQueryWithDistance=value, supportsQueryWithHistoricMoment=False)
    report = nj.qualify(live=True, http_client=client)
    assert report["metadata_observed"] is True
    assert report["metadata_flags"] == {
        "supportsQueryWithDistance": value if type(value) is bool else None,
        "supportsQueryWithHistoricMoment": False,
        "supportsReturningGeometryCentroid": False,
    }
    assert report["network_requests"] == len(client.calls) == 7
    assert "Sensitive" not in json.dumps(report)


def test_metadata_flags_retained_if_required_schema_fails():
    client = Client()
    client.meta["fields"] = []
    client.meta["advancedQueryCapabilities"]["supportsQueryWithDistance"] = True
    report = nj.qualify(live=True, http_client=client)
    assert report["failure_reason"] == "schema_mismatch"
    assert report["metadata_observed"] is True
    assert report["metadata_flags"]["supportsQueryWithDistance"] is True
    assert report["metadata_flags"]["supportsQueryWithHistoricMoment"] is None
    assert len(client.calls) == 1


@pytest.mark.parametrize("ring", [
    [[-75, 39], [-75, 39], [-75, 39], [-75, 39]],
    [[-75, 39], [-74, 39], [-73, 39], [-75, 39]],
    [[-75, 39], [-74, 40], [-75, 40], [-74, 39], [-75, 39]],
    [[-75, 39], [-74, 39], [-75, 39], [-74, 39]],
])
def test_degenerate_rings_rejected_before_shared_transform(monkeypatch, ring):
    def forbidden(*args, **kwargs):
        pytest.fail("degenerate ring reached shared centroid transform")

    monkeypatch.setattr(nj, "prepare_mapped_record", forbidden)
    client = Client(centroid=False)
    client.features[0]["geometry"]["rings"] = [ring]
    report = nj.qualify(live=True, http_client=client)
    assert report["failure_reason"] == "invalid_polygon"
    assert report["technical_qualification_passed"] is False
    assert "rings" not in json.dumps(report)


def test_zero_area_inner_ring_is_also_rejected(monkeypatch):
    client = Client(centroid=False)
    client.features[0]["geometry"]["rings"].append([[-75, 39]] * 4)
    monkeypatch.setattr(nj, "prepare_mapped_record",
                        lambda *args, **kwargs: pytest.fail("invalid inner ring reached transform"))
    report = nj.qualify(live=True, http_client=client)
    assert report["failure_reason"] == "invalid_polygon"


@pytest.mark.parametrize("reverse", [False, True])
def test_nonzero_area_rings_accept_either_winding(reverse):
    geometry = Client(centroid=False).features[0]["geometry"]
    if reverse:
        geometry["rings"][0].reverse()
    point = nj._local_centroid(geometry, {"wkid": 4326})
    assert point["x"] == pytest.approx(-75.31)
    assert point["y"] == pytest.approx(39.74)


def test_request_receipt_explicitly_counts_logical_calls_not_wire_requests():
    for live in (False, True):
        client = Client()
        report = nj.qualify(live=live, http_client=client)
        assert report["network_requests_unit"] == "logical_get_bytes_operations"
        assert report["max_logical_operations"] == 7
        assert report["wire_request_count"] is None
        assert report["network_requests"] == len(client.calls)
        settings = report["default_transport_settings"]
        assert settings["max_retries"] == 0
        assert settings["timeout_seconds"] == 20
        assert settings["max_same_host_redirect_responses"] == 6
        assert settings["per_ip_failover"] is True
        assert report["http_client_injected"] is True
