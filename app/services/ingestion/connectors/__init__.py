"""Permit ingestion connector interfaces and built-in implementations."""

from .arcgis import ArcGISConnector, ArcGISFeatureServerConnector
from .base import (
    BaseConnector,
    Checkpoint,
    Connector,
    ConnectorError,
    ConnectorRequestError,
    ConnectorResponseError,
    FetchEnvelope,
    HttpClient,
    InvalidCheckpointError,
    Record,
    RetryingHttpClient,
)
from .civicplus_newsflash import CivicPlusNewsFlashConnector
from .ckan import CKANConnector, CKANDataStoreConnector
from .csv import CSVConnector, CsvConnector
from .factory import build_connector
from .json_array import JSONArrayConnector
from .opendatasoft import OpenDataSoftConnector, OpenDataSoftV2Connector
from .rss import RSSConnector
from .socrata import SocrataConnector

__all__ = [
    "ArcGISConnector",
    "ArcGISFeatureServerConnector",
    "BaseConnector",
    "Checkpoint",
    "Connector",
    "ConnectorError",
    "ConnectorRequestError",
    "ConnectorResponseError",
    "CKANConnector",
    "CKANDataStoreConnector",
    "CivicPlusNewsFlashConnector",
    "CSVConnector",
    "CsvConnector",
    "FetchEnvelope",
    "HttpClient",
    "InvalidCheckpointError",
    "JSONArrayConnector",
    "OpenDataSoftConnector",
    "OpenDataSoftV2Connector",
    "Record",
    "RetryingHttpClient",
    "RSSConnector",
    "SocrataConnector",
    "build_connector",
]
