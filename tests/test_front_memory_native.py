"""Actual SSE tool framing → front brain → sourced memory → final reply.

All model responses are frozen HTTP fixtures; no network, paid calls or real
user memories are used. The lookup itself runs the real shared-memory code.
"""
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.front.front_brain import FrontBrain
from bigbrain.llm.openai_compat_provider import OpenAICompatProvider
from bigbrain.llm.provider import MemoryToolCall
from bigbrain.memory.shared import SharedMemory
from bigbrain.web.sessions import SessionStore


def sse(chunks):
    frames = ["data: " + json.dumps({"choices": [{"delta": chunk}]}) for chunk in chunks]
    return httpx.Response(200, text="\n\n".join(frames) + "\n\ndata: [DONE]\n\n",
                          headers={"content-type": "text/event-stream"})


@pytest.mark.asyncio
async def test_native_memory_preamble_does_not_end_turn_before_actual_lookup(tmp_path):
    calls = []
    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["tool_choice"] == "auto"
        if len(calls) == 1:
            return sse([{"reasoning_content": "PRIVATE CONTINUATION", "reasoning_details": [{"index": 0, "type": "reasoning.text", "text": "private"}]},
                {"content": "Je consulte la mémoire. "},
                {"tool_calls": [{"index": 0, "id": "call-memory", "type": "function", "function": {
                    "name": "bigbrain_memory", "arguments": '{"tool":"facts.read","arguments":'}}]},
                {"tool_calls": [{"index": 0, "function": {"arguments": '{"key":"user.cat.name"}}'}}]}])
        result = body["messages"][-1]
        assistant = body["messages"][-2]
        assert assistant["tool_calls"][0]["type"] == "function"
        assert assistant["reasoning_content"] == "PRIVATE CONTINUATION"
        assert assistant["reasoning_details"][0]["text"] == "private"
        assert result["role"] == "tool" and result["tool_call_id"] == "call-memory"
        fact = json.loads(result["content"])
        assert fact["status"] == "ok"
        assert fact["fact"]["source_session"] == "past"
        return sse([{"content": f"Ton chat s’appelle {fact['fact']['value']}."}])
    provider = OpenAICompatProvider("openrouter-gpt-6.1-sol", api_key="fixture")
    provider._client = httpx.AsyncClient(base_url=provider.entry.base_url, transport=httpx.MockTransport(respond))
    bus = MessageBus(tmp_path / "logs", auth=None)
    front = FrontBrain(bus, llm_provider=provider)
    source = SessionStore().append_message("past", "user", "Mon chat se nomme Moka.")["messages"][-1]
    memory = SharedMemory(bus.logger.log_dir, front.memory.persistent.storage_dir)
    memory.facts_write({"key": "user.cat.name", "value": "Moka", "quote": source["text"],
        "source_message_id": source["id"], "expected_revision": 0}, "past")
    try:
        await front._handle_ui_message(BusMessage(type=MessageType.TASK, source="morphable_ui", target="front_brain",
            payload={"text": "Te rappelles-tu de mon animal ?", "session_id": "now", "turn_id": "turn"}))
    finally:
        await bus.close()
        await provider._client.aclose()
    frames = [json.loads(line) for p in (tmp_path / "logs").glob("*.jsonl") for line in p.read_text().splitlines()]
    events = [frame["payload"] for frame in frames]
    consulted = next(i for i, e in enumerate(events) if e.get("event") == "memory.consulted")
    done = [i for i, e in enumerate(events) if e.get("event") == "chat.done"]
    assert len(done) == 1 and done[0] > consulted
    assert events[done[0]]["text"] == "Ton chat s’appelle Moka."
    assert len(calls) == 2
    assert all("bigbrain_memory" not in e.get("delta", "") for e in events)
    assert "PRIVATE CONTINUATION" not in json.dumps(frames)


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_empty_model_reply_produces_explicit_terminal_message(tmp_path, streaming):
    class Provider:
        async def chat_complete(self, **kwargs):
            async def stream():
                if False:
                    yield ""
            return stream() if streaming else ""
    bus = MessageBus(tmp_path / "logs", auth=None)
    front = FrontBrain(bus, llm_provider=Provider())
    front._emit_chat_message = AsyncMock()
    await front._handle_ui_message(BusMessage(type=MessageType.TASK, source="morphable_ui", target="front_brain",
        payload={"text": "Alors ?", "session_id": "s"}))
    assert "sans fournir de réponse" in front._emit_chat_message.await_args.args[1]
    await bus.close()


@pytest.mark.parametrize("calls", [[], [{"id": "x", "function": {"name": "shell", "arguments": "{}"}}]])
def test_native_memory_cannot_execute_an_unknown_tool(calls):
    with pytest.raises(ValueError):
        OpenAICompatProvider._memory_call(calls)


def test_native_memory_envelope_is_not_plain_chat_text():
    call = OpenAICompatProvider._memory_call([{"id": "x", "function": {"name": "bigbrain_memory",
        "arguments": '{"tool":"facts.search","arguments":{"query":"animal"}}'}}])
    assert isinstance(call, MemoryToolCall)
    assert call.arguments["tool"] == "facts.search"
