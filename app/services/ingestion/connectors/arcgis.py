"""Connector for ArcGIS FeatureServer layer query endpoints."""
from __future__ import annotations

import re
from typing import Any, Mapping

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

_ARCGIS_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ArcGISFeatureServerConnector(BaseConnector):
    """Read features using ArcGIS result-offset pagination."""

    source_name = "arcgis_featureserver"

    def __init__(
        self,
        endpoint: str,
        *,
        page_size: int = 1000,
        where: str = "1=1",
        out_fields: str = "*",
        order_by_fields: str | None = None,
        keyset_field: str | None = None,
        collapse_identity_fields: tuple[str, ...] | None = None,
        collapse_recency_field: str | None = None,
        include_geometry: bool = False,
        include_centroid: bool = False,
        query: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        http_client: HttpClient | None = None,
    ) -> None:
        super().__init__(page_size=page_size)
        if not endpoint:
            raise ValueError("endpoint is required")
        self.endpoint = endpoint.rstrip("/")
        if not self.endpoint.lower().endswith("/query"):
            self.endpoint += "/query"
        self.where = where
        self.out_fields = out_fields
        self.keyset_field = keyset_field.strip() if keyset_field else None
        if self.keyset_field and not _ARCGIS_IDENTIFIER.fullmatch(self.keyset_field):
            raise ValueError("keyset_field must be a valid ArcGIS field identifier")
        keyset_order = f"{self.keyset_field} ASC" if self.keyset_field else None
        if keyset_order and order_by_fields and _normalize_order(order_by_fields) != _normalize_order(keyset_order):
            raise ValueError("order_by_fields must match ascending keyset_field")
        self.order_by_fields = keyset_order or order_by_fields
        # Optional collapse of publisher re-import snapshots: some ArcGIS layers
        # (e.g. Arlington "Issued Permits") carry several rows for one real
        # permit — each a fresh ImportDate/OBJECTID snapshot. They share the
        # derived business identity (source_record_id), so the canary's
        # duplicate-identity check rejects them even though downstream ingestion
        # upserts by source_record_id. When configured, keep only the most
        # recent row per identity (max recency_field) so the fetched batch
        # carries one row per permit. Identity/recency fields are validated as
        # ArcGIS identifiers to avoid injection into later query building.
        self.collapse_identity_fields: tuple[str, ...] = tuple(
            collapse_identity_fields or ()
        )
        self.collapse_recency_field = (
            collapse_recency_field.strip() if collapse_recency_field else None
        )
        for _field in (*self.collapse_identity_fields, *filter(None, [self.collapse_recency_field])):
            if not _ARCGIS_IDENTIFIER.fullmatch(_field):
                raise ValueError(
                    f"collapse field must be a valid ArcGIS field identifier: {_field!r}"
                )
        if self.collapse_identity_fields and not self.collapse_recency_field:
            raise ValueError(
                "collapse_recency_field is required when collapse_identity_fields is set"
            )
        self.include_geometry = include_geometry
        self.include_centroid = include_centroid
        self.query = dict(query or {})
        self.headers = dict(headers or {})
        self.http_client = http_client or RetryingHttpClient(
            timeout=timeout, max_retries=max_retries
        )

    def fetch(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
        cursor = _keyset_checkpoint(checkpoint, self.keyset_field) if self.keyset_field else None
        offset = 0 if self.keyset_field else checkpoint_offset(checkpoint)
        where = self.where
        if cursor is not None:
            where = f"({where}) AND ({self.keyset_field} > {_sql_literal(cursor)})"
        params: dict[str, Any] = {
            **self.query,
            "f": "json",
            "where": where,
            "outFields": self.out_fields,
            "returnGeometry": str(self.include_geometry or self.include_centroid).lower(),
            "resultOffset": offset,
            "resultRecordCount": self.page_size,
        }
        if self.include_centroid:
            params["returnCentroid"] = "true"
        if self.order_by_fields:
            params["orderByFields"] = self.order_by_fields

        payload = self.http_client.get_json(
            self.endpoint, params=params, headers=self.headers or None
        )
        if not isinstance(payload, Mapping):
            raise ConnectorResponseError("ArcGIS response must be an object")
        if "error" in payload:
            error = payload["error"]
            message = error.get("message") if isinstance(error, Mapping) else str(error)
            raise ConnectorResponseError(f"ArcGIS API error: {message}")
        features = payload.get("features")
        if not isinstance(features, list):
            raise ConnectorResponseError("ArcGIS response is missing a features list")

        records = tuple(self._normalize_feature(feature) for feature in features)
        raw_record_count = len(records)
        if self.keyset_field:
            records = _dedupe_keyset_records(records, self.keyset_field)
        # Pagination cursor is derived from the keyset-deduped page BEFORE the
        # identity collapse, so collapsing re-import snapshots can never drop the
        # row that carries the max keyset value (keyset) or shorten the advance
        # (offset) — either would silently skip or re-read rows.
        page_records = records
        if self.collapse_identity_fields:
            records = _collapse_latest_by_identity(
                records,
                self.collapse_identity_fields,
                self.collapse_recency_field,  # type: ignore[arg-type]
            )
        exceeded_limit = payload.get("exceededTransferLimit") is True
        has_more = exceeded_limit or raw_record_count == self.page_size
        if has_more and not page_records:
            raise ConnectorResponseError(
                "ArcGIS indicated another page without returning any features"
            )
        if self.keyset_field and has_more:
            last_value = page_records[-1].get(self.keyset_field)
            if last_value is None:
                raise ConnectorResponseError(
                    f"ArcGIS keyset row is missing cursor field: {self.keyset_field}"
                )
            next_checkpoint = {"keyset": {self.keyset_field: last_value}}
        else:
            next_checkpoint = (
                {"offset": offset + len(page_records)} if has_more else None
            )
        return FetchEnvelope(
            source=self.source_name,
            records=records,
            checkpoint=next_checkpoint,
            has_more=has_more,
            metadata={
                "endpoint": self.endpoint,
                "offset": offset,
                "spatial_reference": payload.get("spatialReference"),
            },
        )

    def _normalize_feature(self, feature: Any) -> dict[str, Any]:
        if not isinstance(feature, Mapping) or not isinstance(feature.get("attributes"), Mapping):
            raise ConnectorResponseError("ArcGIS feature is missing attributes")
        record = dict(feature["attributes"])
        if self.include_geometry and feature.get("geometry") is not None:
            geometry_key = "geometry" if "geometry" not in record else "_geometry"
            record[geometry_key] = feature["geometry"]
        if self.include_centroid and feature.get("centroid") is not None:
            centroid_key = "centroid" if "centroid" not in record else "_centroid"
            record[centroid_key] = feature["centroid"]
        return record


def _normalize_order(value: str) -> str:
    return " ".join(value.casefold().replace(",", " , ").split())


def _keyset_checkpoint(checkpoint: Checkpoint | None, field: str) -> Any:
    if checkpoint is None:
        return None
    if not isinstance(checkpoint, Mapping) or not isinstance(checkpoint.get("keyset"), Mapping):
        raise InvalidCheckpointError("checkpoint 'keyset' must be an object")
    cursor = checkpoint["keyset"]
    if set(cursor) != {field} or cursor[field] is None:
        raise InvalidCheckpointError("checkpoint keyset field does not match connector configuration")
    return cursor[field]


def _sql_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return f"'{str(value).replace(chr(39), chr(39) * 2)}'"


def _dedupe_keyset_records(
    records: tuple[dict[str, Any], ...], field: str
) -> tuple[dict[str, Any], ...]:
    """Collapse publisher join duplicates that share one pagination identity."""
    deduped: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for record in records:
        value = record.get(field)
        if value is None or value not in seen:
            deduped.append(record)
            if value is not None:
                seen.add(value)
    return tuple(deduped)


def _collapse_latest_by_identity(
    records: tuple[dict[str, Any], ...],
    identity_fields: tuple[str, ...],
    recency_field: str,
) -> tuple[dict[str, Any], ...]:
    """Keep one row per derived identity, the most recent by ``recency_field``.

    Some publishers re-import the same real record repeatedly, emitting multiple
    rows that share a business identity (the join of ``identity_fields``) but
    differ by snapshot (``recency_field``, e.g. ImportDate). They collapse to one
    source_record_id downstream, so a canary sample otherwise trips the
    duplicate-identity check. Rows whose identity fields are all present are
    collapsed keeping the max recency value (missing/incomparable recency sorts
    oldest); rows missing any identity field are passed through untouched so this
    never silently drops records it cannot key. First-seen order is preserved.
    """
    latest: dict[tuple[Any, ...], int] = {}
    recency: dict[tuple[Any, ...], Any] = {}
    order: list[tuple[Any, ...]] = []
    passthrough: list[tuple[int, dict[str, Any]]] = []
    kept: dict[tuple[Any, ...], dict[str, Any]] = {}

    for index, record in enumerate(records):
        if any(record.get(f) is None for f in identity_fields):
            passthrough.append((index, record))
            continue
        key = tuple(record.get(f) for f in identity_fields)
        value = record.get(recency_field)
        if key not in kept:
            order.append(key)
            kept[key] = record
            recency[key] = value
            latest[key] = index
            continue
        if _recency_sort_key(value) >= _recency_sort_key(recency[key]):
            kept[key] = record
            recency[key] = value
            latest[key] = index

    # Re-emit in first-seen order, interleaving untouched passthrough rows by
    # their original position so downstream ordering stays stable.
    collapsed_by_pos = {latest[key]: kept[key] for key in order}
    collapsed_by_pos.update({idx: rec for idx, rec in passthrough})
    return tuple(collapsed_by_pos[pos] for pos in sorted(collapsed_by_pos))


def _recency_sort_key(value: Any) -> tuple[int, Any]:
    """Sort key placing missing/incomparable recency values oldest."""
    if value is None:
        return (0, 0)
    if isinstance(value, bool):
        return (1, int(value))
    if isinstance(value, (int, float)):
        return (1, value)
    return (2, str(value))


# Concise alias for callers that do not need the vendor product name.
ArcGISConnector = ArcGISFeatureServerConnector
