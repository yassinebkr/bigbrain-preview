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
from .provider import LLMProvider
from .usage import UsageRecord, get_tracker

# Thinking shares the completion-token budget on reasoning models
# (verified on Kimi K3 and GLM in fpga): requests need reasoning-sized
# output headroom so the answer is not starved by thinking.
_REASONING_MAX_TOKENS_HEADROOM = 2048


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

    def __init__(self, registry_key: str, api_key: Optional[str] = None):
        self.registry_key = registry_key
        self.entry: ModelEntry = get_model(registry_key)
        self.api_key = api_key or os.environ.get(self.entry.api_key_env, "")
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.entry.base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(120.0, connect=10.0),
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
            "stream_options": {"include_usage": True},
        }
        if self.entry.reasoning:
            body["max_tokens"] = max_tokens + _REASONING_MAX_TOKENS_HEADROOM
            effort = self.entry.reasoning_effort_default
            if effort and effort in self.entry.reasoning_efforts:
                body["reasoning_effort"] = effort
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
        if stream:
            return self._stream_chat(body)
        response = await self.client.post("/chat/completions", json=body)
        response.raise_for_status()
        data = response.json()
        self._record_usage(data, model)
        choices = data.get("choices") or [{}]
        return (choices[0].get("message") or {}).get("content") or ""

    async def _stream_chat(self, body: dict) -> AsyncIterator[str]:
        """Yield text deltas from an SSE stream; record usage at stream end."""
        collected_usage: dict | None = None
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
                    delta = choice.get("delta") or {}
                    # reasoning_content deltas are thinking; only the visible
                    # content field is surfaced to the caller.
                    text = delta.get("content")
                    if text:
                        yield text
        if collected_usage:
            get_tracker().record(
                UsageRecord.from_openai_usage(
                    collected_usage,
                    model_id=body["model"],
                    provider=self.entry.provider,
                )
            )

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
