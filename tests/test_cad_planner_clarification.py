"""Specialist questions suspend CAD preparation with conversation-owned state."""

import json
from unittest.mock import AsyncMock

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.cad_drawings import DrawingSpecification
from bigbrain.cad_planning import CadClarification, CadClarificationRequired, draft_cad_plan
from bigbrain.front.front_brain import FrontBrain
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, TaskPlan, TaskStatus, SubTask
from bigbrain.web.sessions import SessionStore
from tests.test_cad_clarification import fixture


@pytest.mark.asyncio
async def test_planner_question_has_no_recipe_or_dispatch():
    _, _, _, data = fixture()
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps({'outcome': 'clarification',
        'question': 'Quelle surface désigne ce rayon ?', 'dimension_ids': ['width'], 'reason': 'missing'})
    with pytest.raises(CadClarificationRequired) as result:
        await draft_cad_plan(provider, 'Model the drawing', drawing=DrawingSpecification.model_validate(data))
    assert result.value.clarification.dimension_ids == ('width',)
    provider.chat_complete.return_value = json.dumps({'outcome': 'clarification',
        'question': 'Quelle surface ?', 'dimension_ids': ['invented'], 'reason': 'missing'})
    with pytest.raises(ValueError, match='unknown drawing'):
        await draft_cad_plan(provider, 'Model the drawing', drawing=DrawingSpecification.model_validate(data))


@pytest.mark.asyncio
async def test_specialist_question_persists_and_prevents_worker_dispatch(tmp_path):
    store, sid, _, data = fixture()
    store.set_cad_context(sid, {'run_id': 'cad-run', 'drawing': data,
                               'status': 'proposed', 'sources': [], 'exchanges': []})
    bus = MessageBus(tmp_path / 'logs', auth=None)
    frames = []
    async def observe(frame):
        frames.append(frame)
    bus.subscribe('*', observe)
    orch = WorkspaceOrchestrator('default', bus)
    original = BusMessage(type=MessageType.TASK, source='front_brain', target=orch.name,
                          payload={'session_id': sid})
    plan = TaskPlan(id='cad-run', original_task=original)
    question = CadClarification(outcome='clarification', question='Quelle surface pour R25 ?',
                                dimension_ids=['width'], reason='missing')
    await orch._request_cad_clarification(plan, question)
    await orch._execute_ready_subtasks(plan)
    await bus.close()
    saved = SessionStore().get(sid)['cad_context']
    assert saved['status'] == 'clarifying' and saved['revision'] == 2
    assert saved['question'] == question.question
    assert saved['drawing']['issues'][0]['blocking'] is True
    assert plan.status == TaskStatus.NEEDS_INPUT and not plan.awaiting_approval
    assert not any(frame.type == MessageType.TASK for frame in frames)
    assert not any(frame.payload.get('event') in {'task.failed', 'contracts.proposal', 'task.complete'} for frame in frames)
    assert any(frame.payload.get('event') == 'task.clarification' for frame in frames)


@pytest.mark.asyncio
async def test_stale_specialist_question_cannot_overwrite_new_dossier(tmp_path):
    store, sid, _, data = fixture()
    store.set_cad_context(sid, {'run_id': 'newer-run', 'drawing': data, 'question': 'Current'})
    bus = MessageBus(tmp_path / 'logs', auth=None)
    orch = WorkspaceOrchestrator('default', bus)
    plan = TaskPlan(id='old-run', original_task=BusMessage(type=MessageType.TASK,
        source='front_brain', target=orch.name, payload={'session_id': sid}))
    question = CadClarification(outcome='clarification', question='Old question', reason='missing')
    with pytest.raises(ValueError, match='superseded'):
        await orch._request_cad_clarification(plan, question)
    assert store.get(sid)['cad_context']['question'] == 'Current'
    await bus.close()


@pytest.mark.asyncio
async def test_front_relays_specialist_question_without_inference(tmp_path):
    bus = MessageBus(tmp_path / 'logs', auth=None)
    provider = AsyncMock()
    front = FrontBrain(bus, llm_provider=provider)
    front._emit_chat_message = AsyncMock()
    await front._handle_task_result(BusMessage(type=MessageType.RESULT,
        source='orchestrator_default', target='front_brain', payload={
            'result_kind': 'cad_clarification', 'question': 'Quelle surface ?', 'session_id': 's'}))
    front._emit_chat_message.assert_awaited_once_with('assistant', 'Quelle surface ?', session_id='s')
    provider.chat_complete.assert_not_called()
    await bus.close()


@pytest.mark.asyncio
async def test_task_request_handles_typed_question_before_contract_or_execution(tmp_path, monkeypatch):
    monkeypatch.setenv('BIGBRAIN_CONTRACTS', '1')
    store, sid, _, data = fixture()
    store.set_cad_context(sid, {'run_id': 'request-run', 'drawing': data, 'status': 'proposed'})
    bus = MessageBus(tmp_path / 'logs', auth=None)
    orch = WorkspaceOrchestrator('default', bus)
    original = BusMessage(type=MessageType.TASK, source='front_brain', target=orch.name,
                          payload={'session_id': sid, 'user_request': 'Create the drawing'})
    plan = TaskPlan(id='request-run', original_task=original, subtasks=[SubTask(
        id='cad-step', description='Create drawing', brain_target='cad_brain',
        payload={'type': 'model_cad'})])
    orch._create_task_plan = AsyncMock(return_value=plan)
    orch._auto_checkpoint_before_execution = AsyncMock()
    orch._propose_contracts = AsyncMock(side_effect=CadClarificationRequired(CadClarification(
        outcome='clarification', question='Quelle surface ?', reason='missing')))
    orch._execute_ready_subtasks = AsyncMock()
    orch._report_planning_failure = AsyncMock()
    await orch._handle_task_request(original)
    assert plan.status == TaskStatus.NEEDS_INPUT
    orch._execute_ready_subtasks.assert_not_called()
    orch._report_planning_failure.assert_not_called()
    await bus.close()
