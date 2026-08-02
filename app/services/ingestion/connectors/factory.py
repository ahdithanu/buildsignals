from __future__ import annotations

import os
from typing import Any, Mapping
from urllib.parse import urlparse

from app.config import IS_PRODUCTION

from .arcgis import ArcGISConnector
from .base import Connector, RetryingHttpClient
from .ckan import CKANConnector
from .csv import CSVConnector
from .json_array import JSONArrayConnector
from .opendatasoft import OpenDataSoftConnector
from .rss import RSSConnector
from .socrata import SocrataConnector


def build_connector(connector_type: str, config: Mapping[str, Any]) -> Connector:
    """Build a connector from non-secret registry configuration."""
    connector_type = connector_type.strip().lower()
    allowed_hosts = _production_allowed_hosts()
    common = {
        "page_size": int(config.get("page_size", 1000)),
        "timeout": float(config.get("timeout", 30.0)),
        "max_retries": int(config.get("max_retries", 3)),
        "http_client": RetryingHttpClient(
            timeout=float(config.get("timeout", 30.0)),
            max_retries=int(config.get("max_retries", 3)),
            allowed_hosts=allowed_hosts,
        ),
    }

    if connector_type == "socrata":
        return SocrataConnector(
            _required(config, "endpoint"),
            app_token=_secret_from_env(config, "app_token_env"),
            order_by=config.get("order_by"),
            keyset_fields=_string_list(config.get("keyset_fields"), "keyset_fields"),
            query=_mapping(config.get("query")),
            **common,
        )
    if connector_type in {"arcgis", "arcgis_featureserver"}:
        return ArcGISConnector(
            _required(config, "endpoint"),
            where=str(config.get("where", "1=1")),
            out_fields=str(config.get("out_fields", "*")),
            order_by_fields=config.get("order_by_fields"),
            keyset_field=config.get("keyset_field"),
            include_geometry=bool(config.get("include_geometry", False)),
            include_centroid=bool(config.get("include_centroid", False)),
            query=_mapping(config.get("query")),
            headers=_public_headers(config),
            **common,
        )
    if connector_type in {"ckan", "ckan_datastore"}:
        return CKANConnector(
            _required(config, "endpoint"),
            resource_id=_required(config, "resource_id"),
            sort=config.get("sort"),
            query=_mapping(config.get("query")),
            **common,
        )
    if connector_type in {"json_array", "json"}:
        return JSONArrayConnector(
            _required(config, "endpoint"),
            max_records=int(config.get("max_records", 10000)),
            query=_mapping(config.get("query")),
            **common,
        )
    if connector_type in {"rss", "rss2", "atom"}:
        return RSSConnector(
            _required(config, "endpoint"),
            max_records=int(config.get("max_records", 1000)),
            query=_mapping(config.get("query")),
            headers=_public_headers(config),
            **common,
        )
    if connector_type in {"opendatasoft", "opendatasoft_v2"}:
        return OpenDataSoftConnector(
            _required(config, "endpoint"),
            order_by=config.get("order_by"),
            query=_mapping(config.get("query")),
            **common,
        )
    if connector_type == "csv":
        source = _required(config, "source")
        if IS_PRODUCTION and urlparse(source).scheme.lower() not in {"http", "https"}:
            raise ValueError("Production CSV sources must use HTTPS or HTTP")
        return CSVConnector(
            source,
            delimiter=config.get("delimiter"),
            encoding=str(config.get("encoding", "utf-8-sig")),
            headers=_secret_headers(config),
            **common,
        )
    raise ValueError(f"Unsupported connector type: {connector_type}")


def _required(config: Mapping[str, Any], key: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Connector configuration requires '{key}'")
    return value.strip()


def _mapping(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("Connector query configuration must be an object")
    return value


def _string_list(value: Any, key: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"Connector '{key}' must be a non-empty list of strings")
    return [item.strip() for item in value]


def _secret_from_env(config: Mapping[str, Any], key: str) -> str | None:
    env_name = config.get(key)
    if env_name is None:
        return None
    if not isinstance(env_name, str) or not env_name.strip():
        raise ValueError(f"'{key}' must name an environment variable")
    value = os.environ.get(env_name)
    if value is None:
        raise ValueError(f"Required connector secret environment variable is not set: {env_name}")
    return value


def _secret_headers(config: Mapping[str, Any]) -> dict[str, str]:
    header_env = config.get("header_env")
    if header_env is None:
        return {}
    if not isinstance(header_env, Mapping):
        raise ValueError("'header_env' must map header names to environment variables")
    headers: dict[str, str] = {}
    for header, env_name in header_env.items():
        if not isinstance(header, str) or not isinstance(env_name, str):
            raise ValueError("'header_env' keys and values must be strings")
        value = os.environ.get(env_name)
        if value is None:
            raise ValueError(f"Required connector secret environment variable is not set: {env_name}")
        headers[header] = value
    return headers


def _public_headers(config: Mapping[str, Any]) -> dict[str, str]:
    value = config.get("headers")
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("'headers' must map header names to literal values")
    headers: dict[str, str] = {}
    for header, header_value in value.items():
        if (
            not isinstance(header, str)
            or not header.strip()
            or not isinstance(header_value, str)
            or not header_value.strip()
        ):
            raise ValueError("'headers' keys and values must be non-empty strings")
        headers[header.strip()] = header_value.strip()
    return headers


def _production_allowed_hosts() -> frozenset[str] | None:
    if not IS_PRODUCTION:
        return None
    hosts = frozenset(
        host.strip().lower()
        for host in os.environ.get("INGESTION_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    )
    if not hosts:
        raise ValueError("INGESTION_ALLOWED_HOSTS must be configured in production")
    return hosts
