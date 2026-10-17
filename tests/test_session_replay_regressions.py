

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
