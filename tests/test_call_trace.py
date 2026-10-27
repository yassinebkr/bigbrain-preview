"""Offline inference lifecycle fault injection and privacy checks."""
import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from bigbrain.llm.call_trace import trace_call
from bigbrain.llm.conversation import conversation_scope
from bigbrain.llm.openai_compat_provider import OpenAICompatProvider
from bigbrain.llm.usage import capture_usage


def traces(tmp_path):
    return [[json.loads(line) for line in file.read_text().splitlines()]
            for file in (tmp_path / "evidence" / "inference").glob("*.jsonl")]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["success", "error", "timeout", "cancel"])
async def test_one_terminal_trace_for_each_provider_outcome(tmp_path, mode):
    provider = SimpleNamespace(registry_key="fixture", default_model="test-model", reasoning_effort="low")
    async def invoke():
        with conversation_scope("session", "research"), trace_call(provider, "choose",
                correlation={"research_id": "run"}, deadline_seconds=.01 if mode == "timeout" else None):
            if mode == "error":
                try:
                    raise OSError("secret-provider-body")
                except OSError as cause:
                    raise ValueError("secret-prompt") from cause
            if mode != "success":
                await asyncio.Event().wait()
    if mode == "timeout":
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(.01):
                await invoke()
    elif mode == "cancel":
        task = asyncio.create_task(invoke())
        await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    elif mode == "error":
        with pytest.raises(ValueError):
            await invoke()
    else:
        await invoke()
    rows = traces(tmp_path)[0]
    assert [r["event"] for r in rows] == ["call.started", "call.finished"]
    assert rows[-1]["outcome"] == {"success": "completed", "error": "failed", "timeout": "deadline", "cancel": "cancelled"}[mode]
    assert rows[-1]["session_id"] == "session" and rows[-1]["research_id"] == "run"
    assert rows[-1]["usage_known"] is False
    assert "secret" not in json.dumps(rows)
    if mode == "error":
        assert rows[-1]["exception_types"] == ["ValueError", "OSError"]


@pytest.mark.asyncio
async def test_http_trace_has_one_transport_attempt_and_captured_usage(tmp_path):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, headers={"x-request-id": "request-1"}, json={
            "choices": [{"message": {"content": "private answer"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}})
    provider = OpenAICompatProvider("openrouter-gpt-6.1-sol", api_key="private-key")
    provider._client = httpx.AsyncClient(base_url="https://api.test", transport=httpx.MockTransport(respond))
    try:
        with capture_usage() as usage, trace_call(provider, "choose", records=usage):
            await provider.chat_complete([{"role": "user", "content": "private prompt"}])
    finally:
        await provider._client.aclose()
    rows = traces(tmp_path)[0]
    assert len(calls) == 1
    assert [r["event"] for r in rows] == ["call.started", "http.started", "http.response", "call.finished"]
    assert rows[1]["automatic_retries"] == 0
    assert rows[2]["request_id"] == "request-1"
    assert rows[-1]["usage"][0]["total_tokens"] == 10
    assert "private" not in json.dumps(rows)


@pytest.mark.asyncio
async def test_http_failure_does_not_retry_or_log_response_body(tmp_path):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(503, text="private-provider-error")
    provider = OpenAICompatProvider("openrouter-gpt-6.1-sol", api_key="private-key")
    provider._client = httpx.AsyncClient(base_url="https://api.test", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(httpx.HTTPStatusError), trace_call(provider, "choose"):
            await provider.chat_complete([{"role": "user", "content": "private prompt"}])
    finally:
        await provider._client.aclose()
    rows = traces(tmp_path)[0]
    assert len(calls) == 1
    assert rows[-1]["outcome"] == "failed"
    assert rows[-2]["status_code"] == 503
    assert "private" not in json.dumps(rows)
