from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app import config

log = logging.getLogger(__name__)


Message = Mapping[str, str]


@dataclass(frozen=True)
class LLMResult:
    content: str
    requested_model: str
    served_model: str | None
    provider: str | None
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cost: float | None
    response_id: str | None


def is_openrouter_configured() -> bool:
    return bool(config.OPENROUTER_API_KEY)


def _usage_value(usage: Any, key: str) -> Any:
    if usage is None:
        return None
    if isinstance(usage, Mapping):
        return usage.get(key)
    return getattr(usage, key, None)


def _response_value(response: Any, key: str) -> Any:
    if response is None:
        return None
    if isinstance(response, Mapping):
        return response.get(key)
    value = getattr(response, key, None)
    if value is not None:
        return value
    raw = getattr(response, "__dict__", {})
    if isinstance(raw, Mapping):
        return raw.get(key)
    return None


def _provider_from_response(response: Any) -> str | None:
    for key in ("provider", "provider_name", "served_by"):
        value = _response_value(response, key)
        if value:
            return str(value)
    usage = _response_value(response, "usage")
    for key in ("provider", "provider_name", "served_by"):
        value = _usage_value(usage, key)
        if value:
            return str(value)
    return None


def _is_retryable(exc: BaseException) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429 or (isinstance(status_code, int) and 500 <= status_code <= 599):
        return True
    return exc.__class__.__name__ in {"RateLimitError", "APITimeoutError", "APIConnectionError", "TimeoutException"}


def openrouter_status_code(exc: BaseException) -> int | None:
    status_code = getattr(exc, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def is_openrouter_service_error(exc: BaseException) -> bool:
    status_code = openrouter_status_code(exc)
    return (
        status_code in {402, 429}
        or (status_code is not None and 500 <= status_code <= 599)
        or exc.__class__.__name__ in {"APITimeoutError", "APIConnectionError", "TimeoutException"}
    )


def _retry_after_seconds(exc: BaseException) -> int | None:
    headers = getattr(exc, "headers", None) or getattr(getattr(exc, "response", None), "headers", None)
    if headers:
        value = headers.get("Retry-After") if hasattr(headers, "get") else None
        if value and str(value).isdigit():
            return min(int(value), 180)
    body = getattr(exc, "body", None)
    if isinstance(body, Mapping):
        metadata = body.get("metadata")
        if isinstance(metadata, Mapping):
            metadata_headers = metadata.get("headers")
            if isinstance(metadata_headers, Mapping):
                value = metadata_headers.get("Retry-After")
                if value and str(value).isdigit():
                    return min(int(value), 180)
    return None


def openrouter_retry_after_seconds(exc: BaseException) -> int | None:
    return _retry_after_seconds(exc)


class OpenRouterClient:
    """OpenAI SDK wrapper configured for OpenRouter server-side routing."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        primary_model: str | None = None,
        fallback_models: Sequence[str] | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        sdk_client: Any | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self.api_key = api_key if api_key is not None else config.OPENROUTER_API_KEY
        self.primary_model = primary_model or config.OPENROUTER_PRIMARY_MODEL
        self.fallback_models = list(
            config.OPENROUTER_FALLBACK_MODELS if fallback_models is None else fallback_models
        )
        self.timeout_seconds = (
            config.OPENROUTER_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
        )
        self.max_retries = config.OPENROUTER_MAX_RETRIES if max_retries is None else max_retries
        self._sdk_client = sdk_client
        self._sleep = sleep

    def _client(self) -> Any:
        if self._sdk_client is not None:
            return self._sdk_client
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required for OpenRouter calls")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - exercised only without dependency installed
            raise RuntimeError("The openai package is required for OpenRouter calls") from exc
        self._sdk_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key,
            timeout=self.timeout_seconds,
            max_retries=0,
        )
        return self._sdk_client

    def chat_completion(
        self,
        *,
        messages: Sequence[Message],
        primary_model: str | None = None,
        fallback_models: Sequence[str] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1_000,
        response_format: Mapping[str, Any] | None = None,
    ) -> LLMResult:
        requested_model = primary_model or self.primary_model
        fallbacks = self.fallback_models if fallback_models is None else list(fallback_models)
        extra_body: dict[str, Any] = {"usage": {"include": True}}
        if fallbacks:
            extra_body["models"] = list(dict.fromkeys([requested_model, *fallbacks]))

        payload: dict[str, Any] = {
            "model": requested_model,
            "messages": [dict(message) for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "extra_body": extra_body,
        }
        if response_format is not None:
            payload["response_format"] = dict(response_format)

        attempts = self.max_retries + 1
        last_exc: BaseException | None = None
        for attempt in range(attempts):
            started = time.perf_counter()
            try:
                response = self._client().chat.completions.create(**payload)
                latency_ms = int((time.perf_counter() - started) * 1000)
                message = response.choices[0].message
                content = getattr(message, "content", "") or ""
                usage = getattr(response, "usage", None)
                result = LLMResult(
                    content=content,
                    requested_model=requested_model,
                    served_model=_response_value(response, "model"),
                    provider=_provider_from_response(response),
                    latency_ms=latency_ms,
                    prompt_tokens=_usage_value(usage, "prompt_tokens"),
                    completion_tokens=_usage_value(usage, "completion_tokens"),
                    total_tokens=_usage_value(usage, "total_tokens"),
                    cost=_usage_value(usage, "cost"),
                    response_id=getattr(response, "id", None),
                )
                log.info(
                    "openrouter_call",
                    extra={
                        "requested_model": result.requested_model,
                        "served_model": result.served_model,
                        "provider": result.provider,
                        "latency_ms": result.latency_ms,
                        "prompt_tokens": result.prompt_tokens,
                        "completion_tokens": result.completion_tokens,
                        "total_tokens": result.total_tokens,
                        "cost": result.cost,
                    },
                )
                return result
            except Exception as exc:  # noqa: BLE001 - provider SDK exceptions vary by installed version.
                last_exc = exc
                if attempt >= attempts - 1 or not _is_retryable(exc):
                    raise
                self._sleep(_retry_after_seconds(exc) or min(2 ** attempt, 8))
        assert last_exc is not None
        raise last_exc


_DEFAULT_CLIENT: OpenRouterClient | None = None


def get_default_llm_client() -> OpenRouterClient:
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = OpenRouterClient()
    return _DEFAULT_CLIENT
