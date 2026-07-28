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
from .csv import CSVConnector, CsvConnector
from .ckan import CKANConnector, CKANDataStoreConnector
from .json_array import JSONArrayConnector
from .opendatasoft import OpenDataSoftConnector, OpenDataSoftV2Connector
from .socrata import SocrataConnector
from .factory import build_connector

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
    "SocrataConnector",
    "build_connector",
]
