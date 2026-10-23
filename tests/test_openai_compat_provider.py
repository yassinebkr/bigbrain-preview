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
async def test_mistral_high_is_default_without_local_token_or_read_timeout(monkeypatch):
    monkeypatch.delenv('MISTRAL_STUDIO_LARGE_4_REASONING_EFFORT', raising=False)
    provider = OpenAICompatProvider('mistral-studio-large-4', api_key='test-key')
    try:
        body = provider._request_params([{'role': 'user', 'content': 'Test'}], None, 768, 0)
        assert body['reasoning_effort'] == 'high'
        assert 'max_tokens' not in body
        assert body['top_p'] == 1
        assert provider.client.timeout.read is None
        assert provider.client.timeout.connect == 10
    finally:
        await provider.client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
async def test_provider_length_finish_never_becomes_partial_tool_result(stream):
    def respond(request):
        if json.loads(request.content).get('stream'):
            return httpx.Response(200, text='data: ' + json.dumps({'choices': [
                {'finish_reason': 'length', 'delta': {}}]}) + '\n\n',
                headers={'content-type': 'text/event-stream'})
        return httpx.Response(200, json={'choices': [{'finish_reason': 'length',
            'message': {'content': 'partial answer'}}]})
    provider = _provider(respond, key='mistral-studio-large-4')
    try:
        with pytest.raises(ValueError, match='truncated'):
            result = await provider.chat_complete([{'role': 'user', 'content': 'Test'}], stream=stream)
            if stream:
                _ = [chunk async for chunk in result]
    finally:
        await provider.client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
async def test_mistral_reasoning_chunks_expose_only_visible_text(monkeypatch, stream):
    monkeypatch.setenv('MISTRAL_STUDIO_LARGE_4_REASONING_EFFORT', 'high')
    handler = _SSEHandler(content=[
        {'type': 'thinking', 'thinking': [{'type': 'text', 'text': 'private reasoning'}]},
        {'type': 'text', 'text': 'final answer'}])
    provider = _provider(handler, key='mistral-studio-large-4')
    try:
        result = await provider.chat_complete([{'role': 'user', 'content': 'Answer'}], stream=stream)
        if stream:
            result = ''.join([text async for text in result])
        assert result == 'final answer'
        body = json.loads(handler.requests[0].content)
        assert body['reasoning_effort'] == 'high'
        assert 'max_tokens' not in body
        assert provider.reasoning_timeout_seconds is None
    finally:
        await provider._client.aclose()


@pytest.mark.asyncio
async def test_structured_review_schema_is_forwarded_and_not_silently_dropped():
    from bigbrain.verification.semantics import _review_format
    handler = _SSEHandler(content='{"decision":"needs_arbitration"}')
    provider = _provider(handler, key='openrouter-gpt-6.1-sol')
    try:
        await provider.chat_complete([{'role': 'user', 'content': 'Review the evidence as JSON'}],
                                     response_format=_review_format())
        body = json.loads(handler.requests[0].content)
        assert body['response_format'] == _review_format()
        assert body['response_format']['json_schema']['strict'] is True
        assert body['provider'] == {'require_parameters': True}
        assert 'temperature' not in body
        assert 'stream_options' not in body
    finally:
        await provider._client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('count', [0, 1, 2])
async def test_native_single_action_requires_exactly_one_named_call(count):
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': 'must not become a text fallback',
            'tool_calls': [{'type': 'function', 'function': {'name': 'step', 'arguments': '{"action":{"type":"read"}}'}}] * count}}]})
    provider = OpenAICompatProvider('openrouter-gpt-6.1-sol', api_key='test-key')
    provider._client = httpx.AsyncClient(base_url=provider.entry.base_url, transport=httpx.MockTransport(respond))
    schema = {'name': 'step', 'description': 'One action', 'parameters': {'type': 'object'}}
    try:
        if count == 1:
            assert await provider.chat_complete([{'role': 'user', 'content': 'One read action'}], tool_schema=schema) == '{"action":{"type":"read"}}'
        else:
            with pytest.raises(ValueError, match='exactly'):
                await provider.chat_complete([{'role': 'user', 'content': 'One read action'}], tool_schema=schema)
        assert requests[0]['tools'][0]['function'] == schema
        assert requests[0]['tool_choice']['function']['name'] == 'step'
        assert requests[0]['parallel_tool_calls'] is False
        assert requests[0]['provider']['require_parameters'] is True
    finally:
        await provider._client.aclose()


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

    provider = _provider(handler, key="openrouter-mistral-large-4")
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
