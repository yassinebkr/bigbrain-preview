"""LLM-native routing: the Front Brain emits an explicit route
(brain + payload) and the orchestrator honors it verbatim.

This is tool-call routing — no keyword matching anywhere. The LLM decides,
the orchestrator executes deterministically.
"""

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType


ROUTE_JSON = (
    '{"reply": "Ajouté à ta taskboard.", "route": {"brain": "taskboard", '
    '"payload": {"type": "board_task", "title": "Mettre à jour le README", '
    '"status": "todo"}}}'
)


class TestRouteParsing:
    def _parse(self, response):
        from bigbrain.front.front_brain import FrontBrain
        return FrontBrain._try_parse_delegation(response)

    def test_raw_route_json(self):
        parsed = self._parse(ROUTE_JSON)
        assert parsed["route"]["brain"] == "taskboard"
        assert parsed["route"]["payload"]["type"] == "board_task"
        assert parsed["route"]["payload"]["status"] == "todo"

    def test_route_json_in_prose(self):
        parsed = self._parse(f"Sure thing!\n{ROUTE_JSON}\nDone.")
        assert parsed is not None
        assert parsed["route"]["brain"] == "taskboard"

    def test_route_json_in_markdown_fence(self):
        fenced = f"```json\n{ROUTE_JSON}\n```"
        parsed = self._parse(fenced)
        assert parsed is not None
        assert parsed["route"]["payload"]["title"] == "Mettre à jour le README"

    def test_task_format_still_parses(self):
        parsed = self._parse(
            '{"reply": "On it.", "task": "Write a fibonacci function"}')
        assert parsed["task"] == "Write a fibonacci function"

    def test_plain_text_is_not_delegation(self):
        assert self._parse("Bonjour ! Comment ça va ?") is None
        assert self._parse("") is None


class RecordingProvider:
    """LLM mock returning a fixed response, recording planning calls."""

    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    async def chat_complete(self, messages=None, **kwargs):
        self.calls += 1
        return self.response


class RecordingBus:
    """Bus stub capturing front brain emissions."""

    def __init__(self):
        self.tasks = []      # (target, task_data)
        self.events = []     # (event_type, payload)

    async def send_task(self, source, target, task_data, priority=None):
        self.tasks.append((target, task_data))

    async def broadcast_event(self, source, event_type, payload,
                              priority=None, **kwargs):
        self.events.append((event_type, payload))


def _make_front(provider):
    from bigbrain.front.front_brain import FrontBrain

    front = FrontBrain(MessageBus(auth=None), llm_provider=provider)
    front.register_brain("taskboard", "adds tasks to the board")
    bus = RecordingBus()
    front.bus = bus
    return front, bus


class TestFrontBrainRouteDispatch:
    async def test_route_sends_brain_task_to_orchestrator(self):
        provider = RecordingProvider(ROUTE_JSON)
        front, bus = _make_front(provider)

        await front._handle_ui_message(BusMessage(
            type=MessageType.TASK, source="morphable_ui",
            target="front_brain",
            payload={"text": "ajoute une tâche à la taskboard : "
                             "mettre à jour le README de near_agi",
                     "session_id": "s1"},
        ))

        assert len(bus.tasks) == 1
        target, task_data = bus.tasks[0]
        assert target == "orchestrator_default"
        assert task_data["brain"] == "taskboard"
        assert task_data["type"] == "board_task"
        assert task_data["title"] == "Mettre à jour le README"
        assert task_data["status"] == "todo"
        assert task_data["reply_to_ui"] is True
        assert "taskboard" in task_data["user_request"]

        # The acknowledgment reached the chat first
        assert bus.events[0][0] == "chat.message"
        assert bus.events[0][1]["text"] == "Ajouté à ta taskboard."

    async def test_invalid_route_falls_back_to_plain_text(self):
        # Malformed route (no payload type) must NOT be sent as a task —
        # the raw reply is shown to the user instead of being lost.
        provider = RecordingProvider(
            '{"reply": "On it.", "route": {"brain": "taskboard", '
            '"payload": {"title": "x"}}}')
        front, bus = _make_front(provider)

        await front._handle_ui_message(BusMessage(
            type=MessageType.TASK, source="morphable_ui",
            target="front_brain",
            payload={"text": "do something", "session_id": "s1"},
        ))

        assert bus.tasks == []  # nothing delegated
        assert bus.events[0][0] == "chat.message"


class TestOrchestratorHonorsRoute:
    def _orchestrator(self):
        from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator

        orch = WorkspaceOrchestrator("default", MessageBus(auth=None))
        orch.register_brain("taskboard", {"description": "board"})
        orch.register_brain("researcher", {"description": "research"})
        orch.brain_pools = {"python_brain": ["python_brain_0"]}
        return orch

    async def test_explicit_brain_skips_llm_planning(self):
        provider = RecordingProvider("")  # any planning call would use this
        orch = self._orchestrator()
        orch.llm_provider = provider

        plan = await orch._create_task_plan(BusMessage(
            type=MessageType.TASK, source="front_brain",
            target="orchestrator_default",
            payload={
                "type": "board_task",
                "brain": "taskboard",
                "title": "Mettre à jour le README",
                "status": "todo",
                "reply_to_ui": True,
                "user_request": "ajoute une tâche à la taskboard : "
                                "mettre à jour le README de near_agi",
            },
        ))

        assert provider.calls == 0  # executed verbatim, no re-planning
        assert len(plan.subtasks) == 1
        subtask = plan.subtasks[0]
        assert subtask.brain_target == "taskboard"
        assert subtask.payload["type"] == "board_task"
        assert "brain" not in subtask.payload  # stripped, not forwarded
        assert subtask.payload["title"] == "Mettre à jour le README"
        assert plan.tracker is not None

    async def test_route_to_pool_brain(self):
        orch = self._orchestrator()
        orch.llm_provider = RecordingProvider("")

        plan = await orch._create_task_plan(BusMessage(
            type=MessageType.TASK, source="front_brain",
            target="orchestrator_default",
            payload={
                "type": "run_file",
                "brain": "python_brain",
                "file": "hello.py",
                "user_request": "run hello.py",
            },
        ))

        assert len(plan.subtasks) == 1
        assert plan.subtasks[0].brain_target == "python_brain"

    async def test_unknown_brain_falls_back_to_planning(self):
        provider = RecordingProvider("")  # planning attempted → called
        orch = self._orchestrator()
        orch.llm_provider = provider

        # "brain" not in registry/pools → normal planning pipeline runs.
        # _assess_complexity gets the provider; its answer "" makes JSON
        # parsing fail → fallback to _simple_decompose.
        plan = await orch._create_task_plan(BusMessage(
            type=MessageType.TASK, source="front_brain",
            target="orchestrator_default",
            payload={
                "type": "board_task",
                "brain": "hallucinated_brain",
                "title": "x",
                "user_request": "ajoute une tâche",
            },
        ))

        assert provider.calls > 0  # planning was attempted
        # The fallback still routes board_task to the taskboard brain
        assert plan.subtasks[0].brain_target == "taskboard"
