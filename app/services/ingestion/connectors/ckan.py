"""Connector for CKAN DataStore action endpoints."""
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


class CKANDataStoreConnector(BaseConnector):
    """Read a CKAN DataStore resource with bounded offset pagination."""

    source_name = "ckan_datastore"

    def __init__(
        self,
        endpoint: str,
        *,
        resource_id: str,
        page_size: int = 1000,
        sort: str | None = None,
        query: Mapping[str, Any] | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        http_client: HttpClient | None = None,
    ) -> None:
        super().__init__(page_size=page_size)
        if not endpoint:
            raise ValueError("endpoint is required")
        if not resource_id:
            raise ValueError("resource_id is required")
        self.endpoint = endpoint
        self.resource_id = resource_id
        self.sort = sort
        self.query = dict(query or {})
        self.http_client = http_client or RetryingHttpClient(
            timeout=timeout,
            max_retries=max_retries,
        )

    def fetch(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
        offset = checkpoint_offset(checkpoint)
        params: dict[str, Any] = {
            **self.query,
            "resource_id": self.resource_id,
            "limit": self.page_size,
            "offset": offset,
        }
        if self.sort:
            params["sort"] = self.sort
        payload = self.http_client.get_json(self.endpoint, params=params)
        if not isinstance(payload, Mapping) or payload.get("success") is not True:
            raise ConnectorResponseError("CKAN response did not report success")
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise ConnectorResponseError("CKAN response is missing a result object")
        records = result.get("records")
        if not isinstance(records, list) or any(not isinstance(row, Mapping) for row in records):
            raise ConnectorResponseError("CKAN result must contain a records list")

        normalized = tuple(dict(row) for row in records)
        total = result.get("total")
        has_more = (
            offset + len(normalized) < total
            if isinstance(total, int) and not isinstance(total, bool)
            else len(normalized) == self.page_size
        )
        next_checkpoint = {"offset": offset + len(normalized)} if has_more else None
        return FetchEnvelope(
            source=self.source_name,
            records=normalized,
            checkpoint=next_checkpoint,
            has_more=has_more,
            metadata={"endpoint": self.endpoint, "offset": offset, "total": total},
        )


CKANConnector = CKANDataStoreConnector
