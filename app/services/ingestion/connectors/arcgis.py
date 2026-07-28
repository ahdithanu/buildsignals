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
        exceeded_limit = payload.get("exceededTransferLimit") is True
        has_more = exceeded_limit or len(records) == self.page_size
        if has_more and not records:
            raise ConnectorResponseError(
                "ArcGIS indicated another page without returning any features"
            )
        if self.keyset_field and has_more:
            last_value = records[-1].get(self.keyset_field)
            if last_value is None:
                raise ConnectorResponseError(
                    f"ArcGIS keyset row is missing cursor field: {self.keyset_field}"
                )
            next_checkpoint = {"keyset": {self.keyset_field: last_value}}
        else:
            next_checkpoint = {"offset": offset + len(records)} if has_more else None
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


# Concise alias for callers that do not need the vendor product name.
ArcGISConnector = ArcGISFeatureServerConnector
