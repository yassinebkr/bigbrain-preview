"""Deterministic fault injection, NOT a live LLM/product campaign."""

import asyncio
import json

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator


class ScriptedProvider:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def chat_complete(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("Unexpected extra LLM call")
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result if isinstance(result, str) else json.dumps(result)


def assessment(deliverable="web_app", mode="project"):
    return {"mode": mode, "deliverable_type": deliverable, "needs_research": False,
            "research_queries": [], "reason": "browser UI"}


def spec(deliverable="web_app"):
    return {"project_name": "react-learning", "deliverable_type": deliverable,
            "acceptance_contracts": ["La progression est conservée après reload", "Les séances peuvent être cochées"],
            "file_specs": [{"path": "src/App.tsx" if deliverable == "web_app" else "main.py",
                            "purpose": "Learning application"}]}


def request(orch):
    return BusMessage(type=MessageType.TASK, source="front_brain", target=orch.name,
                      payload={"type": "compound", "user_request": "Organise mon apprentissage",
                               "session_id": "sess-react"})


@pytest.fixture
def make_orch(tmp_path):
    def factory(provider=None):
        return WorkspaceOrchestrator("default", MessageBus(tmp_path / "logs", auth=None),
                                     llm_provider=provider)
    return factory


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["project", "script"])
async def test_llm_web_decision_is_preserved_even_for_a_small_app(make_orch, mode):
    provider = ScriptedProvider(assessment(mode=mode), spec())
    orch = make_orch(provider)
    plan = await orch._create_task_plan(request(orch))
    assert plan.project_spec.deliverable_type == "web_app"
    assert plan.project_spec.web_stack == "react_vite"
    assert {s.brain_target for s in plan.subtasks} == {"web_app_brain"}
    assert plan.subtasks[-1].payload["type"] == "assemble_and_preview"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["not JSON", "[]", "{}", '{"mode":"script"}',
    json.dumps({**assessment(), "deliverable_type": "unknown"}),
    json.dumps({**assessment(), "needs_research": "false"}),
    json.dumps({**assessment(), "research_queries": "not an array"})])
async def test_invalid_assessment_never_defaults_to_python(make_orch, bad):
    provider = ScriptedProvider(bad)
    orch = make_orch(provider)
    with pytest.raises(ValueError, match="assessment"):
        await orch._create_task_plan(request(orch))
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_architect_repair_is_bounded_and_never_uses_legacy_python(make_orch):
    provider = ScriptedProvider(assessment(), "bad architecture", "bad architecture again")
    orch = make_orch(provider)
    with pytest.raises(ValueError, match="architect"):
        await orch._create_task_plan(request(orch))
    assert len(provider.calls) == 3


@pytest.mark.asyncio
async def test_architect_can_repair_structure_without_changing_deliverable(make_orch):
    provider = ScriptedProvider(assessment(), "bad architecture", spec())
    orch = make_orch(provider)
    plan = await orch._create_task_plan(request(orch))
    assert {s.brain_target for s in plan.subtasks} == {"web_app_brain"}
    assert len(provider.calls) == 3


@pytest.mark.asyncio
async def test_contradictory_architect_cannot_override_the_web_decision(make_orch):
    provider = ScriptedProvider(assessment(), spec("python"), spec("python"))
    orch = make_orch(provider)
    with pytest.raises(ValueError, match="architect"):
        await orch._create_task_plan(request(orch))


@pytest.mark.asyncio
async def test_missing_provider_is_not_permission_to_generate_python(make_orch):
    orch = make_orch()
    with pytest.raises(ValueError, match="provider"):
        await orch._create_task_plan(request(orch))


@pytest.mark.asyncio
async def test_timeout_and_stop_do_not_trigger_another_planner(make_orch):
    provider = ScriptedProvider(assessment(), TimeoutError("architect timeout"))
    orch = make_orch(provider)
    with pytest.raises(ValueError, match="architect"):
        await orch._create_task_plan(request(orch))
    assert len(provider.calls) == 2
    stopped = ScriptedProvider(assessment(), asyncio.CancelledError())
    orch = make_orch(stopped)
    with pytest.raises(asyncio.CancelledError):
        await orch._create_task_plan(request(orch))
    assert len(stopped.calls) == 2


@pytest.mark.asyncio
async def test_planning_failure_closes_the_run_once_without_contract_or_dispatch(make_orch):
    orch = make_orch(ScriptedProvider(assessment(), "invalid", "still invalid"))
    events = []

    async def observe(message):
        events.append(message)

    orch.bus.subscribe("*", observe)
    await orch._handle_task_request(request(orch))
    terminal = [m for m in events if m.payload.get("event") == "task.failed"]
    assert len(terminal) == 1
    assert terminal[0].payload["session_id"] == "sess-react"
    assert terminal[0].payload["runnable"] is False
    assert terminal[0].payload["stage"] == "architect"
    assert len([m for m in events if m.type == MessageType.RESULT]) == 1
    assert not any(m.type == MessageType.TASK for m in events)
    assert not any(m.payload.get("event") == "contracts.proposal" for m in events)
    await orch.bus.close()


@pytest.mark.asyncio
async def test_python_project_and_direct_actions_remain_in_their_own_brain(make_orch):
    orch = make_orch(ScriptedProvider(assessment("python"), spec("python")))
    plan = await orch._create_task_plan(request(orch))
    assert {s.brain_target for s in plan.subtasks} == {"python_brain"}
    direct = make_orch()
    plan = await direct._create_task_plan(BusMessage(
        type=MessageType.TASK, source="front_brain", target=direct.name,
        payload={"type": "research", "query": "some topic"}))
    assert plan.subtasks[0].brain_target == "researcher"


@pytest.mark.asyncio
async def test_proposal_uses_architect_contracts_without_a_third_llm_call(make_orch):
    provider = ScriptedProvider(assessment(), spec())
    orch = make_orch(provider)
    await orch._handle_task_request(request(orch))
    plan = next(iter(orch.task_plans.values()))
    assert plan.awaiting_approval is True
    assert len(provider.calls) == 2
    assert plan.project_spec.acceptance_contracts == spec()["acceptance_contracts"]


@pytest.mark.asyncio
@pytest.mark.parametrize('files', [
    [{'path': 'a.tsx', 'dependencies': ['missing.tsx']}],
    [{'path': 'a.tsx', 'dependencies': ['b.tsx']}, {'path': 'b.tsx', 'dependencies': ['a.tsx']}],
    [{'path': 'src/App.tsx'}, {'path': 'src/App.tsx'}],
    [{'path': '../escape.tsx'}],
])
async def test_unsafe_or_impossible_graphs_never_reach_contract_approval(make_orch, files):
    broken = {**spec(), 'file_specs': files}
    orch = make_orch(ScriptedProvider(assessment(), broken, broken))
    with pytest.raises(ValueError, match='architect'):
        await orch._create_task_plan(request(orch))


@pytest.mark.asyncio
async def test_a_hanging_provider_is_actually_cancelled_at_the_deadline(make_orch, monkeypatch):
    cancelled = asyncio.Event()
    class HangingProvider:
        async def chat_complete(self, **kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
    real_wait_for = asyncio.wait_for
    async def short_deadline(awaitable, timeout):
        return await real_wait_for(awaitable, timeout=0.01)
    monkeypatch.setattr(asyncio, 'wait_for', short_deadline)
    orch = make_orch(HangingProvider())
    with pytest.raises(ValueError, match='assessment'):
        await orch._create_task_plan(request(orch))
    assert cancelled.is_set()
