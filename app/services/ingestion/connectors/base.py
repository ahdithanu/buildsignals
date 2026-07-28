"""Shared contracts and HTTP utilities for permit source connectors."""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import Message
from typing import Any, Callable, Iterator, Mapping, Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


Checkpoint = Mapping[str, Any]
Record = Mapping[str, Any]


class ConnectorError(RuntimeError):
    """Base error raised by ingestion connectors."""


class InvalidCheckpointError(ConnectorError, ValueError):
    """Raised when a checkpoint cannot be used by a connector."""


class ConnectorRequestError(ConnectorError):
    """Raised when a source cannot be reached after retries."""


class ConnectorResponseError(ConnectorError):
    """Raised when a source returns a malformed or API-error response."""


@dataclass(frozen=True)
class FetchEnvelope:
    """A normalized, checkpointable page returned by every connector."""

    source: str
    records: tuple[Record, ...]
    checkpoint: Checkpoint | None
    has_more: bool
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.has_more and self.checkpoint is None:
            raise ValueError("checkpoint is required when has_more is true")

    @property
    def next_checkpoint(self) -> Checkpoint | None:
        """Explicit alias for callers that distinguish input/output checkpoints."""
        return self.checkpoint


@runtime_checkable
class Connector(Protocol):
    """Structural interface implemented by all permit connectors."""

    source_name: str

    def fetch(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
        """Fetch one page, resuming after ``checkpoint`` when supplied."""
        ...

    def fetch_page(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
        """Alias for ``fetch`` that makes page-at-a-time use explicit."""
        ...


class BaseConnector(ABC):
    """Base implementation with safe page and record iteration helpers."""

    source_name: str

    def __init__(self, *, page_size: int) -> None:
        if page_size <= 0:
            raise ValueError("page_size must be greater than zero")
        self.page_size = page_size

    @abstractmethod
    def fetch(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
        """Fetch a single normalized page from the source."""

    def fetch_page(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
        return self.fetch(checkpoint)

    def iter_pages(
        self, checkpoint: Checkpoint | None = None
    ) -> Iterator[FetchEnvelope]:
        current = checkpoint
        while True:
            envelope = self.fetch(current)
            yield envelope
            if not envelope.has_more:
                return
            if envelope.checkpoint == current:
                raise ConnectorResponseError("connector returned a repeated checkpoint")
            current = envelope.checkpoint

    def iter_records(
        self, checkpoint: Checkpoint | None = None
    ) -> Iterator[Record]:
        for envelope in self.iter_pages(checkpoint):
            yield from envelope.records


def checkpoint_offset(
    checkpoint: Checkpoint | None, *, key: str = "offset"
) -> int:
    """Read and validate a non-negative integer offset from a checkpoint."""
    if checkpoint is None:
        return 0
    if not isinstance(checkpoint, Mapping):
        raise InvalidCheckpointError("checkpoint must be a mapping")
    value = checkpoint.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidCheckpointError(f"checkpoint '{key}' must be a non-negative integer")
    return value


class HttpClient(Protocol):
    """Injectable HTTP boundary used by network-backed connectors."""

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        ...

    def get_text(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        encoding: str = "utf-8-sig",
    ) -> str:
        ...


class RetryingHttpClient:
    """Small standard-library HTTP client with bounded transient retries."""

    RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
        allowed_hosts: frozenset[str] | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if max_retries < 0 or backoff_seconds < 0:
            raise ValueError("retry settings cannot be negative")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep
        self.allowed_hosts = allowed_hosts

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        body, _ = self._get(url, params=params, headers=headers)
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConnectorResponseError(f"invalid JSON response from {url}") from exc

    def get_text(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        encoding: str = "utf-8-sig",
    ) -> str:
        body, response_headers = self._get(url, params=params, headers=headers)
        charset = response_headers.get_content_charset() if response_headers else None
        try:
            return body.decode(charset or encoding)
        except (LookupError, UnicodeDecodeError) as exc:
            raise ConnectorResponseError(f"invalid text response from {url}") from exc

    def _get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None,
        headers: Mapping[str, str] | None,
    ) -> tuple[bytes, Message]:
        query = urlencode(params or {}, doseq=True, quote_via=quote, safe="$")
        request_url = f"{url}{'&' if '?' in url else '?'}{query}" if query else url
        self._validate_url(request_url)
        request = Request(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "BuildSignals/1.0 (+https://buildsignals.ai)",
                **dict(headers or {}),
            },
            method="GET",
        )

        for attempt in range(self.max_retries + 1):
            try:
                response_context = (
                    build_opener(_ValidatingRedirectHandler(self._validate_url)).open(
                        request, timeout=self.timeout
                    )
                    if self.allowed_hosts
                    else urlopen(request, timeout=self.timeout)
                )
                with response_context as response:
                    return response.read(), response.headers
            except HTTPError as exc:
                if exc.code not in self.RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    raise ConnectorRequestError(
                        f"GET {url} failed with HTTP {exc.code}"
                    ) from exc
                self._sleep(self._retry_delay(attempt, exc.headers))
            except (URLError, TimeoutError) as exc:
                if attempt >= self.max_retries:
                    raise ConnectorRequestError(f"GET {url} failed after retries") from exc
                self._sleep(self._retry_delay(attempt))

        raise AssertionError("retry loop exhausted unexpectedly")

    def _retry_delay(self, attempt: int, headers: Message | None = None) -> float:
        if headers:
            retry_after = headers.get("Retry-After")
            if retry_after:
                try:
                    return max(0.0, float(retry_after))
                except ValueError:
                    pass
        return self.backoff_seconds * (2**attempt)

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ConnectorRequestError("connector URL must use HTTP or HTTPS")
        if parsed.username or parsed.password:
            raise ConnectorRequestError("connector URL cannot contain credentials")
        if self.allowed_hosts and not any(
            parsed.hostname == allowed or parsed.hostname.endswith(f".{allowed}")
            for allowed in self.allowed_hosts
        ):
            raise ConnectorRequestError(f"connector host is not allowlisted: {parsed.hostname}")


class _ValidatingRedirectHandler(HTTPRedirectHandler):
    def __init__(self, validate: Callable[[str], None]) -> None:
        super().__init__()
        self._validate = validate

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self._validate(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)
