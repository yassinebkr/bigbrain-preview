

def test_terminal_task_removes_routing_marker_from_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGBRAIN_SESSIONS_DIR", str(tmp_path / "sessions"))
    server = WebServer(bus=MessageBus(auth=None))
    routing = {
        "type": "event",
        "source": "front_brain",
        "payload": {
            "event": "task.routing",
            "session_id": "sess-1",
            "description": "build fitness app",
        },
    }
    server._maybe_buffer("event", "task.routing", routing)
    assert len(server._replay_buffer) == 1

    completed = {
        "type": "event",
        "source": "orchestrator_default",
        "payload": {
            "event": "task.complete",
            "task_id": "plan-1",
            "session_id": "sess-1",
        },
    }
    server._maybe_buffer("event", "task.complete", completed)

    events = [
        item["payload"]["event"] for _, item in server._replay_buffer
    ]
    assert "task.routing" not in events
    assert "task.complete" in events
"""Regression tests for persisted chat context and contract replay state."""

from unittest.mock import AsyncMock

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.front.front_brain import FrontBrain
from bigbrain.web.server import WebServer


def test_front_brain_rehydrates_exact_persisted_session_window():
    brain = FrontBrain(MessageBus(auth=None))
    brain._history_for("sess-cat").append({
        "role": "assistant", "content": "stale in-memory answer"
    })
    brain._hydrate_session_history("sess-cat", [
        {"role": "user", "content": "Mon chat s appelle Chichi"},
        {"role": "assistant", "content": "Je retiens Chichi."},
        {"role": "system", "content": "ignored"},
    ])
    assert brain._history_for("sess-cat") == [
        {"role": "user", "content": "Mon chat s appelle Chichi"},
        {"role": "assistant", "content": "Je retiens Chichi."},
    ]


@pytest.mark.asyncio
async def test_chat_send_carries_persisted_history_before_current_turn(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGBRAIN_SESSIONS_DIR", str(tmp_path / "sessions"))
    bus = MessageBus(auth=None)
    sent = []
    bus.subscribe("front_brain", lambda message: sent.append(message))
    server = WebServer(bus=bus)
    server._sessions.append_message("sess-cat", "user", "Mon chat s appelle Chichi")
    server._sessions.append_message("sess-cat", "assistant", "Je retiens Chichi.")

    await server._handle_chat_send(AsyncMock(), {
        "payload": {
            "text": "Quel est son nom ?",
            "messageId": "m2",
            "sessionId": "sess-cat",
        }
    })

    task = sent[-1]
    assert task.payload["conversation_history"] == [
        {"role": "user", "content": "Mon chat s appelle Chichi"},
        {"role": "assistant", "content": "Je retiens Chichi."},
    ]
    assert task.payload["text"] == "Quel est son nom ?"


def test_contract_verdict_removes_pending_proposal_from_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGBRAIN_SESSIONS_DIR", str(tmp_path / "sessions"))
    server = WebServer(bus=MessageBus(auth=None))
    proposal = {
        "type": "event",
        "source": "orchestrator_default",
        "payload": {
            "event": "contracts.proposal",
            "design_id": "task-abc",
            "plan_id": "plan-1",
        },
    }
    server._maybe_buffer("event", "contracts.proposal", proposal)
    assert len(server._replay_buffer) == 1

    approved = {
        "type": "event",
        "source": "orchestrator_default",
        "payload": {
            "event": "contracts.approved",
            "design_id": "task-abc",
            "plan_id": "plan-1",
        },
    }
    server._maybe_buffer("event", "contracts.approved", approved)
    assert server._replay_buffer == []


def test_cancelled_task_does_not_replay_as_running():
    server = WebServer(bus=MessageBus(auth=None))
    for event in ("task.received", "task.cancelled"):
        server._maybe_buffer("event", event, {
            "source": "orchestrator_default",
            "payload": {"event": event, "task_id": "plan-1"},
        })
    assert [data["payload"]["event"] for _, data in server._replay_buffer] == ["task.cancelled"]


@pytest.mark.asyncio
async def test_selected_project_is_not_a_mandatory_destination_for_new_requests():
    provider = AsyncMock()
    provider.chat_complete.return_value = "D'accord"
    front = FrontBrain(MessageBus(auth=None), llm_provider=provider)
    front._current_project = lambda: "sandbox/blender"
    front._history_for("sess-new").append({
        "role": "user", "content": "Crée un programme React sur quatre semaines",
    })
    await front._handle_ui_message(BusMessage(
        type=MessageType.TASK, source="morphable_ui", target="front_brain",
        payload={"text": "Crée un programme React sur quatre semaines", "session_id": "sess-new",
                 "navigation_project": "sandbox/blender"}))
    messages = provider.chat_complete.call_args.kwargs["messages"]
    context = next(m["content"] for m in messages if "Workspace selection:" in m["content"])
    assert "sandbox/blender" in context
    assert "NOT an instruction to reuse" in context
    assert "own sibling directory" in context
    assert "File operations and generated code belong in this project" not in context


@pytest.mark.asyncio
async def test_failed_plan_emits_one_terminal_result_despite_late_worker_completions(monkeypatch):
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, TaskPlan, SubTask, TaskStatus

    bus = MessageBus(auth=None)
    bus.send_result = AsyncMock()
    bus.broadcast_event = AsyncMock()
    orch = WorkspaceOrchestrator("default", bus)
    monkeypatch.setattr(orch, "_extract_learnings", AsyncMock())
    plan = TaskPlan(
        id="plan-once", status=TaskStatus.RUNNING,
        original_task=BusMessage(type=MessageType.TASK, source="front_brain", target=orch.name),
        subtasks=[SubTask(id="s1", description="file one", brain_target="python_brain", payload={},
                          status=TaskStatus.FAILED, error="same failure"),
                  SubTask(id="s2", description="file two", brain_target="python_brain", payload={},
                          status=TaskStatus.RUNNING)],
    )
    await orch._check_plan_completion(plan)
    plan.subtasks[1].status = TaskStatus.FAILED
    plan.subtasks[1].error = "same failure"
    await orch._check_plan_completion(plan)
    await orch._check_plan_completion(plan)
    assert bus.send_result.await_count == 1
    assert bus.broadcast_event.await_count == 1
    assert plan.error == "same failure"


@pytest.mark.asyncio
async def test_late_result_and_stream_keep_their_originating_session():
    bus = MessageBus(auth=None)
    bus.broadcast_event = AsyncMock()
    front = FrontBrain(bus)
    front._last_session_id = "sess-new"
    await front._handle_task_result(BusMessage(
        type=MessageType.RESULT, source="orchestrator_default", target="front_brain",
        payload={"success": False, "error": "old failure", "session_id": "sess-old"},
    ))
    reply = next(call.kwargs for call in bus.broadcast_event.await_args_list
                 if call.kwargs.get("event_type") == "chat.message")
    assert reply["payload"]["session_id"] == "sess-old"
    await front._emit_chat_delta("old text", session_id="sess-old")
    assert bus.broadcast_event.await_args.kwargs["payload"]["session_id"] == "sess-old"
    assert front._last_session_id == "sess-new"
