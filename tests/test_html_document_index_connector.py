from __future__ import annotations

from typing import Any, Mapping

import pytest

from app.services.ingestion.connectors.html_document_index import HTMLDocumentIndexConnector


class FakeHttpClient:
    def __init__(self, responses: Mapping[str, str]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, Mapping[str, Any], Mapping[str, str]]] = []

    def get_text(self, url, *, params=None, headers=None, encoding="utf-8-sig"):
        self.calls.append((url, params or {}, headers or {}))
        return self.responses[url]


def test_discovers_filtered_allowlisted_documents_with_stable_metadata():
    endpoint = "https://city.example.gov/hearings/"
    html = """
    <a href="/docs/agenda-2026-08-19.pdf">August 19, 2026 Agenda</a>
    <a href="/docs/minutes-08-05-2026.pdf"><span>August 5, 2026</span> Minutes</a>
    <a href="/docs/budget-2026-08-19.pdf">August 19, 2026 Budget</a>
    <a href="https://files.vendor.test/agenda.pdf">Agenda mirror</a>
    <a href="mailto:clerk@example.gov">Clerk</a>
    """
    connector = HTMLDocumentIndexConnector(
        endpoint,
        href_pattern=r"\.pdf$",
        text_pattern=r"agenda|minutes",
        http_client=FakeHttpClient({endpoint: html}),
    )

    records = list(connector.iter_records())

    assert [(row["title"], row["document_type"], row["meeting_date"]) for row in records] == [
        ("August 19, 2026 Agenda", "agenda", "2026-08-19"),
        ("August 5, 2026 Minutes", "minutes", "2026-08-05"),
    ]
    assert records[0]["url"] == "https://city.example.gov/docs/agenda-2026-08-19.pdf"
    assert len(records[0]["source_record_id"]) == 64

    repeated = list(connector.iter_records())
    assert repeated[0]["source_record_id"] == records[0]["source_record_id"]


def test_crawl_and_output_pagination_are_independently_bounded():
    first = "https://city.example.gov/hearings/"
    second = "https://city.example.gov/hearings/?page=2"
    third = "https://city.example.gov/hearings/?page=3"
    http = FakeHttpClient(
        {
            first: """
                <a href="/docs/agenda-1.pdf">2026-08-01 Agenda</a>
                <a href="?page=2">Next</a>
            """,
            second: """
                <a href="/docs/agenda-2.pdf">2026-08-02 Agenda</a>
                <a href="/docs/agenda-3.pdf">2026-08-03 Agenda</a>
                <a href="?page=3">Next</a>
            """,
            third: '<a href="/docs/agenda-4.pdf">2026-08-04 Agenda</a>',
        }
    )
    connector = HTMLDocumentIndexConnector(
        first,
        href_pattern=r"/docs/.*\.pdf$",
        index_page_pattern=r"[?&]page=\d+",
        page_size=1,
        max_records=2,
        max_pages=2,
        http_client=http,
    )

    pages = list(connector.iter_pages())

    assert [page.records[0]["meeting_date"] for page in pages] == ["2026-08-01", "2026-08-02"]
    assert pages[0].checkpoint == {"offset": 1}
    assert pages[0].has_more is True
    assert pages[1].has_more is False
    assert pages[0].metadata["index_pages_fetched"] == 2
    assert all(call[0] != third for call in http.calls)


def test_custom_document_types_and_url_canonicalization_deduplicate_links():
    endpoint = "https://city.example.gov/index"
    connector = HTMLDocumentIndexConnector(
        endpoint,
        href_pattern=r"showpublisheddocument",
        document_type_patterns={"staff_report": r"staff\s+report"},
        allowed_hosts=frozenset({"city.example.gov", "cdn.example.gov"}),
        http_client=FakeHttpClient(
            {
                endpoint: """
                    <a href="https://cdn.example.gov/showpublisheddocument?b=2&amp;a=1#page=3">
                      Staff Report
                    </a>
                    <a href="https://cdn.example.gov/showpublisheddocument?a=1&amp;b=2">
                      Staff Report duplicate
                    </a>
                """
            }
        ),
    )

    records = list(connector.iter_records())

    assert len(records) == 1
    assert records[0]["document_type"] == "staff_report"
    assert records[0]["url"] == "https://cdn.example.gov/showpublisheddocument?a=1&b=2"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"href_pattern": "["}, "href_pattern is not a valid regular expression"),
        ({"href_pattern": r"\.pdf$", "max_pages": 0}, "max_pages must be a positive integer"),
        (
            {"href_pattern": r"\.pdf$", "allowed_hosts": frozenset()},
            "allowed_hosts must contain at least one host",
        ),
    ],
)
def test_rejects_invalid_bounds_and_patterns(kwargs, message):
    with pytest.raises(ValueError, match=message):
        HTMLDocumentIndexConnector("https://city.example.gov", **kwargs)
