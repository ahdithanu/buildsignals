"""Planning-item records extracted from bounded public meeting documents."""

from __future__ import annotations

import re
from datetime import date
from email.message import Message
from typing import Any, Mapping
from urllib.parse import urlsplit

from app.services.ingestion.planning_items import (
    PageText,
    PlanningItem,
    PlanningItemRules,
    segment_planning_items,
)
from app.services.planning_documents import extract_document

from .base import (
    BaseConnector,
    Checkpoint,
    ConnectorResponseError,
    FetchEnvelope,
    HttpClient,
    RetryingHttpClient,
    checkpoint_offset,
)
from .html_document_index import HTMLDocumentIndexConnector

_DEFAULT_EVENT_TYPES = {
    "agenda": "planning_hearing_agenda_item",
    "minutes": "planning_hearing_decision",
}
_DEFAULT_STAGES = {
    "agenda": "hearing_scheduled",
    "minutes": "decision_recorded",
}


class PlanningDocumentsConnector(BaseConnector):
    """Discover meeting documents and emit evidence-backed planning items."""

    source_name = "planning_documents"

    def __init__(
        self,
        endpoint: str,
        *,
        href_pattern: str,
        item_pattern: str,
        file_pattern: str,
        value_patterns: Mapping[str, str] | None = None,
        text_pattern: str | None = None,
        index_page_pattern: str | None = None,
        document_type_patterns: Mapping[str, str] | None = None,
        event_types: Mapping[str, str] | None = None,
        stages: Mapping[str, str] | None = None,
        suppression_patterns: list[str] | None = None,
        meeting_name: str | None = None,
        governing_body: str | None = None,
        document_allowed_hosts: frozenset[str] | None = None,
        page_size: int = 100,
        max_documents: int = 100,
        max_index_pages: int = 1,
        max_document_bytes: int = 10 * 1024 * 1024,
        max_items_per_document: int = 250,
        max_item_characters: int = 100_000,
        max_records: int = 1000,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        http_client: HttpClient | None = None,
    ) -> None:
        super().__init__(page_size=page_size)
        for name, value in {
            "max_documents": max_documents,
            "max_index_pages": max_index_pages,
            "max_document_bytes": max_document_bytes,
            "max_items_per_document": max_items_per_document,
            "max_item_characters": max_item_characters,
            "max_records": max_records,
        }.items():
            if isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

        endpoint_host = (urlsplit(endpoint).hostname or "").casefold()
        if not endpoint_host:
            raise ValueError("endpoint must use HTTP or HTTPS")
        allowed_document_hosts = (
            frozenset({endpoint_host})
            if document_allowed_hosts is None
            else frozenset(host.casefold() for host in document_allowed_hosts)
        )
        if endpoint_host not in allowed_document_hosts:
            raise ValueError("document_allowed_hosts must include the index endpoint host")
        self.document_allowed_hosts = allowed_document_hosts

        self.http_client = http_client or RetryingHttpClient(
            timeout=timeout,
            max_retries=max_retries,
            allowed_hosts=allowed_document_hosts,
        )
        self.index = HTMLDocumentIndexConnector(
            endpoint,
            href_pattern=href_pattern,
            text_pattern=text_pattern,
            index_page_pattern=index_page_pattern,
            allowed_hosts=allowed_document_hosts,
            document_type_patterns=document_type_patterns,
            page_size=max_documents,
            max_records=max_documents,
            max_pages=max_index_pages,
            headers=headers,
            timeout=timeout,
            max_retries=max_retries,
            http_client=self.http_client,
        )
        self.rules = PlanningItemRules(
            item_pattern=item_pattern,
            file_pattern=file_pattern,
            value_patterns=value_patterns or {},
        )
        self.event_types = {**_DEFAULT_EVENT_TYPES, **dict(event_types or {})}
        self.stages = {**_DEFAULT_STAGES, **dict(stages or {})}
        self.suppression_patterns = _compile_suppression_patterns(suppression_patterns)
        self.meeting_name = meeting_name
        self.governing_body = governing_body
        self.max_document_bytes = max_document_bytes
        self.max_items_per_document = max_items_per_document
        self.max_item_characters = max_item_characters
        self.max_records = max_records
        self.headers = {
            "Accept": "application/pdf,text/html,application/xhtml+xml",
            **dict(headers or {}),
        }
        self._record_cache: tuple[dict[str, Any], ...] | None = None
        self._documents_processed = 0

    def fetch(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
        offset = checkpoint_offset(checkpoint)
        if self._record_cache is None:
            records, self._documents_processed = self._records()
            self._record_cache = tuple(records)
        records = self._record_cache
        page = tuple(records[offset : offset + self.page_size])
        next_offset = offset + len(page)
        has_more = next_offset < len(records)
        return FetchEnvelope(
            source=self.source_name,
            records=page,
            checkpoint={"offset": next_offset} if has_more else None,
            has_more=has_more,
            metadata={
                "endpoint": self.index.endpoint,
                "offset": offset,
                "total": len(records),
                "documents_processed": self._documents_processed,
            },
        )

    def _records(self) -> tuple[list[dict[str, Any]], int]:
        records: list[dict[str, Any]] = []
        documents_processed = 0
        for document in self.index.iter_records():
            if len(records) >= self.max_records:
                break
            document_url = str(document["url"])
            if (
                urlsplit(document_url).hostname or ""
            ).casefold() not in self.document_allowed_hosts:
                continue
            content, response_headers = self.http_client.get_bytes(
                document_url,
                max_bytes=self.max_document_bytes,
                headers=self.headers,
            )
            content_type = _content_type(response_headers)
            extracted = extract_document(
                content,
                content_type,
                source_url=document_url,
                max_bytes=self.max_document_bytes,
            )
            meeting_date = _meeting_date(document.get("meeting_date"), document_url)
            pages = tuple(
                PageText(
                    page_number=section.page_number or section.section_number or index,
                    text=self._suppress(section.text),
                )
                for index, section in enumerate(extracted.sections, start=1)
            )
            items = segment_planning_items(
                pages,
                meeting_date=meeting_date,
                document_hash=extracted.sha256,
                source_url=document_url,
                rules=self.rules,
                max_items=self.max_items_per_document,
                max_item_characters=self.max_item_characters,
            )
            document_type = str(document.get("document_type") or "document").casefold()
            for item in items:
                records.append(self._record(item, document, document_type, extracted.content_type))
                if len(records) >= self.max_records:
                    break
            documents_processed += 1
        return records, documents_processed

    def _suppress(self, value: str) -> str:
        for pattern in self.suppression_patterns:
            value = pattern.sub("[suppressed]", value)
        return value

    def _record(
        self,
        item: PlanningItem,
        document: Mapping[str, Any],
        document_type: str,
        content_type: str,
    ) -> dict[str, Any]:
        title = str(document.get("title") or f"Planning item {item.item_number}")
        summary = " ".join(item.text.split())
        return {
            **dict(item.values),
            "source_record_id": item.identity,
            "event_type": self.event_types.get(document_type, "planning_document_item"),
            "stage": self.stages.get(document_type, "under_review"),
            "title": title,
            "summary": summary,
            "evidence_excerpt": summary[:1000],
            "agenda_item_number": item.item_number,
            "meeting_name": self.meeting_name,
            "governing_body": self.governing_body,
            "meeting_date": item.meeting_date.isoformat(),
            "meeting_at": item.meeting_date.isoformat(),
            "source_url": item.source_url,
            "source_pages": list(item.source_pages),
            "document_hash": item.document_hash,
            "document_type": document_type,
            "content_type": content_type,
            "reference_number": item.reference_number,
            "file_numbers": list(item.file_numbers),
            "extracted_values": dict(item.values),
        }


def _content_type(headers: Message | Mapping[str, str]) -> str:
    content_type = headers.get("Content-Type") or headers.get("content-type")
    if not content_type:
        raise ConnectorResponseError("planning document response is missing Content-Type")
    return str(content_type)


def _meeting_date(value: Any, source_url: str) -> date:
    if not isinstance(value, str) or not value:
        raise ConnectorResponseError(
            f"planning document link has no parseable meeting date: {source_url}"
        )
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ConnectorResponseError(
            f"planning document link has an invalid meeting date: {source_url}"
        ) from exc


def _compile_suppression_patterns(values: list[str] | None) -> tuple[re.Pattern[str], ...]:
    patterns: list[re.Pattern[str]] = []
    for value in values or []:
        try:
            patterns.append(re.compile(value, re.IGNORECASE | re.MULTILINE))
        except re.error as exc:
            raise ValueError("suppression_patterns contains an invalid regular expression") from exc
    return tuple(patterns)
