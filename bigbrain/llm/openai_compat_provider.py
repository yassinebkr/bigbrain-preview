"""OpenAI-compatible HTTP provider — OpenRouter, Mistral, Kimi direct.

Speaks the OpenAI Chat Completions wire format over httpx against any
base URL from the model registry. This covers every API-key provider in the
registry (OpenRouter models, mistral-vibe, kimi-k3) without litellm, so
reasoning deltas (``reasoning_content``) and exact usage accounting are
handled in one place.

Reasoning handling (lesson from fpga's registry): some models stream private
thinking via the ``reasoning_content`` delta field. Thinking tokens are
billed against the completion budget, so requests to reasoning models get
``max_tokens`` headroom and the reasoning effort is only sent when the entry
declares supported values.
"""

from __future__ import annotations

import base64
import json
import os
from typing import AsyncIterator, Optional

import httpx

from .model_registry import ModelEntry, get_model
from .provider import LLMProvider, MemoryToolCall
from .usage import UsageRecord, get_tracker

# Thinking shares the completion-token budget on reasoning models
# (verified on Kimi K3 and GLM in fpga): requests need reasoning-sized
# output headroom so the answer is not starved by thinking.
_REASONING_MAX_TOKENS_HEADROOM = 2048


def visible_content(content):
    """Mistral high reasoning uses chunk lists; never expose thinking chunks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ''.join(chunk['text'] for chunk in content
                       if isinstance(chunk, dict) and chunk.get('type') == 'text'
                       and isinstance(chunk.get('text'), str))
    return ''


def image_content_block(data: bytes, media_type: str) -> dict:
    """Build an OpenAI-compatible inline image content block."""
    if not media_type.startswith("image/"):
        raise ValueError("media_type must be an image MIME type")
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{encoded}"},
    }


class OpenAICompatProvider(LLMProvider):
    """Provider for any OpenAI-compatible endpoint described by the registry."""
    native_memory_tools = True

    def __init__(self, registry_key: str, api_key: Optional[str] = None):
        self.registry_key = registry_key
        self.entry: ModelEntry = get_model(registry_key)
        self.api_key = api_key or os.environ.get(self.entry.api_key_env, "")
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def reasoning_timeout_seconds(self) -> float | None:
        """Bound long-thinking calls explicitly; ordinary models keep their stage budgets."""
        if self.registry_key == 'mistral-studio-large-4' and self.entry.reasoning_effort_default == 'high':
            return None
        return 180.0 if self.entry.reasoning_effort_default == 'high' else 0.0

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.entry.base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(None if self.reasoning_timeout_seconds is None else
                                      max(120.0, self.reasoning_timeout_seconds), connect=10.0),
            )
        return self._client

    def _request_params(
        self,
        messages: list[dict],
        model: Optional[str],
        max_tokens: int,
        temperature: float,
    ) -> dict:
        """Build the completion request body from the registry entry."""
        model_id = model if model and model != "default" else self.entry.model_id
        effective_max_tokens = max_tokens
        body: dict = {
            "model": model_id,
            "messages": messages,
            "max_tokens": effective_max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if not self.entry.supports_temperature:
            body.pop('temperature', None)
        if self.entry.reasoning:
            effort = self.entry.reasoning_effort_default
            body["max_tokens"] = max_tokens + _REASONING_MAX_TOKENS_HEADROOM
            if effort and effort in self.entry.reasoning_efforts:
                body["reasoning_effort"] = effort
            if self.registry_key == 'mistral-studio-large-4' and effort == 'high':
                # The API owns its context/output limits. A local 4K/8K budget
                # must not consume thinking then starve the final tool call.
                body.pop('max_tokens', None)
                if temperature == 0:
                    # Studio's high-mode preset otherwise defaults top_p below
                    # one and rejects greedy independent-review requests (400).
                    body['top_p'] = 1
        return body

    async def complete(
        self,
        prompt: str,
        model: str = "default",
        stream: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs,
    ):
        messages = [{"role": "user", "content": prompt}]
        return await self.chat_complete(
            messages, model=model, stream=stream, max_tokens=max_tokens,
            temperature=temperature, **kwargs,
        )

    async def chat_complete(
        self,
        messages: list[dict],
        model: str = "default",
        stream: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs,
    ):
        body = self._request_params(messages, model, max_tokens, temperature)
        if kwargs.get('response_format') is not None:
            body['response_format'] = kwargs['response_format']
            if self.registry_key.startswith('openrouter-'):
                # Endpoint support, not a prompt promise. Never silently route
                # a structured protocol to an endpoint that drops its schema.
                body['provider'] = {'require_parameters': True}
        tool_schema = kwargs.get('tool_schema')
        if kwargs.get('memory_tools'):
            if tool_schema is not None or kwargs.get('response_format') is not None:
                raise ValueError('Native memory tools cannot combine with a forced action schema')
            from ..memory.shared import MEMORY_TOOL_SCHEMA
            body['tools'] = [{'type': 'function', 'function': MEMORY_TOOL_SCHEMA}]
            body['tool_choice'] = 'auto'
            body['parallel_tool_calls'] = False
            if self.registry_key.startswith('openrouter-'):
                body['provider'] = {'require_parameters': True}
        if tool_schema is not None:
            if stream or kwargs.get('response_format') is not None:
                raise ValueError('Single-action tool protocol is non-streaming and cannot combine response formats')
            body['tools'] = [{'type': 'function', 'function': tool_schema}]
            body['tool_choice'] = {'type': 'function', 'function': {'name': tool_schema['name']}}
            body['parallel_tool_calls'] = False
            if self.registry_key.startswith('openrouter-'):
                body['provider'] = {'require_parameters': True}
        if stream:
            body['stream_options'] = {'include_usage': True}
            return self._stream_chat(body)
        response = await self.client.post("/chat/completions", json=body)
        response.raise_for_status()
        data = response.json()
        self._record_usage(data, model)
        choices = data.get("choices") or [{}]
        if choices[0].get('finish_reason') == 'length':
            raise ValueError('Provider truncated generation at its token/context limit; no partial answer accepted')
        if tool_schema is not None:
            calls = (choices[0].get('message') or {}).get('tool_calls') or []
            if len(calls) != 1 or calls[0].get('function', {}).get('name') != tool_schema['name']:
                finish = choices[0].get('finish_reason')
                raise ValueError(f'Provider must return exactly the requested single tool call; received {len(calls)} calls; finish_reason={finish}; no text fallback')
            arguments = calls[0]['function'].get('arguments')
            if not isinstance(arguments, str) or not isinstance(json.loads(arguments), dict):
                raise ValueError('Native tool arguments must be a JSON object')
            return arguments
        if kwargs.get('memory_tools') and (choices[0].get('message') or {}).get('tool_calls'):
            return self._memory_call((choices[0]['message'])['tool_calls'], choices[0]['message'])
        return visible_content((choices[0].get("message") or {}).get("content"))

    @staticmethod
    def _memory_call(calls, message=None):
        if len(calls) != 1 or calls[0].get('function', {}).get('name') != 'bigbrain_memory' or not calls[0].get('id'):
            raise ValueError('Expected exactly one identified memory tool call')
        arguments = json.loads(calls[0]['function'].get('arguments', ''))
        if not isinstance(arguments, dict):
            raise ValueError('Memory tool arguments must be an object')
        normalized = [{'id': calls[0]['id'], 'type': 'function', 'function': {
            'name': 'bigbrain_memory', 'arguments': calls[0]['function']['arguments']}}]
        assistant = {'role': 'assistant', 'tool_calls': normalized, 'content': visible_content((message or {}).get('content')) or None}
        # Some reasoning providers require their private continuation metadata
        # alongside tool results. It is returned to that provider only, never
        # streamed to the UI or persisted as a chat/memory observation.
        for key in ('reasoning_content', 'reasoning_details'):
            if (message or {}).get(key):
                assistant[key] = message[key]
        return MemoryToolCall(calls[0]['id'], arguments, assistant)

    async def _stream_chat(self, body: dict) -> AsyncIterator[str]:
        """Yield text deltas from an SSE stream; record usage at stream end."""
        collected_usage: dict | None = None
        memory_calls = {}
        private_reasoning = []
        private_details = {}
        visible_parts = []
        async with self.client.stream(
            "POST", "/chat/completions", json={**body, "stream": True}
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except ValueError:
                    continue
                if chunk.get("usage"):
                    collected_usage = chunk["usage"]
                for choice in chunk.get("choices", []):
                    if choice.get('finish_reason') == 'length':
                        raise ValueError('Provider truncated generation at its token/context limit')
                    delta = choice.get("delta") or {}
                    if body.get('tools'):
                        if isinstance(delta.get('reasoning_content'), str):
                            private_reasoning.append(delta['reasoning_content'])
                        for detail in delta.get('reasoning_details') or []:
                            identity = (detail.get('index', len(private_details)), detail.get('type'))
                            target = private_details.setdefault(identity, {})
                            for key, value in detail.items():
                                target[key] = target.get(key, '') + value if key in {'text', 'data', 'signature'} and isinstance(value, str) else value
                        for call in delta.get('tool_calls') or []:
                            index = call.get('index', 0)
                            accumulated = memory_calls.setdefault(index, {'id': '', 'function': {'name': '', 'arguments': ''}})
                            accumulated['id'] += call.get('id') or ''
                            function = call.get('function') or {}
                            accumulated['function']['name'] += function.get('name') or ''
                            accumulated['function']['arguments'] += function.get('arguments') or ''
                    # reasoning_content deltas are thinking; only the visible
                    # content field is surfaced to the caller.
                    text = visible_content(delta.get("content"))
                    if text:
                        if body.get('tools'):
                            visible_parts.append(text)
                        yield text
        if collected_usage:
            get_tracker().record(
                UsageRecord.from_openai_usage(
                    collected_usage,
                    model_id=body["model"],
                    provider=self.entry.provider,
                )
            )
        if memory_calls:
            yield self._memory_call(list(memory_calls.values()), {
                'content': ''.join(visible_parts), 'reasoning_content': ''.join(private_reasoning),
                'reasoning_details': list(private_details.values())})

    def _record_usage(self, data: dict, model: str) -> None:
        usage = data.get("usage")
        if usage:
            get_tracker().record(
                UsageRecord.from_openai_usage(
                    usage,
                    model_id=body_model(data, self.entry, model),
                    provider=self.entry.provider,
                )
            )

    def get_available_models(self) -> list[str]:
        """Models this provider can serve (its registry entry by default)."""
        return [self.entry.model_id]

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate: ~4 chars per token for mixed prose/code."""
        return max(1, len(text) // 4)


def body_model(data: dict, entry: ModelEntry, model: str | None) -> str:
    """Model id reported in a response, falling back to the entry default."""
    return data.get("model") or (model if model and model != "default" else entry.model_id)
