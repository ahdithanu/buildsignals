from __future__ import annotations

from email.message import Message
from typing import Mapping

import pytest

from app.services.ingestion.connectors import (
    HTMLDocumentIndexConnector,
    PlanningDocumentsConnector,
    build_connector,
)
from app.services.ingestion.connectors.base import ConnectorResponseError, RetryingHttpClient


class FakeHttpClient:
    def __init__(self, text: Mapping[str, str], documents: Mapping[str, tuple[bytes, str]]) -> None:
        self.text = text
        self.documents = documents
        self.byte_calls: list[tuple[str, int]] = []

    def get_text(self, url, *, params=None, headers=None, encoding="utf-8-sig"):
        return self.text[url]

    def get_bytes(self, url, *, max_bytes, params=None, headers=None):
        self.byte_calls.append((url, max_bytes))
        body, content_type = self.documents[url]
        if len(body) > max_bytes:
            raise ConnectorResponseError("response exceeds maximum allowed size")
        response_headers = Message()
        response_headers["Content-Type"] = content_type
        return body, response_headers


RULES = {
    "item_pattern": r"^Item\s+(?P<item_number>\d+(?:\.\d+)?)\b",
    "file_pattern": r"\b(?P<file_number>(?:SP|ER|H)\d{2}-\d{3})\b",
    "value_patterns": {
        "address": r"^Location:\s*(?P<value>.+)$",
        "owner_name": r"^Owner:\s*(?P<value>.+)$",
    },
}


def test_agenda_and_minutes_emit_shared_identity_with_document_provenance():
    index = "https://city.example.gov/hearings/"
    agenda_url = "https://city.example.gov/docs/agenda-2026-08-19.html"
    minutes_url = "https://city.example.gov/docs/minutes-2026-08-19.html"
    http = FakeHttpClient(
        {
            index: f"""
                <a href=\"{agenda_url}\">August 19, 2026 Agenda</a>
                <a href=\"{minutes_url}\">August 19, 2026 Minutes</a>
            """,
        },
        {
            agenda_url: (
                b"<html><body><p>Item 3.2</p><p>Files H23-014 / ER23-138</p>"
                b"<p>Location: 741 South Winchester Boulevard</p>"
                b"<p>Owner: SYUFY Enterprises</p>"
                b"</body></html>",
                "text/html; charset=utf-8",
            ),
            minutes_url: (
                b"<html><body><p>Item 3.2</p>"
                b"<p>Environmental file ER23-138; permit H23-014</p>"
                b"<p>Action: Approved</p></body></html>",
                "text/html",
            ),
        },
    )
    connector = PlanningDocumentsConnector(
        index,
        href_pattern=r"/docs/.*\.html$",
        page_size=1,
        max_document_bytes=4096,
        meeting_name="Planning Director Hearing",
        governing_body="City of San Jose",
        http_client=http,
        **RULES,
    )

    first_page = connector.fetch()
    second_page = connector.fetch(first_page.checkpoint)
    agenda = first_page.records[0]
    minutes = second_page.records[0]

    assert agenda["source_record_id"] == minutes["source_record_id"]
    assert agenda["event_type"] == "planning_hearing_agenda_item"
    assert agenda["stage"] == "hearing_scheduled"
    assert minutes["event_type"] == "planning_hearing_decision"
    assert minutes["stage"] == "decision_recorded"
    assert agenda["file_numbers"] == ["H23-014", "ER23-138"]
    assert agenda["reference_number"] == "H23-014"
    assert minutes["reference_number"] == "ER23-138"
    assert agenda["address"] == "741 South Winchester Boulevard"
    assert agenda["owner_name"] == "SYUFY Enterprises"
    assert agenda["source_pages"] == [1, 2, 3, 4]
    assert agenda["document_hash"] != minutes["document_hash"]
    assert agenda["meeting_at"] == "2026-08-19"
    assert agenda["meeting_name"] == "Planning Director Hearing"
    assert http.byte_calls == [(agenda_url, 4096), (minutes_url, 4096)]
    assert first_page.has_more is True
    assert second_page.has_more is False


def test_missing_or_unsupported_content_type_fails_before_segmentation():
    index = "https://city.example.gov/hearings/"
    document_url = "https://city.example.gov/docs/agenda-2026-08-19.pdf"
    http = FakeHttpClient(
        {index: f'<a href="{document_url}">August 19, 2026 Agenda</a>'},
        {document_url: (b"plain text", "text/plain")},
    )
    connector = PlanningDocumentsConnector(
        index,
        href_pattern=r"\.pdf$",
        http_client=http,
        **RULES,
    )

    with pytest.raises(ValueError, match="unsupported content type"):
        connector.fetch()


def test_factory_registers_both_document_connectors(monkeypatch):
    monkeypatch.setattr(
        "app.services.ingestion.connectors.factory.RetryingHttpClient",
        lambda **_kwargs: FakeHttpClient({}, {}),
    )
    index_connector = build_connector(
        "html_document_index",
        {
            "endpoint": "https://city.example.gov/hearings/",
            "href_pattern": r"\.pdf$",
            "max_pages": 2,
        },
    )
    planning_connector = build_connector(
        "planning_documents",
        {
            "endpoint": "https://city.example.gov/hearings/",
            "href_pattern": r"\.pdf$",
            **RULES,
            "max_documents": 12,
            "max_document_bytes": 2048,
        },
    )

    assert isinstance(index_connector, HTMLDocumentIndexConnector)
    assert index_connector.max_pages == 2
    assert isinstance(planning_connector, PlanningDocumentsConnector)
    assert planning_connector.index.max_records == 12
    assert planning_connector.max_document_bytes == 2048


def test_documents_are_same_host_by_default():
    index = "https://city.example.gov/hearings/"
    http = FakeHttpClient(
        {
            index: """
                <a href="https://documents.city.example.gov/agenda-2026-08-19.html">
                    August 19, 2026 Agenda
                </a>
            """,
        },
        {},
    )
    connector = PlanningDocumentsConnector(
        index,
        href_pattern=r"agenda.*\.html$",
        http_client=http,
        **RULES,
    )

    assert connector.fetch().records == ()
    assert http.byte_calls == []


def test_http_byte_reader_reads_only_one_byte_beyond_limit():
    class Response:
        def __init__(self) -> None:
            self.headers = Message()
            self.requested: int | None = None

        def read(self, amount=None):
            self.requested = amount
            return b"12345"

    response = Response()

    with pytest.raises(ConnectorResponseError, match="maximum allowed size"):
        RetryingHttpClient._read_response(response, max_bytes=4)

    assert response.requested == 5
