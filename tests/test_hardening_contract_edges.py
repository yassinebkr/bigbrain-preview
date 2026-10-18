"""Approval and lifecycle faults must never authorize unrecorded execution."""

import asyncio
import hashlib
from unittest.mock import AsyncMock

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.orchestrator.architect import ProjectSpec
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, TaskPlan, TaskStatus, SubTask
from bigbrain.verification.evidence import default_repository
from bigbrain.web.server import WebServer


@pytest.fixture
def pending(tmp_path):
    orch = WorkspaceOrchestrator('default', MessageBus(tmp_path / 'logs', auth=None))
    original = BusMessage(type=MessageType.TASK, source='front_brain', target=orch.name,
                          payload={'session_id': 'sess-contract'})
    plan = TaskPlan(id='p-contract', original_task=original, status=TaskStatus.RUNNING,
                    project_spec=ProjectSpec(project_name='learning', description='learning',
                        acceptance_contracts=['Le parcours est consultable', 'La progression est persistée']))
    orch.task_plans[plan.id] = plan
    orch._execute_ready_subtasks = AsyncMock()
    return orch, plan


@pytest.mark.asyncio
@pytest.mark.parametrize('persistence_failure', ['missing', 'exception'])
async def test_failed_approval_persistence_keeps_plan_paused(pending, monkeypatch, persistence_failure):
    orch, plan = pending
    await orch._propose_contracts(plan, 'application apprentissage')
    repo = default_repository()
    if persistence_failure == 'missing':
        monkeypatch.setattr(repo, 'approve_spec', lambda *a, **kw: None)
    else:
        def fail(*a, **kw):
            raise OSError('disk unavailable')
        monkeypatch.setattr(repo, 'approve_spec', fail)
    # The factory returns a fresh repository object for the same root.
    monkeypatch.setattr('bigbrain.verification.evidence.default_repository', lambda: repo)
    await orch._handle_contracts_approval({'plan_id': plan.id, 'design_id': plan.approval_design_id, 'approve': True})
    assert plan.awaiting_approval is True
    orch._execute_ready_subtasks.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', [{'design_id': 'another-design', 'approve': True},
                                  {'approve': 'false'}, {'approve': 1}])
async def test_invalid_decision_cannot_approve_another_or_untyped_contract(pending, invalid):
    orch, plan = pending
    await orch._propose_contracts(plan, 'application apprentissage')
    await orch._handle_contracts_approval({'plan_id': plan.id,
        'design_id': plan.approval_design_id, **invalid})
    assert plan.awaiting_approval is True
    orch._execute_ready_subtasks.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_approval_dispatches_once(pending):
    orch, plan = pending
    await orch._propose_contracts(plan, 'application apprentissage')
    decision = {'plan_id': plan.id, 'design_id': plan.approval_design_id, 'approve': True}
    await asyncio.gather(orch._handle_contracts_approval(decision), orch._handle_contracts_approval(decision))
    orch._execute_ready_subtasks.assert_awaited_once()


@pytest.mark.asyncio
async def test_rejected_contract_cannot_be_approved_afterwards(pending):
    orch, plan = pending
    await orch._propose_contracts(plan, 'application apprentissage')
    decision = {'plan_id': plan.id, 'design_id': plan.approval_design_id, 'approve': False}
    await orch._handle_contracts_approval(decision)
    await orch._handle_contracts_approval({**decision, 'approve': True})
    assert plan.status == TaskStatus.CANCELLED
    orch._execute_ready_subtasks.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_request_cannot_resurrect_different_old_contracts(pending):
    orch, plan = pending
    old = await orch._propose_contracts(plan, 'same exact request')
    plan.project_spec.acceptance_contracts = ['Nouvelle exigence réelle', 'Une autre exigence réelle']
    new = await orch._propose_contracts(plan, 'same exact request')
    assert new.revision > old.revision
    assert 'Nouvelle exigence réelle' in new.contracts
    assert default_repository().load_spec(old.design_id, old.revision).contracts == old.contracts


@pytest.mark.asyncio
async def test_contracts_that_arrive_after_stop_do_not_resurrect_a_proposal(pending):
    orch, plan = pending
    started, finish = asyncio.Event(), asyncio.Event()
    class SlowProvider:
        async def chat_complete(self, **kwargs):
            started.set()
            await finish.wait()
            return '["requirement one", "requirement two"]'
    orch.llm_provider = SlowProvider()
    plan.project_spec = None
    task = asyncio.create_task(orch._propose_contracts(plan, 'a request'))
    await started.wait()
    await orch._cancel_task(plan.id, 'soft')
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert plan.awaiting_approval is False
    design_id = 'task-' + hashlib.sha256(b'a request').hexdigest()[:16]
    assert default_repository().load_latest_spec(design_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [[], None, {'design_id': 'd', 'plan_id': 'p', 'approve': 'false'},
                                {'design_id': 'd', 'plan_id': 'p', 'approve': 1}])
async def test_http_decision_requires_a_boolean_and_object(tmp_path, body):
    class Request:
        async def json(self):
            return body
    server = WebServer(MessageBus(tmp_path / 'logs', auth=None))
    response = await server._handle_contracts_approve(Request())
    assert response.status == 400


@pytest.mark.asyncio
async def test_missing_proposal_closes_preparation_without_dispatch(pending):
    orch, plan = pending
    plan.subtasks = [SubTask(id='s', description='write', brain_target='python_brain',
                            payload={'type': 'generate_and_execute'})]
    orch._create_task_plan = AsyncMock(return_value=plan)
    orch._propose_contracts = AsyncMock(return_value=None)
    await orch._handle_task_request(plan.original_task)
    assert orch.task_plans[plan.id].status == TaskStatus.FAILED
    orch._execute_ready_subtasks.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_approval_after_restart_is_a_visible_failure_not_a_silent_ack(pending):
    orch, _ = pending
    orch.bus.broadcast_event = AsyncMock()
    await orch._handle_contracts_approval({'plan_id': 'lost-after-restart', 'design_id': 'd', 'approve': True})
    event = orch.bus.broadcast_event.await_args.kwargs
    assert event['event_type'] == 'contracts.approval_failed'
    assert event['payload']['plan_id'] == 'lost-after-restart'
    orch._execute_ready_subtasks.assert_not_awaited()
