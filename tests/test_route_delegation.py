"""LLM-native routing: the Front Brain emits an explicit route
(brain + payload) and the orchestrator honors it verbatim.

This is tool-call routing — no keyword matching anywhere. The LLM decides,
the orchestrator executes deterministically.
"""

import json
import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType


ROUTE_JSON = (
    '{"reply": "Ajouté à ta taskboard.", "route": {"brain": "taskboard", '
    '"payload": {"type": "board_task", "title": "Mettre à jour le README", '
    '"status": "todo"}}}'
)


@pytest.mark.asyncio
@pytest.mark.parametrize('chunks', [["Je relance.\n", ROUTE_JSON], list("Je relance.\n```json\n" + ROUTE_JSON + "\n```")])
async def test_v1_rejects_unexpected_stream_without_leaking_action(chunks):
    class Provider:
        async def chat_complete(self, **kwargs):
            async def stream():
                for chunk in chunks:
                    yield chunk
            return stream()
    front, bus = _make_front(Provider())
    await front._handle_ui_message(BusMessage(type=MessageType.TASK, source='morphable_ui', target='front_brain',
        payload={'text': 'Réessaie', 'session_id': 's1'}))
    deltas = ''.join(p['delta'] for kind, p in bus.events if kind == 'chat.delta')
    assert deltas == ''
    assert len(bus.tasks) == 0
    replies = [(kind, p) for kind, p in bus.events if kind in {'chat.message', 'chat.done'}]
    assert len(replies) == 1 and replies[0][0] == 'chat.message'
    assert 'Aucune nouvelle tâche' in replies[0][1]['text']


@pytest.mark.asyncio
async def test_ordinary_braces_and_code_are_released_without_routing():
    class Provider:
        async def chat_complete(self, **kwargs):
            assert kwargs['stream'] is False
            return json.dumps({'decision':{'operation':'respond','reply':'Voici `dict` : {"value": 1}'}})
    front, bus = _make_front(Provider())
    await front._handle_ui_message(BusMessage(type=MessageType.TASK, source='morphable_ui', target='front_brain',
        payload={'text': 'Explique dict', 'session_id': 's1'}))
    assert not any(kind == 'chat.delta' for kind, _ in bus.events)
    assert next(p['text'] for kind,p in bus.events if kind == 'chat.message') == 'Voici `dict` : {"value": 1}'
    assert not bus.tasks


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
        # Adapt the frozen legacy routing fixtures to the new provider contract;
        # the production front never accepts these legacy shapes directly.
        try:
            old = json.loads(response)
        except (ValueError,TypeError):
            old = None
        if isinstance(old,dict) and ('route' in old or 'task' in old):
            route = old.get('route',{})
            payload = route.get('payload',{})
            objective = payload.get('query') or old.get('task') or payload.get('title') or 'Requested action'
            fields = {k:v for k,v in old.items() if k not in {'task'}}
            if route.get('brain') == 'researcher':
                fields['route'] = {**route,'payload':{k:v for k,v in payload.items() if k != 'query'}}
            self.response = json.dumps({'decision':{'operation':'delegate','objective':objective,**fields}})
        else:
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

    async def send_task(self, source, target, task_data, priority=None, require_target=False, on_accepted=None):
        self.tasks.append((target, task_data))
        if on_accepted:
            await on_accepted()

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
    @pytest.mark.parametrize("followup", ["réessaie", "continue la demande précédente"])
    async def test_research_followup_keeps_resolved_objective_through_dispatch(self, followup):
        from unittest.mock import AsyncMock
        from bigbrain.brains.researcher import ResearcherBrain
        from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator
        objective = "Compare Python 3.13 and 3.7 Path.unlink missing_ok using official documentation."
        provider = RecordingProvider(json.dumps({"reply":"Je relance la recherche.",
            "route":{"brain":"researcher","payload":{"type":"research","query":objective}}}))
        front, bus = _make_front(provider)
        front.register_brain("researcher", "research official documentation")
        await front._handle_ui_message(BusMessage(type=MessageType.TASK, source="morphable_ui", target="front_brain",
            payload={"text":followup,"session_id":"retry-session"}))
        dispatched = bus.tasks[0][1]
        assert dispatched["user_request"] == objective
        assert dispatched["user_message"] == followup
        assert dispatched["session_id"] == "retry-session"
        assert next(p for kind,p in bus.events if kind == "task.routing")["description"] == objective
        orch = WorkspaceOrchestrator("default", MessageBus(auth=None))
        orch.register_brain("researcher", {"description":"research"})
        plan = await orch._create_task_plan(BusMessage(type=MessageType.TASK, source="front_brain",
            target="orchestrator_default", payload=dispatched))
        brain = ResearcherBrain("researcher", MessageBus(auth=None), search_provider=AsyncMock())
        brain._full_research = AsyncMock(return_value={"success":True})
        await brain.handle_task(BusMessage(type=MessageType.TASK, source="orchestrator_default", target="researcher",
            payload=plan.subtasks[0].payload))
        assert brain._full_research.call_args.args[0] == objective

    async def test_research_query_precedes_legacy_raw_user_request(self):
        from unittest.mock import AsyncMock
        from bigbrain.brains.researcher import ResearcherBrain
        brain = ResearcherBrain("researcher", MessageBus(auth=None), search_provider=AsyncMock())
        brain._full_research = AsyncMock(return_value={"success":True})
        await brain.handle_task(BusMessage(type=MessageType.TASK, source="orchestrator_default", target="researcher",
            payload={"type":"research","query":"Resolved research objective","user_request":"réessaie"}))
        assert brain._full_research.call_args.args[0] == "Resolved research objective"

    async def test_validation_change_proposal_is_forwarded_not_granted_as_permission(self):
        decision = {'path': 'tests/test_old.py', 'reason': 'Conflicting expected result',
                    'expected_behavior': 'Return the requested sum', 'authority': 'Explicit user requirement'}
        provider = RecordingProvider(json.dumps({'reply': 'Je propose un nouveau contrat.',
            'task': 'Repair the existing project after arbitration',
            'project_target': {'mode': 'existing', 'path': 'sandbox/calculator'}, 'test_changes': [decision]}))
        front, bus = _make_front(provider)
        await front._handle_ui_message(BusMessage(type=MessageType.TASK, source='morphable_ui', target='front_brain',
            payload={'text': 'Propose the correction', 'session_id': 's1'}))
        assert bus.tasks[0][1]['test_changes'] == [decision]
        assert '_approved_test_paths' not in bus.tasks[0][1]

    async def test_stop_during_provider_wait_prevents_delegation(self):
        class StoppingProvider:
            async def chat_complete(self, **kwargs):
                front.request_stop()
                return ROUTE_JSON

        front, bus = _make_front(StoppingProvider())
        await front._handle_ui_message(BusMessage(
            type=MessageType.TASK, source="morphable_ui", target="front_brain",
            payload={"text": "do something", "session_id": "s1"}))
        assert bus.tasks == []
        assert not any(event == "task.routing" for event, _ in bus.events)

    async def test_route_sends_brain_task_to_orchestrator(self):
        provider = RecordingProvider(ROUTE_JSON)
        front, bus = _make_front(provider)
        front._current_project = lambda: "sandbox/existing-project"

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
        assert "project_path" not in task_data
        assert task_data.get("project_target") is None
        assert task_data["user_request"] == "Mettre à jour le README"
        assert "taskboard" in task_data["user_message"]

        # The acknowledgment reached the chat first
        assert next(p['text'] for kind,p in bus.events if kind == 'chat.message') == "Ajouté à ta taskboard."
        assert next(i for i,(kind,_) in enumerate(bus.events) if kind == 'task.routing') < next(i for i,(kind,_) in enumerate(bus.events) if kind == 'chat.message')

    async def test_invalid_route_produces_protocol_error_without_dispatch(self):
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
        assert any(kind == 'front.decision_failed' for kind,_ in bus.events)
        assert 'Aucune nouvelle tâche' in next(p['text'] for kind,p in bus.events if kind == 'chat.message')


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
        from bigbrain.web.fs_api import workspace_root
        directory = workspace_root() / "sandbox" / "hello"
        directory.mkdir(parents=True)
        (directory / ".project.json").write_text('{}')

        plan = await orch._create_task_plan(BusMessage(
            type=MessageType.TASK, source="front_brain",
            target="orchestrator_default",
            payload={
                "type": "run_file",
                "brain": "python_brain",
                "file": "hello.py",
                "user_request": "run hello.py",
                "project_target": {"mode": "existing", "path": "sandbox/hello"},
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
