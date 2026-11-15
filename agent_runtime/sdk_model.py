"""SDK adapter using the application's existing OpenRouter routing and accounting."""
from __future__ import annotations

import asyncio
import os

os.environ['OPENAI_AGENTS_DISABLE_TRACING'] = '1'

from agents import Model, ModelResponse, Usage, set_tracing_disabled  # noqa: E402
from openai.types.responses import ResponseOutputMessage, ResponseOutputText  # noqa: E402

set_tracing_disabled(True)


class OpenRouterResearchModel(Model):
    def __init__(self, client):
        self.client = client
        self.receipts = []

    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, *, previous_response_id,
                           conversation_id, prompt):
        if (tools or handoffs or output_schema is not None or previous_response_id
                or conversation_id or prompt or not tracing.is_disabled()):
            raise ValueError('unsupported_agent_capability')
        if len(self.receipts) >= 2:
            raise ValueError('research_call_limit')
        messages = [{'role': 'system', 'content': system_instructions or ''}]
        if isinstance(input, str):
            messages.append({'role': 'user', 'content': input})
        else:
            for item in input:
                if (not isinstance(item, dict) or item.get('role') != 'user'
                        or not isinstance(item.get('content'), str)):
                    raise ValueError('unsupported_agent_input')
                messages.append({'role': 'user', 'content': item['content']})
        result = await asyncio.to_thread(
            self.client.chat_completion, messages=messages, temperature=0, max_tokens=800,
            response_format={'type': 'json_object'},
        )
        self.receipts.append(result)
        return ModelResponse(
            output=[ResponseOutputMessage(
                id=f'research-{len(self.receipts)}', type='message', role='assistant',
                status='completed', content=[ResponseOutputText(
                    type='output_text', text=result.content, annotations=[],
                )],
            )],
            usage=Usage(requests=1, input_tokens=result.prompt_tokens or 0,
                        output_tokens=result.completion_tokens or 0,
                        total_tokens=result.total_tokens or 0),
            response_id=None,
        )

    async def stream_response(self, *args, **kwargs):
        raise ValueError('streaming_not_supported')
        yield  # pragma: no cover
