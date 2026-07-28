"""Checkpointable connector for local or HTTP-hosted CSV permit feeds."""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from .base import (
    BaseConnector,
    Checkpoint,
    ConnectorResponseError,
    FetchEnvelope,
    HttpClient,
    RetryingHttpClient,
    checkpoint_offset,
)


class CSVConnector(BaseConnector):
    """Read CSV rows in pages; checkpoints are zero-based data-row offsets."""

    source_name = "csv"

    def __init__(
        self,
        source: str | Path,
        *,
        page_size: int = 1000,
        delimiter: str | None = None,
        encoding: str = "utf-8-sig",
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        http_client: HttpClient | None = None,
    ) -> None:
        super().__init__(page_size=page_size)
        if not str(source):
            raise ValueError("source is required")
        if delimiter is not None and len(delimiter) != 1:
            raise ValueError("delimiter must be one character")
        self.source = str(source)
        self.delimiter = delimiter
        self.encoding = encoding
        self.headers = dict(headers or {})
        self.http_client = http_client or RetryingHttpClient(
            timeout=timeout, max_retries=max_retries
        )

    def fetch(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
        offset = checkpoint_offset(checkpoint, key="row_offset")
        text = self._read_text()
        reader = csv.DictReader(io.StringIO(text, newline=""), dialect=self._dialect(text))
        if not reader.fieldnames:
            raise ConnectorResponseError("CSV source is missing a header row")

        records: list[dict[str, str | None]] = []
        index = -1
        for index, row in enumerate(reader):
            if index < offset:
                continue
            if len(records) >= self.page_size:
                break
            if None in row:
                raise ConnectorResponseError("CSV row has more values than the header")
            records.append(dict(row))

        # The loop consumes one look-ahead row when a full page is available.
        has_more = len(records) == self.page_size and index >= offset + self.page_size
        next_checkpoint = (
            {"row_offset": offset + len(records)} if has_more else None
        )
        return FetchEnvelope(
            source=self.source_name,
            records=tuple(records),
            checkpoint=next_checkpoint,
            has_more=has_more,
            metadata={"source": self.source, "row_offset": offset},
        )

    def _read_text(self) -> str:
        scheme = urlparse(self.source).scheme.lower()
        if scheme in {"http", "https"}:
            return self.http_client.get_text(
                self.source,
                headers={"Accept": "text/csv,*/*", **self.headers},
                encoding=self.encoding,
            )
        if scheme and scheme != "file":
            raise ConnectorResponseError(f"unsupported CSV source scheme: {scheme}")
        path = Path(urlparse(self.source).path) if scheme == "file" else Path(self.source)
        try:
            return path.read_text(encoding=self.encoding)
        except (OSError, UnicodeError) as exc:
            raise ConnectorResponseError(f"unable to read CSV source {self.source}") from exc

    def _dialect(self, text: str) -> csv.Dialect:
        if self.delimiter:
            class ConfiguredDialect(csv.excel):
                delimiter = self.delimiter

            return ConfiguredDialect
        try:
            return csv.Sniffer().sniff(text[:8192], delimiters=",\t;|")
        except csv.Error:
            return csv.excel


CsvConnector = CSVConnector
