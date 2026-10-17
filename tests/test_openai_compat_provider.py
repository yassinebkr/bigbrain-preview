"""Tests for the OpenAI-compatible provider (Phase 3).

Uses httpx.MockTransport — no network, no paid calls.
"""

import json

import httpx
import pytest

from bigbrain.llm.openai_compat_provider import OpenAICompatProvider
from bigbrain.llm.usage import UsageTracker, set_tracker_for_test


class _SSEHandler:
    """Serves one scripted non-stream or SSE stream response."""

    def __init__(self, *, content="hello", usage=None):
        self.content = content
        self.usage = usage or {}
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body = json.loads(request.content)
        if body.get("stream"):
            chunks = []
            for piece in (self.content[:3], self.content[3:]):
                delta = {"choices": [{"delta": {"content": piece}}]}
                chunks.append(f"data: {json.dumps(delta)}\n\n")
            chunks.append(
                f"data: {json.dumps({'choices': [], 'usage': self.usage})}\n\n"
            )
            chunks.append("data: [DONE]\n\n")
            return httpx.Response(
                200, text="".join(chunks),
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={
            "model": body["model"],
            "choices": [{"message": {"content": self.content}}],
            "usage": self.usage,
        })


@pytest.fixture(autouse=True)
def clean_tracker():
    set_tracker_for_test(UsageTracker())
    yield
    set_tracker_for_test(UsageTracker())


def _provider(handler, key="openrouter-gpt-sol", monkeypatch=None):
    provider = OpenAICompatProvider(key)
    provider.api_key = "test-key"
    provider._client = httpx.AsyncClient(
        base_url=provider.entry.base_url,
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer test-key"},
    )
    return provider


@pytest.mark.asyncio
async def test_non_stream_completion():
    handler = _SSEHandler(
        content="answer",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    provider = _provider(handler)
    result = await provider.chat_complete([{"role": "user", "content": "hi"}])
    assert result == "answer"
    # Usage recorded (Phase 5 wiring).
    from bigbrain.llm.usage import get_tracker
    totals = get_tracker().totals()
    assert totals["calls"] == 1
    assert totals["total_tokens"] == 15


@pytest.mark.asyncio
async def test_stream_completion_yields_text():
    handler = _SSEHandler(
        content="streamed",
        usage={"prompt_tokens": 4, "completion_tokens": 4, "total_tokens": 8},
    )
    provider = _provider(handler)
    stream = await provider.chat_complete(
        [{"role": "user", "content": "hi"}], stream=True
    )
    pieces = [piece async for piece in stream]
    assert "".join(pieces) == "streamed"
    from bigbrain.llm.usage import get_tracker
    assert get_tracker().totals()["total_tokens"] == 8


@pytest.mark.asyncio
async def test_reasoning_content_deltas_are_not_surfaced():
    """Thinking streams via reasoning_content; only visible content yields."""
    def handler(request: httpx.Request) -> httpx.Response:
        chunks = [
            {"choices": [{"delta": {"reasoning_content": "thinking..."}}]},
            {"choices": [{"delta": {"content": "visible"}}]},
            {"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 2}},
        ]
        payload = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(
            200, text=payload, headers={"content-type": "text/event-stream"}
        )

    provider = _provider(handler)
    stream = await provider.chat_complete([{"role": "user", "content": "x"}], stream=True)
    pieces = [piece async for piece in stream]
    assert pieces == ["visible"]


@pytest.mark.asyncio
async def test_reasoning_model_gets_token_headroom_and_effort():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = _provider(handler, key="openrouter-kimi-k3")
    await provider.chat_complete([{"role": "user", "content": "x"}], max_tokens=100)
    assert captured["max_tokens"] > 100  # reasoning headroom
    assert captured["reasoning_effort"] == "low"


@pytest.mark.asyncio
async def test_non_reasoning_model_sends_no_effort():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = _provider(handler, key="openrouter-kimi-k2.7-code")
    await provider.chat_complete([{"role": "user", "content": "x"}], max_tokens=100)
    assert captured["max_tokens"] == 100
    assert "reasoning_effort" not in captured


@pytest.mark.asyncio
async def test_model_param_overrides_entry_default():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = _provider(handler, key="openrouter-gpt-sol")
    await provider.chat_complete(
        [{"role": "user", "content": "x"}], model="moonshotai/kimi-k3"
    )
    assert captured["model"] == "moonshotai/kimi-k3"


def test_image_content_block_encodes_a_data_url():
    from bigbrain.llm.openai_compat_provider import image_content_block

    block = image_content_block(b"photo-bytes", "image/jpeg")
    assert block == {
        "type": "image_url",
        "image_url": {"url": "data:image/jpeg;base64,cGhvdG8tYnl0ZXM="},
    }
    with pytest.raises(ValueError):
        image_content_block(b"x", "application/pdf")


@pytest.mark.asyncio
async def test_multimodal_content_blocks_are_sent_unchanged():
    handler = _SSEHandler(content="seen")
    provider = _provider(handler)
    content = [
        {"type": "text", "text": "describe"},
        {"type": "image_url", "image_url": {
            "url": "data:image/png;base64,UE5H"}},
    ]

    result = await provider.chat_complete(
        [{"role": "user", "content": content}])

    assert result == "seen"
    body = json.loads(handler.requests[0].content)
    assert body["messages"][0]["content"] == content
