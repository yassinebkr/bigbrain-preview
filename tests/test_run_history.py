"""Durable activity restoration and memory retrieval regressions."""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.front.front_brain import FrontBrain
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, TaskPlan, TaskStatus, SubTask
from bigbrain.web.run_history import conversation_activity
from bigbrain.web.server import WebServer


async def emit(bus, event, task_id, session_id="sess-demo", **data):
    await bus.broadcast_event(source="test", event_type=event,
        payload={"task_id": task_id, "session_id": session_id, **data})


@pytest.mark.asyncio
async def test_restore_interleaved_web_and_taskboard_after_buffer_expiry(tmp_path):
    bus = MessageBus(tmp_path / "logs", auth=None)
    server = WebServer(bus)
    server._sessions.append_message("sess-demo", "user", "Build a running tracker")
    try:
        await emit(bus, "task.routing", "web", description="Running tracker")
        await emit(bus, "task.received", "web")
        await emit(bus, "subtask.started", "web", subtask_id="web-file", brain="web_app_brain_0", description="Write App")
        await emit(bus, "task.routing", "board", description="Add laundry")
        await emit(bus, "task.received", "board")
        await emit(bus, "subtask.started", "board", subtask_id="board-task", brain="taskboard")
        await emit(bus, "subtask.complete", "board", subtask_id="board-task")
        await emit(bus, "task.complete", "board", result_kind="taskboard")
        await emit(bus, "workspace.file_written", "web", path="sandbox/running/src/App.tsx")
        await emit(bus, "subtask.complete", "web", subtask_id="web-file")
        await emit(bus, "task.complete", "web", project_path="sandbox/running", entry_point="index.html", runnable=True)
        await emit(bus, "task.received", "foreign", session_id="sess-other")
        server._replay_buffer.clear()  # Empty/expired transient buffer must not matter.
        ws = AsyncMock()
        await server._handle_request(ws, {"id": "history", "method": "chat.history", "params": {"sessionId": "sess-demo"}})
        result = ws.send_json.call_args.args[0]["payload"]
        assert result["messages"][0]["text"] == "Build a running tracker"
        frames = result["activities"]
        assert {f["payload"]["task_id"] for f in frames} == {"web", "board"}
        assert len([f for f in frames if f["payload"]["event"] == "task.complete"]) == 2
        board_step = next(f for f in frames if f["payload"].get("subtask_id") == "board-task")
        assert board_step["payload"]["brain"] == "taskboard"
        assert not result["activity_error"]
        assert server._sessions.get("sess-demo")["title"] == "Build a running tracker"
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_restart_restores_pending_plan_as_interrupted_not_working(tmp_path):
    bus = MessageBus(tmp_path / "logs", auth=None)
    await emit(bus, "task.received", "pending")
    await emit(bus, "contracts.proposal", "pending", plan_id="pending", design_id="design", contracts=["real criterion"])
    server_after_restart = WebServer(bus)
    try:
        frames = conversation_activity(bus.logger.log_dir, "sess-demo", server_after_restart._started_at)
        final = frames[-1]["payload"]
        assert final["event"] == "task.failed"
        assert final["task_id"] == "pending"
        assert "redémarrage" in final["error"]
        assert final["runnable"] is False
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_legacy_routing_gets_correlated_and_invalid_log_line_is_ignored(tmp_path):
    bus = MessageBus(tmp_path / "logs", auth=None)
    await bus.broadcast_event(source="front", event_type="task.routing", payload={"session_id": "sess-demo"})
    await emit(bus, "task.received", "legacy")
    await emit(bus, "task.complete", "legacy")
    await bus.close()
    with next((tmp_path / "logs").glob("*.jsonl")).open("a") as handle:
        handle.write('{"incomplete":')
    frames = conversation_activity(bus.logger.log_dir, "sess-demo", 0)
    assert {f["payload"]["task_id"] for f in frames} == {"legacy"}


def test_taskboard_never_inherits_selected_project_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path))
    selected = tmp_path / "sandbox" / "blender"
    selected.mkdir(parents=True)
    (selected / ".project.json").write_text(json.dumps({"name": "blender", "entry_point": "main.py", "run": "python main.py"}))
    message = BusMessage(type=MessageType.TASK, source="front", target="orchestrator", payload={"project_path": "sandbox/blender"})
    plan = TaskPlan(id="board", original_task=message, status=TaskStatus.COMPLETE,
        subtasks=[SubTask(id="s", description="Create task", brain_target="taskboard", payload={"type": "board_task"})])
    assert WorkspaceOrchestrator._project_result_metadata(plan) == {"result_kind": "taskboard", "runnable": False}


def test_side_task_terminal_does_not_remove_other_routing_in_same_conversation(tmp_path):
    server = WebServer(MessageBus(tmp_path / "logs", auth=None))
    for task_id in ["web", "board"]:
        server._maybe_buffer("event", "task.routing", {"type": "event", "payload": {
            "event": "task.routing", "task_id": task_id, "session_id": "sess-demo"}})
    server._maybe_buffer("event", "task.complete", {"type": "event", "payload": {
        "event": "task.complete", "task_id": "board", "session_id": "sess-demo"}})
    assert any(frame["payload"].get("task_id") == "web" for _, frame in server._replay_buffer)


def test_recall_dedupes_before_budget_and_keeps_original_user_evidence(tmp_path):
    front = FrontBrain(MessageBus(tmp_path / "logs", auth=None))
    question = "te rappelles-tu de mon animal ?"
    front.memory.persistent.query = Mock(return_value=[
        {"content": f"user: {question}", "metadata": {"role": "user"}},
        {"content": f"user: {question}", "metadata": {"role": "user"}},
        {"content": "user: quel est le nom déjà ?", "metadata": {"role": "user"}},
        {"content": "assistant: Je ne sais plus", "metadata": {"role": "assistant"}},
        {"content": "assistant: Il est blanc", "metadata": {"role": "assistant"}},
        {"content": "assistant: Il aime jouer", "metadata": {"role": "assistant"}},
        {"content": "user: Mon chat s’appelle Moka", "metadata": {"role": "user"}},
    ])
    recalled = front._recall_relevant(question, [{"role": "user", "content": question}])
    assert len(recalled) == 4
    assert any("user: Mon chat s’appelle Moka" in fact for fact in recalled)
    assert not any(question in fact for fact in recalled)
    assert front.memory.persistent.query.call_args.kwargs["limit"] == 24
