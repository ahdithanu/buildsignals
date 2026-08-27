"""Bounded connector for document links published on official HTML indexes."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Mapping, Pattern
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from .base import (
    BaseConnector,
    Checkpoint,
    ConnectorResponseError,
    FetchEnvelope,
    HttpClient,
    RetryingHttpClient,
    checkpoint_offset,
)

_DATE_PATTERNS = (
    re.compile(
        r"\b(?P<month>January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?"
        r"(?:,)?\s+(?P<year>20\d{2})\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?P<month>\d{1,2})[/-](?P<day>\d{1,2})[/-](?P<year>20\d{2})\b"),
    re.compile(r"\b(?P<year>20\d{2})[-_/](?P<month>\d{1,2})[-_/](?P<day>\d{1,2})\b"),
    re.compile(
        r"(?<!\d)(?P<month>\d{1,2})[/-](?P<day>\d{1,2})[/-](?P<year>\d{2})(?!\d)"
    ),
)
_DEFAULT_DOCUMENT_TYPES = {
    "agenda": re.compile(r"\bagenda\b", re.IGNORECASE),
    "minutes": re.compile(r"\bminutes?\b", re.IGNORECASE),
    "packet": re.compile(r"\bpacket\b", re.IGNORECASE),
    "notice": re.compile(r"\bnotice\b", re.IGNORECASE),
}


class HTMLDocumentIndexConnector(BaseConnector):
    """Discover allowlisted document links from a finite HTML index crawl."""

    source_name = "html_document_index"

    def __init__(
        self,
        endpoint: str,
        *,
        href_pattern: str,
        text_pattern: str | None = None,
        index_page_pattern: str | None = None,
        allowed_hosts: frozenset[str] | None = None,
        document_type_patterns: Mapping[str, str] | None = None,
        page_size: int = 100,
        max_records: int = 1000,
        max_pages: int = 1,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        http_client: HttpClient | None = None,
    ) -> None:
        super().__init__(page_size=page_size)
        self.endpoint = _canonical_http_url(endpoint)
        if isinstance(max_records, bool) or max_records < 1:
            raise ValueError("max_records must be a positive integer")
        if isinstance(max_pages, bool) or max_pages < 1:
            raise ValueError("max_pages must be a positive integer")

        endpoint_host = urlsplit(self.endpoint).hostname
        configured_hosts = (
            frozenset({endpoint_host or ""}) if allowed_hosts is None else allowed_hosts
        )
        self.allowed_hosts = frozenset(host.casefold() for host in configured_hosts if host)
        if not self.allowed_hosts:
            raise ValueError("allowed_hosts must contain at least one host")

        self.href_pattern = _compile_pattern(href_pattern, "href_pattern")
        self.text_pattern = _compile_pattern(text_pattern, "text_pattern")
        self.index_page_pattern = _compile_pattern(index_page_pattern, "index_page_pattern")
        self.document_type_patterns = _compile_document_types(document_type_patterns)
        self.max_records = max_records
        self.max_pages = max_pages
        self.headers = {"Accept": "text/html,application/xhtml+xml", **dict(headers or {})}
        self.http_client = http_client or RetryingHttpClient(
            timeout=timeout,
            max_retries=max_retries,
            allowed_hosts=self.allowed_hosts,
        )

    def fetch(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
        offset = checkpoint_offset(checkpoint)
        records, pages_fetched = self._discover()
        page = tuple(records[offset : offset + self.page_size])
        next_offset = offset + len(page)
        has_more = next_offset < len(records)
        return FetchEnvelope(
            source=self.source_name,
            records=page,
            checkpoint={"offset": next_offset} if has_more else None,
            has_more=has_more,
            metadata={
                "endpoint": self.endpoint,
                "offset": offset,
                "total": len(records),
                "index_pages_fetched": pages_fetched,
            },
        )

    def _discover(self) -> tuple[list[dict[str, str | None]], int]:
        pending = [self.endpoint]
        visited: set[str] = set()
        documents: dict[str, dict[str, str | None]] = {}

        while pending and len(visited) < self.max_pages and len(documents) < self.max_records:
            page_url = pending.pop(0)
            if page_url in visited:
                continue
            visited.add(page_url)
            body = self.http_client.get_text(page_url, headers=self.headers)
            parser = _AnchorParser()
            try:
                parser.feed(body)
                parser.close()
            except Exception as exc:
                raise ConnectorResponseError("HTML index returned malformed markup") from exc

            for href, text in parser.links:
                try:
                    resolved = _canonical_http_url(urljoin(page_url, href))
                except ValueError:
                    continue
                if not self._is_allowed(resolved):
                    continue
                searchable = f"{text} {resolved}"
                if self._matches_document(resolved, text):
                    documents.setdefault(resolved, self._record(resolved, text))
                    if len(documents) >= self.max_records:
                        break
                elif (
                    self.index_page_pattern
                    and self.index_page_pattern.search(searchable)
                    and resolved not in visited
                    and resolved not in pending
                ):
                    pending.append(resolved)

        return list(documents.values()), len(visited)

    def _matches_document(self, url: str, title: str) -> bool:
        return bool(
            self.href_pattern.search(url)
            and (self.text_pattern is None or self.text_pattern.search(title))
        )

    def _is_allowed(self, url: str) -> bool:
        host = (urlsplit(url).hostname or "").casefold()
        return any(
            host == allowed or host.endswith(f".{allowed}") for allowed in self.allowed_hosts
        )

    def _record(self, url: str, title: str) -> dict[str, str | None]:
        clean_title = " ".join(title.split()) or _title_from_url(url)
        return {
            "source_record_id": hashlib.sha256(url.encode("utf-8")).hexdigest(),
            "title": clean_title,
            "url": url,
            "document_type": self._document_type(clean_title, url),
            "meeting_date": _parse_meeting_date(f"{clean_title} {url}"),
        }

    def _document_type(self, title: str, url: str) -> str:
        searchable = f"{title} {url}"
        for document_type, pattern in self.document_type_patterns.items():
            if pattern.search(searchable):
                return document_type
        path = urlsplit(url).path
        suffix = path.rsplit(".", 1)[-1].casefold() if "." in path.rsplit("/", 1)[-1] else ""
        return suffix or "document"


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a" or self._href is not None:
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href.strip()
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None
            self._text = []


def _canonical_http_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("endpoint and discovered URLs must be non-empty strings")
    parsed = urlsplit(value.strip())
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("endpoint and discovered URLs must use HTTP or HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("endpoint and discovered URLs cannot contain credentials")
    host = parsed.hostname.casefold()
    if parsed.port and not (
        parsed.scheme.casefold() == "http"
        and parsed.port == 80
        or parsed.scheme.casefold() == "https"
        and parsed.port == 443
    ):
        host = f"{host}:{parsed.port}"
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)), doseq=True)
    return urlunsplit((parsed.scheme.casefold(), host, parsed.path or "/", query, ""))


def _compile_pattern(value: str | None, name: str) -> Pattern[str] | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty regular expression")
    try:
        return re.compile(value, re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"{name} is not a valid regular expression") from exc


def _compile_document_types(values: Mapping[str, str] | None) -> dict[str, Pattern[str]]:
    if values is None:
        return dict(_DEFAULT_DOCUMENT_TYPES)
    compiled: dict[str, Pattern[str]] = {}
    for name, value in values.items():
        pattern = _compile_pattern(value, f"document_type_patterns.{name}")
        if not name or pattern is None:
            raise ValueError("document type names and patterns must be non-empty")
        compiled[name] = pattern
    return compiled


def _parse_meeting_date(value: str) -> str | None:
    for pattern in _DATE_PATTERNS:
        match = pattern.search(value)
        if not match:
            continue
        parts = match.groupdict()
        month = parts["month"]
        try:
            if not month.isdigit():
                month = str(datetime.strptime(month[:3], "%b").month)
            year = int(parts["year"])
            if year < 100:
                year = datetime.strptime(parts["year"], "%y").year
            return date(year, int(month), int(parts["day"])).isoformat()
        except ValueError:
            continue
    return None


def _title_from_url(url: str) -> str:
    filename = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    return filename or "document"
