"""Native decision framing, checked dispatch and conversation isolation."""
import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from bigbrain.bus.auth import BusAuth
from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.front.decision import FrontDecision, FRONT_TOOL_SCHEMA
from bigbrain.front.front_brain import FrontBrain
from bigbrain.llm.openai_compat_provider import OpenAICompatProvider


def delegation():
    objective = "Compare Path.unlink in Python 3.13 and 3.7 using official documentation."
    return {"operation":"delegate", "reply":"Je relance la recherche.", "objective":objective,
            "route":{"brain":"researcher","payload":{"type":"research"}}}


def message(session="s"):
    return BusMessage(type=MessageType.TASK, source="morphable_ui", target="front_brain",
        payload={"text":"réessaie","session_id":session,"turn_id":"turn-"+session})


@pytest.mark.asyncio
async def test_cancelled_front_turn_emits_correlated_chat_done(tmp_path):
    bus = MessageBus(tmp_path / 'logs', auth=None)
    events = []
    entered = asyncio.Event()
    async def observe(frame):
        events.append(frame.payload)
    bus.subscribe('*', observe)
    async def blocked(**kwargs):
        entered.set()
        await asyncio.Event().wait()
    provider = AsyncMock()
    provider.chat_complete.side_effect = blocked
    front = FrontBrain(bus, llm_provider=provider)
    task = asyncio.create_task(front._handle_ui_message(message()))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await bus.close()
    done = [e for e in events if e.get('event') == 'chat.done']
    assert len(done) == 1
    assert done[0]['session_id'] == 's' and done[0]['turn_id'] == 'turn-s'
    assert not any(e.get('event') == 'task.routing' for e in events)


@pytest.mark.asyncio
async def test_stalled_front_decision_settles_chat_without_dispatch(tmp_path, monkeypatch):
    from bigbrain.front import decision_runtime
    monkeypatch.setattr(decision_runtime, "FRONT_DECISION_TIMEOUT_SECONDS", .03)
    bus = MessageBus(tmp_path / "logs", auth=None)
    events, tasks = [], []
    async def observe(frame):
        events.append(frame.payload)
        if frame.type == MessageType.TASK:
            tasks.append(frame)
    bus.subscribe("*", observe)
    cancelled = asyncio.Event()
    async def never_returns(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    provider = AsyncMock()
    provider.chat_complete.side_effect = never_returns
    front = FrontBrain(bus, llm_provider=provider)
    await asyncio.wait_for(front._handle_ui_message(message()), timeout=2)
    await bus.close()
    assert cancelled.is_set()
    assert not tasks
    assert next(e for e in events if e.get("event") == "front.decision_started")["turn_id"] == "turn-s"
    failed = next(e for e in events if e.get("event") == "front.decision_failed")
    assert failed["code"] == "decision_timeout" and failed["session_id"] == "s"
    replies = [e for e in events if e.get("event") == "chat.message"]
    assert len(replies) == 1
    assert "tentative est arrêtée" in replies[0]["text"]
    assert replies[0]["session_id"] == "s" and replies[0]["turn_id"] == "turn-s"


@pytest.mark.asyncio
async def test_late_provider_decision_cannot_dispatch_after_deadline(tmp_path, monkeypatch):
    from bigbrain.front import decision_runtime
    monkeypatch.setattr(decision_runtime, "FRONT_DECISION_TIMEOUT_SECONDS", .01)
    bus = MessageBus(tmp_path / "logs", auth=None)
    events = []
    async def observe(frame):
        events.append(frame.payload)
    bus.subscribe("*", observe)
    async def late(**kwargs):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            return json.dumps({"decision": delegation()})
    provider = AsyncMock()
    provider.chat_complete.side_effect = late
    front = FrontBrain(bus, llm_provider=provider)
    front.register_brain("researcher", "Research")
    await front._handle_ui_message(message())
    await bus.close()
    assert not any(e.get("event") == "task.routing" for e in events)
    assert any(e.get("event") == "front.decision_failed" and e.get("code") == "decision_timeout" for e in events)
    assert len([e for e in events if e.get("event") == "chat.message"]) == 1


@pytest.mark.parametrize("decision", [
    {"operation":"respond","reply":"Bonjour"},
    {"operation":"clarify","reply":"Quelle recherche souhaites-tu relancer ?"},
    {"operation":"consult_memory","tool":"projects.list","arguments":{}},
    delegation(),
    {"operation":"delegate","reply":"Je prépare le projet.","objective":"Create a calculator",
     "project_target":{"mode":"new"}},
])
def test_decision_schema_supports_codex_closed_objects(decision):
    from bigbrain.llm.codex_provider import _strict_schema
    assert FrontDecision.model_validate({"decision":decision})
    assert _strict_schema(FRONT_TOOL_SCHEMA["parameters"])["additionalProperties"] is False


@pytest.mark.parametrize("decision", [
    {"operation":"respond","reply":"Bonjour","route":delegation()["route"]},
    {"operation":"delegate","reply":"Je relance"},
    {**delegation(),"route":{"brain":"researcher","payload":{"type":"research","query":"Duplicate objective"}}},
    {"operation":"consult_memory","tool":"shell","arguments":{}},
    {"operation":"delegate","reply":"Go","objective":"Repair project","project_target":{"mode":"existing"}},
])
def test_decision_contract_rejects_contradictory_or_incomplete_actions(decision):
    with pytest.raises(ValidationError):
        FrontDecision.model_validate({"decision":decision})


@pytest.mark.asyncio
async def test_native_provider_retries_history_and_drives_real_bus_events(tmp_path):
    calls, delivered, events = [], [], []
    def respond(request):
        body=json.loads(request.content)
        calls.append(body)
        assert body["stream"] is False
        assert body["tool_choice"]["function"]["name"] == "bigbrain_front_decision"
        assert "An old failed attempt" in json.dumps(body["messages"])
        return httpx.Response(200,json={"choices":[{"finish_reason":"tool_calls","message":{
            "tool_calls":[{"id":"front","type":"function","function":{
            "name":"bigbrain_front_decision","arguments":json.dumps({"decision":delegation()})}}]}}]})
    provider=OpenAICompatProvider("openrouter-gpt-6.1-sol",api_key="fixture")
    provider._client=httpx.AsyncClient(base_url=provider.entry.base_url,transport=httpx.MockTransport(respond))
    auth=BusAuth()
    auth.generate_token("front_brain")
    auth.generate_token("orchestrator_default")
    bus=MessageBus(tmp_path/"logs",auth=auth)
    async def observe(frame):
        events.append(frame.payload)
    async def accept(frame):
        if frame.type != MessageType.TASK or frame.target != "orchestrator_default":
            return
        delivered.append(frame)
        await bus.broadcast_event(source="orchestrator_default",event_type="task.received",
            payload={"session_id":frame.payload["session_id"],"task_id":frame.payload["_ui_run_id"]})
    bus.subscribe("*",observe)
    bus.subscribe("orchestrator_default",accept)
    front=FrontBrain(bus,llm_provider=provider)
    front.register_brain("researcher","Documentation research")
    front._history_for("s").append({"role":"assistant","content":"An old failed attempt"})
    try:
        await front._handle_ui_message(message())
    finally:
        await provider._client.aclose()
        await bus.close()
    assert len(calls)==len(delivered)==1
    payload=delivered[0].payload
    assert payload["query"]==payload["user_request"]==delegation()["objective"]
    assert payload["user_message"]=="réessaie" and payload["session_id"]=="s"
    kinds=[e.get("event") for e in events]
    assert kinds.index("task.routing") < kinds.index("chat.message") < kinds.index("task.received")
    assert not {"chat.delta","task.failed","task.complete"}.intersection(kinds)
    assert len([e for e in events if e.get("event")=="chat.message"])==1


@pytest.mark.asyncio
async def test_unavailable_target_settles_attempt_without_success_acknowledgement(tmp_path):
    bus=MessageBus(tmp_path/"logs",auth=None)
    events=[]
    async def observe(frame):
        events.append(frame.payload)
    bus.subscribe("*",observe)
    provider=AsyncMock()
    provider.chat_complete.return_value=json.dumps({"decision":delegation()})
    front=FrontBrain(bus,llm_provider=provider)
    front.register_brain("researcher","Documentation research")
    await front._handle_ui_message(message())
    await bus.close()
    routed=next(e for e in events if e.get("event")=="task.routing")
    failed=next(e for e in events if e.get("event")=="task.failed")
    assert failed["task_id"]==routed["task_id"] and failed["session_id"]=="s"
    assert not any(e.get("text")==delegation()["reply"] for e in events)


@pytest.mark.asyncio
async def test_checked_bus_rejects_unsigned_task_before_acceptance(tmp_path):
    bus=MessageBus(tmp_path/"logs",auth=BusAuth())
    target,ack=AsyncMock(),AsyncMock()
    bus.subscribe("orchestrator_default",target)
    with pytest.raises(PermissionError):
        await bus.send_task("unregistered","orchestrator_default",{},require_target=True,on_accepted=ack)
    ack.assert_not_awaited()
    target.assert_not_awaited()
    await bus.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["Je relance.\n❌ Task failed: An old failure", "{}", "```json\n{}\n```"])
async def test_plain_or_invalid_decision_never_replays_historical_failure(tmp_path,raw):
    provider=AsyncMock()
    provider.chat_complete.return_value=raw
    bus=MessageBus(tmp_path/"logs",auth=None)
    front=FrontBrain(bus,llm_provider=provider)
    front._emit_chat_message=AsyncMock()
    bus.send_task=AsyncMock()
    await front._handle_ui_message(message())
    bus.send_task.assert_not_awaited()
    assert "Aucune nouvelle tâche" in front._emit_chat_message.call_args.args[1]
    assert "An old failure" not in front._emit_chat_message.call_args.args[1]
    await bus.close()


@pytest.mark.asyncio
async def test_literal_routing_json_in_a_response_is_never_executed(tmp_path):
    text=json.dumps({"reply":"Example","route":delegation()["route"]})
    provider=AsyncMock()
    provider.chat_complete.return_value=json.dumps({"decision":{"operation":"respond","reply":text}})
    bus=MessageBus(tmp_path/"logs",auth=None)
    front=FrontBrain(bus,llm_provider=provider)
    front._emit_chat_message=AsyncMock()
    bus.send_task=AsyncMock()
    await front._handle_ui_message(message())
    bus.send_task.assert_not_awaited()
    assert front._emit_chat_message.call_args.args[1]==text
    await bus.close()


@pytest.mark.asyncio
async def test_stop_during_native_decision_prevents_a_valid_delegation(tmp_path):
    bus=MessageBus(tmp_path/"logs",auth=None)
    class Provider:
        async def chat_complete(self,**kwargs):
            front.request_stop("s")
            return json.dumps({"decision":delegation()})
    front=FrontBrain(bus,llm_provider=Provider())
    bus.send_task=AsyncMock()
    await front._handle_ui_message(message())
    bus.send_task.assert_not_awaited()
    await bus.close()


@pytest.mark.asyncio
async def test_concurrent_delegation_does_not_leak_into_another_conversation(tmp_path):
    waiting,release=asyncio.Event(),asyncio.Event()
    class Provider:
        async def chat_complete(self,messages,**kwargs):
            if messages[-1]["content"]=="A":
                waiting.set()
                await release.wait()
                return json.dumps({"decision":delegation()})
            return json.dumps({"decision":{"operation":"clarify","reply":"Quelle tâche ?"}})
    bus=MessageBus(tmp_path/"logs",auth=None)
    received=[]
    async def accept(frame):
        if frame.type==MessageType.TASK:
            received.append(frame.payload)
    bus.subscribe("orchestrator_default",accept)
    front=FrontBrain(bus,llm_provider=Provider())
    front.register_brain("researcher","Research")
    def request(name):
        return BusMessage(type=MessageType.TASK,source="morphable_ui",target="front_brain",
            payload={"text":name,"session_id":name})
    task=asyncio.create_task(front._handle_ui_message(request("A")))
    try:
        await asyncio.wait_for(waiting.wait(),2)
        await front._handle_ui_message(request("B"))
        release.set()
        await asyncio.wait_for(task,2)
        assert len(received)==1 and received[0]["session_id"]=="A"
    finally:
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        await bus.close()
