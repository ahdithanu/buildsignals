"""Connector for finite RSS 2.0 and Atom feeds."""
from __future__ import annotations

from typing import Any, Mapping
from xml.etree import ElementTree

from .base import (
    BaseConnector,
    Checkpoint,
    ConnectorResponseError,
    FetchEnvelope,
    HttpClient,
    RetryingHttpClient,
    checkpoint_offset,
)


class RSSConnector(BaseConnector):
    """Read a public syndication feed with local offset pagination."""

    source_name = "rss"

    def __init__(
        self,
        endpoint: str,
        *,
        page_size: int = 100,
        max_records: int = 1000,
        query: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        http_client: HttpClient | None = None,
    ) -> None:
        super().__init__(page_size=page_size)
        if not endpoint:
            raise ValueError("endpoint is required")
        if isinstance(max_records, bool) or max_records < 1:
            raise ValueError("max_records must be a positive integer")
        self.endpoint = endpoint
        self.max_records = max_records
        self.query = dict(query or {})
        self.headers = {
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
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
        records = _parse_feed(body)
        if len(records) > self.max_records:
            raise ConnectorResponseError(
                f"RSS endpoint returned {len(records)} records; "
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
            metadata={"endpoint": self.endpoint, "offset": offset, "total": len(records)},
        )


def _parse_feed(body: str) -> list[dict[str, str]]:
    if "<!DOCTYPE" in body.upper() or "<!ENTITY" in body.upper():
        raise ConnectorResponseError("RSS response cannot contain document type declarations")
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        raise ConnectorResponseError("RSS endpoint returned malformed XML") from exc

    root_name = _local_name(root.tag).casefold()
    if root_name == "rss":
        items = [node for node in root.iter() if _local_name(node.tag) == "item"]
        return [_rss_item(node) for node in items]
    if root_name == "feed":
        entries = [node for node in root if _local_name(node.tag) == "entry"]
        return [_atom_entry(node) for node in entries]
    raise ConnectorResponseError("XML response is not an RSS or Atom feed")


def _rss_item(node: ElementTree.Element) -> dict[str, str]:
    return {
        "guid": _child_text(node, "guid"),
        "title": _child_text(node, "title"),
        "link": _child_text(node, "link"),
        "published_at": _child_text(node, "pubDate"),
        "description": _child_text(node, "description"),
    }


def _atom_entry(node: ElementTree.Element) -> dict[str, str]:
    link = ""
    for child in node:
        if _local_name(child.tag) == "link" and child.attrib.get("href"):
            if child.attrib.get("rel", "alternate") == "alternate":
                link = child.attrib["href"].strip()
                break
    return {
        "guid": _child_text(node, "id"),
        "title": _child_text(node, "title"),
        "link": link,
        "published_at": _child_text(node, "published") or _child_text(node, "updated"),
        "description": _child_text(node, "summary") or _child_text(node, "content"),
    }


def _child_text(node: ElementTree.Element, name: str) -> str:
    for child in node:
        if _local_name(child.tag) == name:
            return "".join(child.itertext()).strip()
    return ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
