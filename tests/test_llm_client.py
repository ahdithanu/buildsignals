from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.llm_client import OpenRouterClient


class _FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeSDKClient:
    def __init__(self, responses):
        self.chat = _FakeChat(_FakeCompletions(responses))


class _RetryableError(Exception):
    status_code = 429


class _RetryAfterError(Exception):
    status_code = 429
    headers = {"Retry-After": "999"}


def test_sdk_response_retry_after_is_honored():
    from app.services.llm_client import openrouter_retry_after_seconds

    error = _RetryableError("retry")
    error.response = SimpleNamespace(headers={"Retry-After": "45"})
    assert openrouter_retry_after_seconds(error) == 45


def _response(content: str = "ok"):
    return SimpleNamespace(
        id="resp_123",
        model="anthropic/claude-3.5-haiku",
        provider="anthropic",
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=12,
            completion_tokens=8,
            total_tokens=20,
            cost=0.00042,
        ),
    )


def test_openrouter_client_passes_fallbacks_and_usage_request():
    sdk = _FakeSDKClient([_response("hello")])
    client = OpenRouterClient(
        api_key="test",
        primary_model="openai/gpt-4o-mini",
        fallback_models=["anthropic/claude-3.5-haiku"],
        sdk_client=sdk,
    )

    result = client.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )

    call = sdk.chat.completions.calls[0]
    assert call["model"] == "openai/gpt-4o-mini"
    assert call["extra_body"]["models"] == ["openai/gpt-4o-mini", "anthropic/claude-3.5-haiku"]
    assert call["extra_body"]["usage"] == {"include": True}
    assert call["response_format"] == {"type": "json_object"}
    assert result.content == "hello"
    assert result.served_model == "anthropic/claude-3.5-haiku"
    assert result.provider == "anthropic"
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 8
    assert result.cost == 0.00042


def test_openrouter_client_retries_rate_limits():
    sdk = _FakeSDKClient([_RetryableError("slow down"), _response("after retry")])
    sleeps: list[int] = []
    client = OpenRouterClient(
        api_key="test",
        max_retries=1,
        sdk_client=sdk,
        sleep=sleeps.append,
    )

    result = client.chat_completion(messages=[{"role": "user", "content": "hi"}])

    assert result.content == "after retry"
    assert len(sdk.chat.completions.calls) == 2
    assert sleeps == [1]


def test_openrouter_client_honors_retry_after_with_cap():
    sdk = _FakeSDKClient([_RetryAfterError("slow down"), _response("after retry")])
    sleeps: list[int] = []
    client = OpenRouterClient(
        api_key="test",
        max_retries=1,
        sdk_client=sdk,
        sleep=sleeps.append,
    )

    result = client.chat_completion(messages=[{"role": "user", "content": "hi"}])

    assert result.content == "after retry"
    assert sleeps == [180]


def test_openrouter_client_honors_retry_after_from_error_body():
    error = _RetryableError("slow down")
    error.body = {"metadata": {"headers": {"Retry-After": "12"}}}
    sdk = _FakeSDKClient([error, _response("after retry")])
    sleeps: list[int] = []
    client = OpenRouterClient(
        api_key="test",
        max_retries=1,
        sdk_client=sdk,
        sleep=sleeps.append,
    )

    result = client.chat_completion(messages=[{"role": "user", "content": "hi"}])

    assert result.content == "after retry"
    assert sleeps == [12]


def test_openrouter_client_requires_key_when_creating_sdk_client():
    client = OpenRouterClient(api_key="", sdk_client=None)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        client.chat_completion(messages=[{"role": "user", "content": "hi"}])
