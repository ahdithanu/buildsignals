"""Connector for Socrata Open Data (SODA) resource endpoints."""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .base import (
    BaseConnector,
    Checkpoint,
    ConnectorResponseError,
    FetchEnvelope,
    HttpClient,
    InvalidCheckpointError,
    RetryingHttpClient,
    checkpoint_offset,
)

_SOQL_IDENTIFIER = re.compile(r"^[A-Za-z_:][A-Za-z0-9_:.]*$")


class SocrataConnector(BaseConnector):
    """Read a Socrata dataset with stable offset/limit checkpoints."""

    source_name = "socrata"

    def __init__(
        self,
        endpoint: str,
        *,
        page_size: int = 1000,
        app_token: str | None = None,
        order_by: str | None = None,
        keyset_fields: Sequence[str] | None = None,
        query: Mapping[str, Any] | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        http_client: HttpClient | None = None,
    ) -> None:
        super().__init__(page_size=page_size)
        if not endpoint:
            raise ValueError("endpoint is required")
        self.endpoint = endpoint
        self.app_token = app_token
        self.keyset_fields = tuple(keyset_fields or ())
        if any(not _SOQL_IDENTIFIER.fullmatch(field) for field in self.keyset_fields):
            raise ValueError("keyset fields must be valid Socrata field identifiers")
        keyset_order = ", ".join(f"{field} ASC" for field in self.keyset_fields)
        if self.keyset_fields and order_by and _normalize_order(order_by) != _normalize_order(keyset_order):
            raise ValueError("order_by must match ascending keyset_fields")
        self.order_by = keyset_order if self.keyset_fields else order_by
        self.query = dict(query or {})
        self.http_client = http_client or RetryingHttpClient(
            timeout=timeout, max_retries=max_retries
        )

    def fetch(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
        if self.keyset_fields:
            cursor = _keyset_checkpoint(checkpoint, self.keyset_fields)
            params = {**self.query, "$limit": self.page_size}
            if cursor:
                keyset_where = _keyset_where(self.keyset_fields, cursor)
                existing_where = params.get("$where")
                params["$where"] = (
                    f"({existing_where}) AND ({keyset_where})"
                    if existing_where
                    else keyset_where
                )
            offset = None
        else:
            offset = checkpoint_offset(checkpoint)
            params = {**self.query, "$limit": self.page_size, "$offset": offset}
        if self.order_by:
            params["$order"] = self.order_by
        headers = {"X-App-Token": self.app_token} if self.app_token else None
        payload = self.http_client.get_json(
            self.endpoint, params=params, headers=headers
        )
        if not isinstance(payload, list) or any(not isinstance(row, Mapping) for row in payload):
            raise ConnectorResponseError("Socrata response must be a list of objects")

        records = tuple(dict(row) for row in payload)
        has_more = len(records) == self.page_size
        if self.keyset_fields and records:
            last = records[-1]
            missing = [field for field in self.keyset_fields if last.get(field) is None]
            if missing:
                raise ConnectorResponseError(
                    f"Socrata keyset row is missing cursor fields: {missing}"
                )
            next_checkpoint = {
                "keyset": {field: last[field] for field in self.keyset_fields}
            }
        elif self.keyset_fields:
            next_checkpoint = dict(checkpoint) if checkpoint else None
        else:
            next_checkpoint = {"offset": offset + len(records)} if has_more else None
        return FetchEnvelope(
            source=self.source_name,
            records=records,
            checkpoint=next_checkpoint,
            has_more=has_more,
            metadata={"endpoint": self.endpoint, "offset": offset},
        )


def _normalize_order(value: str) -> str:
    return " ".join(value.casefold().replace(",", " , ").split())


def _keyset_checkpoint(
    checkpoint: Checkpoint | None,
    fields: tuple[str, ...],
) -> Mapping[str, Any] | None:
    if checkpoint is None:
        return None
    if not isinstance(checkpoint, Mapping) or not isinstance(checkpoint.get("keyset"), Mapping):
        raise InvalidCheckpointError("checkpoint 'keyset' must be an object")
    cursor = checkpoint["keyset"]
    if set(cursor) != set(fields) or any(cursor[field] is None for field in fields):
        raise InvalidCheckpointError("checkpoint keyset fields do not match connector configuration")
    return cursor


def _soql_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return f"'{str(value).replace(chr(39), chr(39) * 2)}'"


def _keyset_where(fields: tuple[str, ...], cursor: Mapping[str, Any]) -> str:
    branches = []
    for index, field in enumerate(fields):
        equals = [
            f"{previous} = {_soql_literal(cursor[previous])}"
            for previous in fields[:index]
        ]
        comparison = f"{field} > {_soql_literal(cursor[field])}"
        branches.append(" AND ".join([*equals, comparison]))
    return " OR ".join(f"({branch})" for branch in branches)
