"""End-to-end coverage for the Biloxi planning_documents connector configuration.

These exercise the committed catalog probe_settings (loaded via qualify_biloxi)
through the real production connector: tolerant mixed-encoding index decoding,
bounded index/document bytes, host isolation, stable identities, idempotent
reruns, changed-document detection and compound-vs-single parcel handling. They
use synthetic documents, not golden source labels, and perform no network I/O.
"""
from __future__ import annotations

from email.message import Message
from typing import Mapping

import pytest

from app.services.ingestion.connectors import build_connector
from app.services.ingestion.connectors.base import ConnectorResponseError
from app.services.ingestion.connectors.planning_documents import PlanningDocumentsConnector
from scripts.qualify_biloxi import ENDPOINT, SETTINGS

AGENDA_URL = "https://biloxi.ms.us/agendas/DRC/2026/DRC-10-14-26.pdf"
OFFSITE_URL = "https://files.vendor.test/agendas/DRC/2026/DRC-10-14-26.pdf"

# cp1252 right single quote (0x92) spliced into an otherwise UTF-8 index page.
INDEX_BYTES = (
    b"<html><body>"
    b"<p>City\x92s Development Review Committee</p>"
    b'<a href="/agendas/DRC/2026/DRC-10-14-26.pdf">October 14, 2026 DRC Agenda</a>'
    b'<a href="https://files.vendor.test/agendas/DRC/2026/DRC-10-14-26.pdf">Mirror</a>'
    b"</body></html>"
)

# Two items: one single-format parcel, one compound/unresolved parcel reference.
AGENDA_HTML = (
    "<html><body>"
    "<p>1. 9:00</p><p>2026-101</p><p>New</p>"
    "<p>Example Coffee LLC</p><p>123 Example Road</p><p>1234A-01-001.000</p><p>2</p>"
    "<p>2. 9:30</p><p>2026-102</p><p>Resubmit</p>"
    "<p>Example Store</p><p>Highway 1 &amp; Example Road</p>"
    "<p>1234A-01-001.000 &amp; 1234A-01-002.000</p><p>1&amp;2</p>"
    "</body></html>"
).encode("utf-8")


class FakeHttpClient:
    def __init__(self, pages: Mapping[str, bytes]) -> None:
        self.pages = dict(pages)
        self.byte_calls: list[tuple[str, int]] = []

    def get_bytes(self, url, *, max_bytes, params=None, headers=None):
        self.byte_calls.append((url, max_bytes))
        if url not in self.pages:
            raise AssertionError(f"unexpected fetch: {url}")
        body = self.pages[url]
        if len(body) > max_bytes:
            raise ConnectorResponseError("response exceeds maximum allowed size")
        response_headers = Message()
        response_headers["Content-Type"] = "text/html; charset=utf-8"
        return body, response_headers


def _connector(pages, **overrides) -> PlanningDocumentsConnector:
    settings = {**SETTINGS, **overrides}
    return PlanningDocumentsConnector(ENDPOINT, http_client=FakeHttpClient(pages), **settings)


def test_biloxi_settings_opt_into_shared_mixed_encoding_decoder():
    assert SETTINGS["text_encoding"] == "utf-8-sig+cp1252"
    # A strict UTF-8 decode of the index would raise; the connector must not.
    with pytest.raises(UnicodeDecodeError):
        INDEX_BYTES.decode("utf-8")


def test_discovers_and_normalizes_agenda_items_over_mixed_encoding_index():
    connector = _connector({ENDPOINT: INDEX_BYTES, AGENDA_URL: AGENDA_HTML})
    records = list(connector.iter_records())

    assert [row["reference_number"] for row in records] == ["2026-101", "2026-102"]
    first, second = records
    assert first["event_type"] == "planning_hearing_agenda_item"
    assert first["stage"] == "hearing_scheduled"
    assert first["meeting_name"] == "Development Review Committee"
    assert first["meeting_date"] == "2026-10-14"
    assert first["source_url"] == AGENDA_URL
    assert first["source_pages"]
    assert len(first["document_hash"]) == 64

    # Single-format parcel reference is retained but is not a verified match.
    assert first["parcel_id"] == "1234A-01-001.000"
    # Compound reference stays unresolved rather than becoming a single identity.
    assert "parcel_id" not in second
    assert " & " in second["parcel_reference"]
    assert second["address"] == "Highway 1 & Example Road"


def test_cross_host_mirror_links_are_never_fetched():
    client = FakeHttpClient({ENDPOINT: INDEX_BYTES, AGENDA_URL: AGENDA_HTML})
    connector = PlanningDocumentsConnector(ENDPOINT, http_client=client, **SETTINGS)
    list(connector.iter_records())
    fetched = {url for url, _ in client.byte_calls}
    assert OFFSITE_URL not in fetched
    assert AGENDA_URL in fetched


def test_identities_are_stable_and_reruns_are_idempotent():
    first = list(_connector({ENDPOINT: INDEX_BYTES, AGENDA_URL: AGENDA_HTML}).iter_records())
    second = list(_connector({ENDPOINT: INDEX_BYTES, AGENDA_URL: AGENDA_HTML}).iter_records())
    assert [r["source_record_id"] for r in first] == [r["source_record_id"] for r in second]
    assert [r["document_hash"] for r in first] == [r["document_hash"] for r in second]


def test_changed_document_bytes_change_hash_but_not_identity():
    base = list(_connector({ENDPOINT: INDEX_BYTES, AGENDA_URL: AGENDA_HTML}).iter_records())
    revised_html = AGENDA_HTML.replace(b"Example Coffee LLC", b"Example Coffee Co")
    revised = list(_connector({ENDPOINT: INDEX_BYTES, AGENDA_URL: revised_html}).iter_records())

    assert base[0]["source_record_id"] == revised[0]["source_record_id"]
    assert base[0]["document_hash"] != revised[0]["document_hash"]
    assert revised[0]["project_name"] == "Example Coffee Co"


def test_index_page_byte_limit_is_enforced():
    connector = _connector(
        {ENDPOINT: INDEX_BYTES, AGENDA_URL: AGENDA_HTML},
        max_index_page_bytes=len(INDEX_BYTES) - 1,
    )
    with pytest.raises(ConnectorResponseError):
        list(connector.iter_records())


def test_document_byte_limit_is_enforced():
    connector = _connector(
        {ENDPOINT: INDEX_BYTES, AGENDA_URL: AGENDA_HTML},
        max_document_bytes=len(AGENDA_HTML) - 1,
    )
    with pytest.raises(ConnectorResponseError):
        list(connector.iter_records())


def test_factory_builds_planning_documents_with_mixed_encoding_setting():
    connector = build_connector("planning_documents", {"endpoint": ENDPOINT, **SETTINGS})
    assert isinstance(connector, PlanningDocumentsConnector)
    assert connector.index.text_encoding == "utf-8-sig+cp1252"
    assert connector.index._hybrid_decoder is not None
    assert connector.index.max_index_page_bytes == SETTINGS["max_document_bytes"]


def test_factory_rejects_invalid_encoding_settings():
    with pytest.raises(ValueError):
        build_connector(
            "html_document_index",
            {"endpoint": ENDPOINT, "href_pattern": r"\.pdf$", "text_encoding": "   "},
        )
    with pytest.raises(ValueError):
        build_connector(
            "html_document_index",
            {"endpoint": ENDPOINT, "href_pattern": r"\.pdf$", "max_index_page_bytes": 0},
        )
