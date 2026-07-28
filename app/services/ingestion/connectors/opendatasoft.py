"""Connector for OpenDataSoft v2 records endpoints."""
from __future__ import annotations

from typing import Any, Mapping

from .base import (
    BaseConnector,
    Checkpoint,
    ConnectorResponseError,
    FetchEnvelope,
    HttpClient,
    RetryingHttpClient,
    checkpoint_offset,
)


class OpenDataSoftConnector(BaseConnector):
    """Read OpenDataSoft API v2 records with offset pagination."""

    source_name = "opendatasoft"

    def __init__(
        self,
        endpoint: str,
        *,
        page_size: int = 1000,
        order_by: str | None = None,
        query: Mapping[str, Any] | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        http_client: HttpClient | None = None,
    ) -> None:
        super().__init__(page_size=page_size)
        if not endpoint:
            raise ValueError("endpoint is required")
        self.endpoint = endpoint
        self.order_by = order_by.strip() if order_by else None
        self.query = dict(query or {})
        self.http_client = http_client or RetryingHttpClient(
            timeout=timeout,
            max_retries=max_retries,
        )

    def fetch(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
        offset = checkpoint_offset(checkpoint)
        params: dict[str, Any] = {
            **self.query,
            "limit": self.page_size,
            "offset": offset,
        }
        if self.order_by:
            params["order_by"] = self.order_by

        payload = self.http_client.get_json(self.endpoint, params=params)
        if not isinstance(payload, Mapping):
            raise ConnectorResponseError("OpenDataSoft response must be an object")
        records_payload = payload.get("records")
        if not isinstance(records_payload, list):
            raise ConnectorResponseError("OpenDataSoft response is missing records")

        records = tuple(_flatten_record(row) for row in records_payload)
        total = payload.get("total_count")
        has_more = (
            offset + len(records) < total
            if isinstance(total, int) and not isinstance(total, bool)
            else len(records) == self.page_size
        )
        next_offset = offset + len(records)
        return FetchEnvelope(
            source=self.source_name,
            records=records,
            checkpoint={"offset": next_offset} if has_more else None,
            has_more=has_more,
            metadata={"endpoint": self.endpoint, "offset": offset, "total": total},
        )


def _flatten_record(row: Any) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise ConnectorResponseError("OpenDataSoft records must be objects")
    record = row.get("record")
    if not isinstance(record, Mapping):
        raise ConnectorResponseError("OpenDataSoft row is missing record object")
    fields = record.get("fields")
    if not isinstance(fields, Mapping):
        raise ConnectorResponseError("OpenDataSoft record is missing fields object")

    flattened = dict(fields)
    if record.get("id") is not None:
        flattened["_record_id"] = record["id"]
    if record.get("timestamp") is not None:
        flattened["_record_timestamp"] = record["timestamp"]
    for link in row.get("links") or ():
        if isinstance(link, Mapping) and link.get("rel") == "self" and link.get("href"):
            flattened["_record_url"] = link["href"]
            break
    return flattened


OpenDataSoftV2Connector = OpenDataSoftConnector
