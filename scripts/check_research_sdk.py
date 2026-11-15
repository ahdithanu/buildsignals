"""Offline SDK integration check: real Runner, injected client, no network or keys.

Run from the repository root in the optional agent runtime environment:
    PYTHONPATH=. python scripts/check_research_sdk.py
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import patch

from agent_runtime.research import run_research
from app.services.llm_client import LLMResult, OpenRouterClient

BUNDLE = {'schema_version': 'research-context-v1',
          'evidence_kind': 'saved_workspace_facts_not_independently_verified',
          'evidence': [{'id': 'deal:synthetic', 'text': '{"city": "Austin"}'}]}
OUTPUT = json.dumps({'facts': [{'source_id': 'deal:synthetic', 'quote': 'Austin'}],
                     'unknowns': ['Occupancy is unknown'], 'questions': ['Request rent roll']})


class FakeClient:
    def __init__(self, *, fail=False):
        self.calls = []
        self.fail = fail

    def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        assert kwargs['temperature'] == 0 and kwargs['max_tokens'] == 800
        assert kwargs['response_format'] == {'type': 'json_object'}
        if self.fail:
            raise RuntimeError('provider error must not trigger default-provider routing')
        return LLMResult(OUTPUT, 'fake/requested', 'fake/resolved', 'fake-provider',
                         1, 100, 50, 150, None, None)


async def check():
    assert version('openai-agents') == '0.24.0'
    assert version('openai') == '3.51.0'
    client = FakeClient()
    with patch.dict(os.environ, {'AGENT_RESEARCH_ENABLED': '0'}):
        try:
            await run_research(BUNDLE, client=client, execute=True)
        except ValueError as exc:
            assert str(exc) == 'research_execution_disabled'
        else:
            raise AssertionError('environment gate did not hold')
    with patch.dict(os.environ, {'AGENT_RESEARCH_ENABLED': '1'}):
        try:
            await run_research(BUNDLE, client=client)
        except ValueError:
            pass
        else:
            raise AssertionError('explicit execution gate did not hold')
        assert not client.calls
        result = await run_research(BUNDLE, client=client, execute=True)
        assert len(client.calls) == 2 and len(result['stages']) == 2
        assert result['usage'][0]['cost'] is None
        assert result['usage'][0]['served_model'] == 'fake/resolved'
        assert all('content' not in row for row in result['usage'])
        failed = FakeClient(fail=True)
        try:
            await run_research(BUNDLE, client=failed, execute=True)
        except RuntimeError:
            pass
        else:
            raise AssertionError('provider failure did not fail closed')
        assert len(failed.calls) == 1

        # Exercise the real application wrapper as well as the SDK adapter.
        requests = []

        def create(**payload):
            requests.append(payload)
            assert payload['extra_body']['models'] == ['fake/primary', 'fake/fallback']
            assert payload['extra_body']['usage'] == {'include': True}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=OUTPUT))],
                                   model='fake/resolved', provider='fake-provider',
                                   usage={'prompt_tokens': 100, 'completion_tokens': 50,
                                          'total_tokens': 150, 'cost': None}, id='offline')

        wrapped = OpenRouterClient(primary_model='fake/primary', fallback_models=['fake/fallback'],
                                   max_retries=0, timeout_seconds=30,
                                   sdk_client=SimpleNamespace(chat=SimpleNamespace(
                                       completions=SimpleNamespace(create=create))))
        result = await run_research(BUNDLE, client=wrapped, execute=True)
        assert len(requests) == 2 and result['usage'][1]['requested_model'] == 'fake/primary'

        from agent_runtime.sdk_model import OpenRouterResearchModel  # noqa: I001
        from agents.models.interface import ModelTracing

        client = FakeClient()
        model = OpenRouterResearchModel(client)
        kwargs = dict(system_instructions='', input='context', model_settings=None, tools=[],
                      output_schema=None, handoffs=[], tracing=ModelTracing.DISABLED,
                      previous_response_id=None, conversation_id=None, prompt=None)
        for changes in ({'tools': [object()]}, {'handoffs': [object()]},
                        {'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': 'x'}]}]},
                        {'tracing': ModelTracing.ENABLED}, {'previous_response_id': 'other'},
                        {'conversation_id': 'other'}, {'output_schema': object()}):
            try:
                await model.get_response(**(kwargs | changes))
            except ValueError:
                pass
            else:
                raise AssertionError('unsupported capability was accepted')
        assert not client.calls
        await model.get_response(**kwargs)
        await model.get_response(**kwargs)
        try:
            await model.get_response(**kwargs)
        except ValueError as exc:
            assert str(exc) == 'research_call_limit'
        else:
            raise AssertionError('call budget was exceeded')
        assert len(client.calls) == 2
        try:
            await anext(model.stream_response())
        except ValueError:
            pass
        else:
            raise AssertionError('streaming was accepted')


if __name__ == '__main__':
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')):
        asyncio.run(check())
    print('PASS: actual SDK Runner; two tool-free stages; both gates; failure closes; no network')
