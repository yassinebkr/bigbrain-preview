"""Persistent TaskBoard — store, brain capability, and agent-created tasks."""

import pytest


@pytest.fixture
def store_path(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    monkeypatch.setenv("BIGBRAIN_TASKS_FILE", str(path))
    return path


class TestTaskBoardStore:
    def test_create_list_update_delete(self, store_path):
        from bigbrain.web.taskboard import TaskBoardStore

        store = TaskBoardStore()
        task = store.create(title="Mettre à jour le README",
                            description="du projet near_agi", status="todo")
        assert task["status"] == "todo"
        assert store.list()[0]["title"] == "Mettre à jour le README"

        updated = store.update(task["id"], {"status": "in-progress"})
        assert updated["status"] == "in-progress"

        assert store.delete(task["id"]) is True
        assert store.list() == []

    def test_invalid_inputs(self, store_path):
        from bigbrain.web.taskboard import TaskBoardError, TaskBoardStore

        store = TaskBoardStore()
        with pytest.raises(TaskBoardError):
            store.create(title="   ")
        with pytest.raises(TaskBoardError):
            store.create(title="ok", status="finished")

    def test_survives_restart(self, store_path):
        from bigbrain.web.taskboard import TaskBoardStore

        TaskBoardStore().create(title="persisted task")
        # A NEW store instance reads the same file.
        assert TaskBoardStore().list()[0]["title"] == "persisted task"


class TestTaskBoardBrain:
    @pytest.fixture
    def brain(self):
        from unittest.mock import AsyncMock, Mock

        from bigbrain.brains.taskboard_brain import TaskBoardBrain

        bus = Mock()
        bus.send = AsyncMock()
        bus.send_result = AsyncMock()
        bus.broadcast_event = AsyncMock()
        bus.subscribe = Mock()
        bus.unsubscribe = Mock()
        return TaskBoardBrain(name="taskboard", bus=bus, workspace="default"), bus

    async def test_board_task_creates_todo_and_broadcasts(self, brain, store_path):
        from bigbrain.bus.message import BusMessage, MessageType

        taskboard, bus = brain
        message = BusMessage(
            type=MessageType.TASK,
            source="orchestrator",
            target="taskboard",
            payload={
                "type": "board_task",
                "title": "Mettre à jour le README du projet near_agi",
                "description": "expliquer l'état actuel",
            },
        )
        result = await taskboard.handle_task(message)

        assert result["success"] is True
        # A requested task is a TO-DO by default — not 'done'.
        assert result["task"]["status"] == "todo"

        # The creation is persisted...
        from bigbrain.web.taskboard import TaskBoardStore

        assert TaskBoardStore().list()[0]["title"].startswith("Mettre à jour")

        # ...and broadcast so open UIs refresh.
        events = [c.args[0].payload for c in bus.send.call_args_list
                  if getattr(c.args[0], "payload", None)]
        assert any(p.get("event") == "taskboard.task_created"
                   for p in events)

    async def test_explicit_status_is_respected(self, brain, store_path):
        from bigbrain.bus.message import BusMessage, MessageType

        taskboard, _ = brain
        result = await taskboard.handle_task(BusMessage(
            type=MessageType.TASK, source="orchestrator", target="taskboard",
            payload={"type": "board_task", "title": "déjà fait",
                      "status": "done"},
        ))
        assert result["task"]["status"] == "done"

    async def test_unknown_task_type_rejected(self, brain):
        from bigbrain.bus.message import BusMessage, MessageType

        taskboard, _ = brain
        with pytest.raises(ValueError, match="Unknown task type"):
            await taskboard.handle_task(BusMessage(
                type=MessageType.TASK, source="orchestrator",
                target="taskboard",
                payload={"type": "execute_code", "code": "print(1)"},
            ))


class TestOrchestratorRouting:
    def test_board_task_routes_to_taskboard_brain(self):
        from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator
        from bigbrain.bus.bus import MessageBus

        orch = WorkspaceOrchestrator("default", MessageBus(auth=None))
        plan_id = "p1"
        subtasks = orch._simple_decompose(plan_id, {
            "type": "board_task",
            "title": "une tâche",
        })
        assert subtasks[0].brain_target == "taskboard"
        assert subtasks[0].payload["type"] == "board_task"


class TestSummarizerGrounding:
    """Board-action results must reach the summarizer as REAL actions,
    and the summarizer must not invent actions the output never shows."""

    @pytest.fixture
    def brain(self):
        from bigbrain.front.front_brain import FrontBrain

        class CapturingProvider:
            def __init__(self):
                self.calls = []

            async def chat_complete(self, messages=None, **kwargs):
                self.calls.append(messages)
                return "résumé honnête"

        provider = CapturingProvider()
        from bigbrain.bus.bus import MessageBus

        return FrontBrain(MessageBus(auth=None), llm_provider=provider), provider

    async def test_board_action_reaches_the_summarizer(self, brain):
        front, provider = brain
        # The summarizer relays the answer to the user's last question.
        front._conversation_history.append(
            {"role": "user", "content": "ajoute une tâche à la taskboard"})
        summary = await front._summarize_result([
            ("action", "Task 'mettre à jour le README' added to the board as todo."),
        ])
        assert summary == "résumé honnête"
        prompt = provider.calls[0][1]["content"]
        assert "Action performed:" in prompt
        assert "added to the board" in prompt

    async def test_grounding_rules_are_in_the_prompt(self, brain):
        front, provider = brain
        front._conversation_history.append(
            {"role": "user", "content": "fais quelque chose"})
        await front._summarize_result([("code", "print('hi')")])
        system = provider.calls[0][0]["content"]
        # The summarizer must not invent actions the output never shows.
        assert "NEVER claim a task was created" in system
        assert "instead of pretending success" in system

    async def test_code_result_is_not_an_action_block(self, brain):
        """A code result alone must not produce an 'Action performed'
        block — the summarizer only sees what really ran."""
        front, provider = brain
        front._conversation_history.append(
            {"role": "user", "content": "affiche hello"})
        await front._summarize_result([("code", "Hello, World!")])
        prompt = provider.calls[0][1]["content"]
        assert "Action performed:" not in prompt
