"""Connector for endpoints that return a complete JSON array."""
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


class JSONArrayConnector(BaseConnector):
    """Read simple JSON array endpoints with local offset slicing."""

    source_name = "json_array"

    def __init__(
        self,
        endpoint: str,
        *,
        page_size: int = 1000,
        max_records: int = 10000,
        query: Mapping[str, Any] | None = None,
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
        self.http_client = http_client or RetryingHttpClient(
            timeout=timeout,
            max_retries=max_retries,
        )

    def fetch(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
        offset = checkpoint_offset(checkpoint)
        payload = self.http_client.get_json(self.endpoint, params=self.query)
        if not isinstance(payload, list) or any(
            not isinstance(row, Mapping) for row in payload
        ):
            raise ConnectorResponseError("JSON array endpoint must return a list of objects")
        if len(payload) > self.max_records:
            raise ConnectorResponseError(
                f"JSON array endpoint returned {len(payload)} records; "
                f"configured max_records is {self.max_records}"
            )

        records = tuple(dict(row) for row in payload[offset:offset + self.page_size])
        next_offset = offset + len(records)
        has_more = next_offset < len(payload)
        return FetchEnvelope(
            source=self.source_name,
            records=records,
            checkpoint={"offset": next_offset} if has_more else None,
            has_more=has_more,
            metadata={"endpoint": self.endpoint, "offset": offset, "total": len(payload)},
        )
