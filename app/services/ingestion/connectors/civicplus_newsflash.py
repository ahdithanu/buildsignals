"""Connector for public CivicPlus NewsFlash category archives."""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Mapping
from urllib.parse import urljoin

from .base import (
    BaseConnector,
    Checkpoint,
    ConnectorResponseError,
    FetchEnvelope,
    HttpClient,
    RetryingHttpClient,
    checkpoint_offset,
)

_ARTICLE_ID = re.compile(r"^list-articles-category-(?P<category>\d+)-(?P<article>\d+)$")
_POSTED_ON = re.compile(r"\bPosted on\s+(.+?)(?:\s*\|\s*Last Updated.*)?$", re.IGNORECASE)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(
    r"(?<!\d)(?:\+?1[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]?\d{3}[ .-]?\d{4}(?!\d)"
)


class CivicPlusNewsFlashConnector(BaseConnector):
    """Read a current NewsFlash category window without following article links."""

    source_name = "civicplus_newsflash"

    def __init__(
        self,
        endpoint: str,
        *,
        category_id: int,
        page_size: int = 100,
        max_records: int = 100,
        max_description_chars: int = 2000,
        query: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        http_client: HttpClient | None = None,
    ) -> None:
        super().__init__(page_size=page_size)
        if not endpoint:
            raise ValueError("endpoint is required")
        if isinstance(category_id, bool) or category_id < 1:
            raise ValueError("category_id must be a positive integer")
        if isinstance(max_records, bool) or max_records < 1:
            raise ValueError("max_records must be a positive integer")
        if isinstance(max_description_chars, bool) or max_description_chars < 1:
            raise ValueError("max_description_chars must be a positive integer")
        self.endpoint = endpoint
        self.category_id = category_id
        self.max_records = max_records
        self.max_description_chars = max_description_chars
        self.query = {"cat": category_id, **dict(query or {})}
        self.headers = {
            "Accept": "text/html,application/xhtml+xml",
            **dict(headers or {}),
        }
        self.http_client = http_client or RetryingHttpClient(
            timeout=timeout,
            max_retries=max_retries,
        )

    def fetch(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
        offset = checkpoint_offset(checkpoint)
        body = self.http_client.get_text(
            self.endpoint,
            params=self.query,
            headers=self.headers,
        )
        records = _parse_newsflash(
            body,
            endpoint=self.endpoint,
            category_id=self.category_id,
            max_description_chars=self.max_description_chars,
        )
        if len(records) > self.max_records:
            raise ConnectorResponseError(
                f"CivicPlus archive returned {len(records)} records; "
                f"configured max_records is {self.max_records}"
            )

        page = tuple(records[offset:offset + self.page_size])
        next_offset = offset + len(page)
        has_more = next_offset < len(records)
        return FetchEnvelope(
            source=self.source_name,
            records=page,
            checkpoint={"offset": next_offset} if has_more else None,
            has_more=has_more,
            metadata={
                "endpoint": self.endpoint,
                "category_id": self.category_id,
                "offset": offset,
                "total": len(records),
            },
        )


@dataclass
class _Article:
    article_id: str
    title: str = ""
    link: str = ""
    published_at: str = ""
    description: str = ""


class _NewsFlashParser(HTMLParser):
    def __init__(self, *, endpoint: str, category_id: int) -> None:
        super().__init__(convert_charrefs=True)
        self.endpoint = endpoint
        self.category_id = str(category_id)
        self.category_seen = False
        self.records: list[_Article] = []
        self._article: _Article | None = None
        self._article_li_depth = 0
        self._title_depth = 0
        self._description_depth = 0
        self._published_depth = 0
        self._title: list[str] = []
        self._description: list[str] = []
        self._published: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        element_id = attributes.get("id", "")
        if element_id == f"articles-category-{self.category_id}":
            self.category_seen = True

        match = _ARTICLE_ID.fullmatch(element_id)
        if (
            self._article is None
            and tag == "li"
            and match
            and match.group("category") == self.category_id
        ):
            self._article = _Article(article_id=match.group("article"))
            self._article_li_depth = 1
        elif self._article is not None and tag == "li":
            self._article_li_depth += 1

        if self._article is None:
            return
        classes = set((attributes.get("class") or "").split())
        if self._title_depth:
            self._title_depth += 1
        elif tag == "a" and "article-title-link" in classes:
            self._title_depth = 1
            self._article.link = urljoin(self.endpoint, attributes.get("href") or "")
        if self._description_depth:
            self._description_depth += 1
        elif "article-preview" in classes:
            self._description_depth = 1
        if self._published_depth:
            self._published_depth += 1
        elif "fst-italic" in classes and "text-body-secondary" in classes:
            self._published_depth = 1

    def handle_endtag(self, tag: str) -> None:
        if self._article is None:
            return
        if self._title_depth:
            self._title_depth -= 1
        if self._description_depth:
            self._description_depth -= 1
        if self._published_depth:
            self._published_depth -= 1
        if tag == "li":
            self._article_li_depth -= 1
        if tag == "li" and self._article_li_depth == 0:
            self._article.title = _clean_text(self._title)
            self._article.description = _clean_text(self._description)
            posted = _clean_text(self._published)
            match = _POSTED_ON.search(posted)
            self._article.published_at = match.group(1).strip() if match else ""
            self.records.append(self._article)
            self._article = None
            self._article_li_depth = 0
            self._title.clear()
            self._description.clear()
            self._published.clear()
            self._title_depth = 0
            self._description_depth = 0
            self._published_depth = 0

    def handle_data(self, data: str) -> None:
        if self._title_depth:
            self._title.append(data)
        if self._description_depth:
            self._description.append(data)
        if self._published_depth:
            self._published.append(data)


def _parse_newsflash(
    body: str,
    *,
    endpoint: str,
    category_id: int,
    max_description_chars: int,
) -> list[dict[str, str]]:
    parser = _NewsFlashParser(endpoint=endpoint, category_id=category_id)
    parser.feed(body)
    parser.close()
    if not parser.category_seen:
        raise ConnectorResponseError(
            f"CivicPlus response did not contain category {category_id}"
        )
    return [
        {
            "article_id": article.article_id,
            "title": article.title,
            "link": article.link,
            "published_at": article.published_at,
            "description": _redact_contacts(article.description)[:max_description_chars].strip(),
        }
        for article in parser.records
    ]


def _clean_text(parts: list[str]) -> str:
    return " ".join("".join(parts).split())


def _redact_contacts(value: str) -> str:
    return _PHONE.sub("[phone suppressed]", _EMAIL.sub("[email suppressed]", value))
