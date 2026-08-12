from __future__ import annotations

from email.message import Message
from typing import Any, Mapping
from urllib.error import HTTPError, URLError

import pytest

from app.services.ingestion.connectors import (
    ArcGISConnector,
    CKANConnector,
    ConnectorRequestError,
    CSVConnector,
    InvalidCheckpointError,
    JSONArrayConnector,
    OpenDataSoftConnector,
    RetryingHttpClient,
    RSSConnector,
    SocrataConnector,
    build_connector,
)
from app.services.ingestion.connectors import factory as connector_factory


class FakeHttpClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, Mapping[str, Any], Mapping[str, str]]] = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append((url, params or {}, headers or {}))
        return next(self.responses)

    def get_text(self, url, *, params=None, headers=None, encoding="utf-8-sig"):
        self.calls.append((url, params or {}, headers or {}))
        return next(self.responses)


def test_socrata_returns_normalized_checkpointed_pages():
    http = FakeHttpClient([[{"id": "1"}, {"id": "2"}], [{"id": "3"}]])
    connector = SocrataConnector(
        "https://example.test/resource/permits.json",
        page_size=2,
        app_token="token",
        order_by="id",
        http_client=http,
    )

    first, second = list(connector.iter_pages())

    assert first.records == ({"id": "1"}, {"id": "2"})
    assert first.checkpoint == {"offset": 2}
    assert first.has_more is True
    assert second.records == ({"id": "3"},)
    assert second.has_more is False
    assert http.calls[0][1] == {
        "$limit": 2,
        "$offset": 0,
        "$order": "id",
    }
    assert http.calls[0][2] == {"X-App-Token": "token"}


def test_ckan_reads_datastore_records_and_uses_reported_total():
    http = FakeHttpClient([
        {"success": True, "result": {"total": 3, "records": [
            {"permit_id": "P-1"}, {"permit_id": "P-2"},
        ]}},
        {"success": True, "result": {"total": 3, "records": [
            {"permit_id": "P-3"},
        ]}},
    ])
    connector = CKANConnector(
        "https://example.test/api/3/action/datastore_search",
        resource_id="resource-1",
        page_size=2,
        sort="permit_id asc",
        http_client=http,
    )

    first, second = list(connector.iter_pages())

    assert first.records == ({"permit_id": "P-1"}, {"permit_id": "P-2"})
    assert first.checkpoint == {"offset": 2}
    assert second.has_more is False
    assert http.calls[0][1] == {
        "resource_id": "resource-1", "limit": 2, "offset": 0, "sort": "permit_id asc",
    }


def test_ckan_rejects_unsuccessful_responses():
    connector = CKANConnector(
        "https://example.test/api/3/action/datastore_search",
        resource_id="resource-1",
        http_client=FakeHttpClient([{"success": False}]),
    )
    with pytest.raises(Exception, match="did not report success"):
        connector.fetch()


def test_json_array_connector_pages_complete_array_locally():
    http = FakeHttpClient([
        [{"id": "1"}, {"id": "2"}, {"id": "3"}],
        [{"id": "1"}, {"id": "2"}, {"id": "3"}],
    ])
    connector = JSONArrayConnector(
        "https://example.test/permits.json",
        page_size=2,
        http_client=http,
    )

    first, second = list(connector.iter_pages())

    assert first.records == ({"id": "1"}, {"id": "2"})
    assert first.checkpoint == {"offset": 2}
    assert second.records == ({"id": "3"},)
    assert second.has_more is False
    assert http.calls[0][1] == {}


def test_json_array_connector_rejects_non_object_rows():
    connector = JSONArrayConnector(
        "https://example.test/permits.json",
        http_client=FakeHttpClient([[{"id": "1"}, "bad"]]),
    )

    with pytest.raises(Exception, match="list of objects"):
        connector.fetch()


def test_json_array_connector_rejects_arrays_above_configured_limit():
    connector = JSONArrayConnector(
        "https://example.test/permits.json",
        max_records=2,
        http_client=FakeHttpClient([[{"id": "1"}, {"id": "2"}, {"id": "3"}]]),
    )

    with pytest.raises(Exception, match="configured max_records is 2"):
        connector.fetch()


def test_rss_connector_parses_and_pages_public_notices():
    feed = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item><guid>notice-1</guid><title>Notice of Application</title>
        <link>https://example.test/1</link><pubDate>Fri, 31 Jul 2026 15:07:37 -0800</pubDate>
        <description>Site plan review</description></item>
      <item><guid>notice-2</guid><title>Public Hearing</title>
        <link>https://example.test/2</link><pubDate>Thu, 30 Jul 2026 10:00:00 -0800</pubDate>
        <description>Legislative hearing</description></item>
    </channel></rss>"""
    http = FakeHttpClient([feed, feed])
    connector = RSSConnector(
        "https://example.test/notices.rss",
        page_size=1,
        headers={"User-Agent": "PublicFeedClient/1.0"},
        http_client=http,
    )

    first, second = list(connector.iter_pages())

    assert first.records[0]["guid"] == "notice-1"
    assert first.records[0]["published_at"] == "Fri, 31 Jul 2026 15:07:37 -0800"
    assert first.checkpoint == {"offset": 1}
    assert second.records[0]["guid"] == "notice-2"
    assert second.has_more is False
    assert http.calls[0][2] == {
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
        "User-Agent": "PublicFeedClient/1.0",
    }


def test_rss_connector_rejects_non_feed_xml_and_document_types():
    connector = RSSConnector(
        "https://example.test/notices.rss",
        http_client=FakeHttpClient(["<html><body>not a feed</body></html>"]),
    )
    with pytest.raises(Exception, match="not an RSS or Atom feed"):
        connector.fetch()

    connector = RSSConnector(
        "https://example.test/notices.rss",
        http_client=FakeHttpClient(["<!DOCTYPE rss><rss><channel /></rss>"]),
    )
    with pytest.raises(Exception, match="document type declarations"):
        connector.fetch()


def test_rss_factory_passes_public_headers():
    connector = build_connector("rss", {
        "endpoint": "https://example.test/notices.rss",
        "page_size": 25,
        "headers": {"User-Agent": "Mozilla/5.0"},
    })

    assert isinstance(connector, RSSConnector)
    assert connector.page_size == 25
    assert connector.headers["User-Agent"] == "Mozilla/5.0"


def test_opendatasoft_returns_flattened_checkpointed_pages():
    http = FakeHttpClient([
        {
            "total_count": 3,
            "records": [
                {
                    "links": [{"rel": "self", "href": "https://example.test/r/1"}],
                    "record": {
                        "id": "hash-1",
                        "timestamp": "2026-07-17T05:55:00Z",
                        "fields": {"permitnum": "P-1", "statuscurrent": "Applied"},
                    },
                },
                {
                    "links": [{"rel": "self", "href": "https://example.test/r/2"}],
                    "record": {
                        "id": "hash-2",
                        "timestamp": "2026-07-17T05:56:00Z",
                        "fields": {"permitnum": "P-2", "statuscurrent": "Issued"},
                    },
                },
            ],
        },
        {
            "total_count": 3,
            "records": [
                {
                    "record": {
                        "id": "hash-3",
                        "timestamp": "2026-07-17T05:57:00Z",
                        "fields": {"permitnum": "P-3", "statuscurrent": "Closed"},
                    },
                }
            ],
        },
    ])
    connector = OpenDataSoftConnector(
        "https://example.test/api/v2/catalog/datasets/permits/records",
        page_size=2,
        order_by="permitnum asc",
        query={"where": "permitnum is not null"},
        http_client=http,
    )

    first, second = list(connector.iter_pages())

    assert first.records == (
        {
            "permitnum": "P-1",
            "statuscurrent": "Applied",
            "_record_id": "hash-1",
            "_record_timestamp": "2026-07-17T05:55:00Z",
            "_record_url": "https://example.test/r/1",
        },
        {
            "permitnum": "P-2",
            "statuscurrent": "Issued",
            "_record_id": "hash-2",
            "_record_timestamp": "2026-07-17T05:56:00Z",
            "_record_url": "https://example.test/r/2",
        },
    )
    assert first.checkpoint == {"offset": 2}
    assert second.records[0]["permitnum"] == "P-3"
    assert second.has_more is False
    assert http.calls[0][1] == {
        "where": "permitnum is not null",
        "limit": 2,
        "offset": 0,
        "order_by": "permitnum asc",
    }


def test_opendatasoft_rejects_missing_record_fields():
    connector = OpenDataSoftConnector(
        "https://example.test/api/v2/catalog/datasets/permits/records",
        http_client=FakeHttpClient([{"records": [{"record": {"id": "bad"}}]}]),
    )

    with pytest.raises(Exception, match="fields object"):
        connector.fetch()


def test_opendatasoft_factory_passes_configuration():
    connector = build_connector("opendatasoft", {
        "endpoint": "https://example.test/api/v2/catalog/datasets/permits/records",
        "page_size": 50,
        "order_by": "statusdate desc",
        "query": {"where": "statuscurrent is not null"},
    })

    assert isinstance(connector, OpenDataSoftConnector)
    assert connector.page_size == 50
    assert connector.order_by == "statusdate desc"
    assert connector.query == {"where": "statuscurrent is not null"}


def test_socrata_keyset_checkpoint_is_durable_and_combines_filters():
    http = FakeHttpClient([[
        {"loaded_at": "2026-07-16T01:00:00.000", "record_id": "10"},
        {"loaded_at": "2026-07-16T01:00:00.000", "record_id": "11"},
    ], [
        {"loaded_at": "2026-07-16T02:00:00.000", "record_id": "12"},
    ]])
    connector = SocrataConnector(
        "https://example.test/resource/permits.json",
        page_size=2,
        keyset_fields=["loaded_at", "record_id"],
        query={"$where": "status != 'cancelled'"},
        http_client=http,
    )

    first, second = list(connector.iter_pages())

    assert first.checkpoint == {"keyset": {
        "loaded_at": "2026-07-16T01:00:00.000",
        "record_id": "11",
    }}
    assert second.has_more is False
    assert second.checkpoint == {"keyset": {
        "loaded_at": "2026-07-16T02:00:00.000",
        "record_id": "12",
    }}
    assert http.calls[0][1]["$order"] == "loaded_at ASC, record_id ASC"
    assert http.calls[1][1]["$where"] == (
        "(status != 'cancelled') AND ((loaded_at > '2026-07-16T01:00:00.000') OR "
        "(loaded_at = '2026-07-16T01:00:00.000' AND record_id > '11'))"
    )


def test_socrata_keyset_rejects_mismatched_checkpoint():
    connector = SocrataConnector(
        "https://example.test/resource/permits.json",
        keyset_fields=["loaded_at", "record_id"],
        http_client=FakeHttpClient([]),
    )

    with pytest.raises(InvalidCheckpointError):
        connector.fetch({"keyset": {"loaded_at": "2026-07-16"}})


def test_arcgis_flattens_attributes_and_preserves_requested_geometry():
    http = FakeHttpClient(
        [
            {
                "features": [
                    {"attributes": {"OBJECTID": 7}, "geometry": {"x": 1, "y": 2}}
                ],
                "exceededTransferLimit": True,
            }
        ]
    )
    connector = ArcGISConnector(
        "https://example.test/FeatureServer/0",
        page_size=10,
        include_geometry=True,
        order_by_fields="OBJECTID",
        http_client=http,
    )

    page = connector.fetch_page()

    assert page.records == ({"OBJECTID": 7, "geometry": {"x": 1, "y": 2}},)
    assert page.next_checkpoint == {"offset": 1}
    assert http.calls[0][0].endswith("/FeatureServer/0/query")
    assert http.calls[0][1]["resultOffset"] == 0
    assert http.calls[0][1]["orderByFields"] == "OBJECTID"


def test_arcgis_preserves_requested_polygon_centroid():
    http = FakeHttpClient([{
        "features": [{
            "attributes": {"PIN": "1234567890"},
            "centroid": {"x": -122.33, "y": 47.61},
        }],
        "exceededTransferLimit": False,
    }])
    connector = ArcGISConnector(
        "https://example.test/FeatureServer/0",
        include_centroid=True,
        query={"outSR": 4326},
        http_client=http,
    )

    page = connector.fetch_page()

    assert page.records == ({
        "PIN": "1234567890",
        "centroid": {"x": -122.33, "y": 47.61},
    },)
    assert http.calls[0][1]["returnCentroid"] == "true"
    assert http.calls[0][1]["returnGeometry"] == "true"
    assert http.calls[0][1]["outSR"] == 4326


def test_arcgis_passes_configured_public_headers():
    http = FakeHttpClient([{"features": []}])
    connector = ArcGISConnector(
        "https://example.test/FeatureServer/0",
        headers={"User-Agent": "Mozilla/5.0"},
        http_client=http,
    )

    connector.fetch_page()

    assert http.calls[0][2] == {"User-Agent": "Mozilla/5.0"}


def test_arcgis_factory_passes_centroid_configuration():
    connector = build_connector("arcgis", {
        "endpoint": "https://example.test/FeatureServer/0/query",
        "include_centroid": True,
        "query": {"outSR": 4326},
    })

    assert connector.include_centroid is True
    assert connector.query == {"outSR": 4326}


def test_staging_requires_an_ingestion_host_allowlist(monkeypatch):
    monkeypatch.setattr(connector_factory, "ENVIRONMENT", "staging")
    monkeypatch.delenv("INGESTION_ALLOWED_HOSTS", raising=False)

    with pytest.raises(ValueError, match="staging and production"):
        connector_factory._production_allowed_hosts()


def test_staging_normalizes_the_ingestion_host_allowlist(monkeypatch):
    monkeypatch.setattr(connector_factory, "ENVIRONMENT", "staging")
    monkeypatch.setenv("INGESTION_ALLOWED_HOSTS", " DATA.EXAMPLE.COM,api.example.com ")

    assert connector_factory._production_allowed_hosts() == frozenset({
        "data.example.com", "api.example.com",
    })


def test_arcgis_factory_passes_public_headers():
    connector = build_connector("arcgis", {
        "endpoint": "https://example.test/FeatureServer/0/query",
        "headers": {"User-Agent": "Mozilla/5.0"},
    })

    assert connector.headers == {"User-Agent": "Mozilla/5.0"}


def test_arcgis_factory_rejects_invalid_public_headers():
    with pytest.raises(ValueError, match="'headers' must map header names"):
        build_connector("arcgis", {
            "endpoint": "https://example.test/FeatureServer/0/query",
            "headers": ["User-Agent"],
        })
    with pytest.raises(ValueError, match="'headers' keys and values"):
        build_connector("arcgis", {
            "endpoint": "https://example.test/FeatureServer/0/query",
            "headers": {"User-Agent": ""},
        })


@pytest.mark.parametrize("header", ["Host", "Proxy-Authorization", "Connection"])
def test_factory_rejects_headers_that_can_change_request_routing(header):
    with pytest.raises(ValueError, match="Connector header is not allowed"):
        build_connector("arcgis", {
            "endpoint": "https://example.test/FeatureServer/0/query",
            "headers": {header: "attacker.example"},
        })


def test_factory_rejects_header_control_characters():
    with pytest.raises(ValueError, match="control characters"):
        build_connector("arcgis", {
            "endpoint": "https://example.test/FeatureServer/0/query",
            "headers": {"X-Source": "trusted\r\nHost: attacker.example"},
        })


def test_deployed_http_client_rejects_non_public_dns(monkeypatch):
    monkeypatch.setattr(
        "app.services.ingestion.connectors.base.socket.getaddrinfo",
        lambda *_args, **_kwargs: [
            (2, 1, 6, "", ("169.254.169.254", 443)),
        ],
    )
    client = RetryingHttpClient(allowed_hosts=frozenset({"metadata.example.test"}))

    with pytest.raises(ConnectorRequestError, match="non-public address"):
        client._validate_url("https://metadata.example.test/data")


def test_deployed_http_client_accepts_exact_public_dns(monkeypatch):
    monkeypatch.setattr(
        "app.services.ingestion.connectors.base.socket.getaddrinfo",
        lambda *_args, **_kwargs: [
            (2, 1, 6, "", ("8.8.8.8", 443)),
        ],
    )
    client = RetryingHttpClient(allowed_hosts=frozenset({"data.example.test"}))

    client._validate_url("https://data.example.test/data")


def test_deployed_http_client_pins_validated_address(monkeypatch):
    connections = []
    monkeypatch.setattr(
        "app.services.ingestion.connectors.base.socket.getaddrinfo",
        lambda *_args, **_kwargs: [
            (2, 1, 6, "", ("8.8.8.8", 443)),
        ],
    )

    class Response:
        status = 200
        reason = "OK"
        headers = Message()

        @staticmethod
        def read():
            return b'{"ok": true}'

    class Connection:
        def __init__(self, host, connect_address, **kwargs):
            connections.append((host, connect_address, kwargs))

        def request(self, method, target, headers):
            assert (method, target) == ("GET", "/data")

        @staticmethod
        def getresponse():
            return Response()

        @staticmethod
        def close():
            return None

    monkeypatch.setattr(
        "app.services.ingestion.connectors.base._PinnedHTTPSConnection",
        Connection,
    )
    client = RetryingHttpClient(allowed_hosts=frozenset({"data.example.test"}))

    assert client.get_json("https://data.example.test/data") == {"ok": True}
    assert connections[0][0:2] == ("data.example.test", "8.8.8.8")


def test_deployed_http_client_rejects_cross_host_redirects(monkeypatch):
    monkeypatch.setattr(
        "app.services.ingestion.connectors.base.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("8.8.8.8", 443))],
    )

    class Response:
        status = 302
        reason = "Found"
        headers = Message()
        headers["Location"] = "https://other.example.test/data"

        @staticmethod
        def read():
            return b""

    class Connection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            pass

        @staticmethod
        def getresponse():
            return Response()

        @staticmethod
        def close():
            return None

    monkeypatch.setattr(
        "app.services.ingestion.connectors.base._PinnedHTTPSConnection",
        Connection,
    )
    client = RetryingHttpClient(allowed_hosts=frozenset({
        "data.example.test", "other.example.test",
    }))

    with pytest.raises(ConnectorRequestError, match="cross-host redirects"):
        client.get_json("https://data.example.test/data")


def test_deployed_http_client_rejects_plain_http_before_dns(monkeypatch):
    dns = []
    monkeypatch.setattr(
        "app.services.ingestion.connectors.base.socket.getaddrinfo",
        lambda *_args, **_kwargs: dns.append(True),
    )
    client = RetryingHttpClient(allowed_hosts=frozenset({"data.example.test"}))

    with pytest.raises(ConnectorRequestError, match="must use HTTPS"):
        client._validate_url("http://data.example.test/data")
    assert dns == []


def test_arcgis_keyset_paginates_without_shifting_offsets():
    http = FakeHttpClient(
        [
            {
                "features": [
                    {"attributes": {"OBJECTID": 10, "PERMIT_ID": "A"}},
                    {"attributes": {"OBJECTID": 20, "PERMIT_ID": "B"}},
                ],
                "exceededTransferLimit": True,
            },
            {
                "features": [
                    {"attributes": {"OBJECTID": 30, "PERMIT_ID": "C"}},
                ],
                "exceededTransferLimit": False,
            },
        ]
    )
    connector = ArcGISConnector(
        "https://example.test/FeatureServer/0",
        page_size=2,
        where="PERMIT_TYPE = 'Building'",
        keyset_field="OBJECTID",
        http_client=http,
    )

    pages = list(connector.iter_pages())

    assert pages[0].checkpoint == {"keyset": {"OBJECTID": 20}}
    assert pages[1].checkpoint is None
    assert http.calls[0][1]["resultOffset"] == 0
    assert http.calls[0][1]["orderByFields"] == "OBJECTID ASC"
    assert http.calls[1][1]["resultOffset"] == 0
    assert http.calls[1][1]["where"] == "(PERMIT_TYPE = 'Building') AND (OBJECTID > 20)"


def test_arcgis_keyset_rejects_mismatched_checkpoint_and_order():
    with pytest.raises(ValueError, match="order_by_fields"):
        ArcGISConnector(
            "https://example.test/FeatureServer/0",
            keyset_field="OBJECTID",
            order_by_fields="PERMIT_ID ASC",
            http_client=FakeHttpClient([]),
        )

    connector = ArcGISConnector(
        "https://example.test/FeatureServer/0",
        keyset_field="OBJECTID",
        http_client=FakeHttpClient([]),
    )
    with pytest.raises(InvalidCheckpointError):
        connector.fetch({"keyset": {"PERMIT_ID": "A"}})


def test_csv_connector_resumes_by_data_row(tmp_path):
    source = tmp_path / "permits.csv"
    source.write_text("id,address\n1,Main St\n2,Oak St\n3,Pine St\n")
    connector = CSVConnector(source, page_size=2)

    pages = list(connector.iter_pages())

    assert pages[0].records == (
        {"id": "1", "address": "Main St"},
        {"id": "2", "address": "Oak St"},
    )
    assert pages[0].checkpoint == {"row_offset": 2}
    assert pages[1].records == ({"id": "3", "address": "Pine St"},)
    assert pages[1].checkpoint is None


def test_csv_connector_preserves_newlines_inside_quoted_fields(tmp_path):
    source = tmp_path / "permits.csv"
    source.write_text('id,description\n1,"First line\nsecond line"\n2,plain\n')
    connector = CSVConnector(source, page_size=1)

    pages = list(connector.iter_pages())

    assert pages[0].records == (
        {"id": "1", "description": "First line\nsecond line"},
    )
    assert pages[1].records == ({"id": "2", "description": "plain"},)


def test_connectors_reject_invalid_checkpoints():
    connector = SocrataConnector(
        "https://example.test/resource/permits.json",
        http_client=FakeHttpClient([]),
    )

    with pytest.raises(InvalidCheckpointError):
        connector.fetch({"offset": -1})


def test_http_client_retries_transient_failures_with_timeout(monkeypatch):
    calls = []
    sleeps = []

    class Response:
        headers = Message()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise URLError("temporary")
        return Response()

    monkeypatch.setattr(
        "app.services.ingestion.connectors.base.urlopen", fake_urlopen
    )
    client = RetryingHttpClient(
        timeout=4.5, max_retries=1, backoff_seconds=0.25, sleep=sleeps.append
    )

    assert client.get_json("https://example.test/data") == {"ok": True}
    assert calls == [4.5, 4.5]
    assert sleeps == [0.25]


def test_http_client_retries_retryable_http_503_responses(monkeypatch):
    calls = []
    sleeps = []
    headers = Message()
    headers.add_header("Retry-After", "1")

    class Response:
        headers = Message()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise HTTPError(request.full_url, 503, "Service Unavailable", headers, None)
        return Response()

    monkeypatch.setattr(
        "app.services.ingestion.connectors.base.urlopen", fake_urlopen
    )
    client = RetryingHttpClient(
        timeout=4.5, max_retries=1, backoff_seconds=0.25, sleep=sleeps.append
    )

    assert client.get_json("https://example.test/data") == {"ok": True}
    assert calls == [4.5, 4.5]
    assert sleeps == [1.0]


def test_http_client_preserves_socrata_query_keys_and_encodes_soql_spaces(monkeypatch):
    requests = []

    class Response:
        headers = Message()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b"[]"

    def fake_urlopen(request, timeout):
        requests.append(request)
        return Response()

    monkeypatch.setattr(
        "app.services.ingestion.connectors.base.urlopen", fake_urlopen
    )
    client = RetryingHttpClient(timeout=4.5, max_retries=0)

    assert client.get_json(
        "https://example.test/resource/permits.json",
        params={
            "$select": "permit_number,processed_date",
            "$where": "permit_number IS NOT NULL AND plan_review_type = 'Commercial'",
        },
    ) == []

    url = requests[0].full_url
    assert "$select=" in url
    assert "%24select" not in url
    assert "permit_number%20IS%20NOT%20NULL" in url
    assert "permit_number+IS+NOT+NULL" not in url
    assert requests[0].get_header("User-agent").startswith("BuildSignals/")
