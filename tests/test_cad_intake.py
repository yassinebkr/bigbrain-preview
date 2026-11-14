"""Early routing, specialist ownership and durable drawing intake boundaries."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bigbrain.cad_intake import prepare_drawing
from bigbrain.cad_planning import CadClarificationRequired
from bigbrain.front.cad_context import design_context
from bigbrain.front.decision import FRONT_TOOL_SCHEMA, FrontDecision
from tests.test_cad_clarification import fixture


def test_front_wire_routes_cad_without_a_dimension_inventory():
    schema = FRONT_TOOL_SCHEMA['parameters']
    assert 'DrawingSpecification' not in schema['$defs']
    assert 'drawing' not in schema['$defs']['CadInput']['properties']
    decision = FrontDecision.model_validate({'decision': {'operation': 'delegate',
        'reply': 'Je transmets le dessin au spécialiste CAO.', 'objective': 'Créer la pièce jointe.',
        'route': {'brain': 'cad_brain', 'payload': {'type': 'model_cad', 'intake': True}}}})
    assert decision.decision.task_payload()['route']['payload']['intake'] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('clarify', [False, True])
async def test_specialist_intake_retains_sources_and_questions(clarify):
    store, sid, _, drawing = fixture()
    if clarify:
        drawing['dimensions'][0].update(value=None, origin='unresolved')
    question = 'Quelle largeur faut-il utiliser ?' if clarify else None
    provider = SimpleNamespace(entry=SimpleNamespace(vision=True), chat_complete=AsyncMock(
        return_value=json.dumps({'decision': {'drawing': drawing, 'question': question}})))
    bus = SimpleNamespace(broadcast_event=AsyncMock())
    payload = {'session_id': sid, 'user_request': 'Créer le support du dessin.'}
    if clarify:
        with pytest.raises(CadClarificationRequired, match='largeur'):
            await prepare_drawing(provider, payload, bus, 'orchestrator_default')
    else:
        result = await prepare_drawing(provider, payload, bus, 'orchestrator_default')
        assert result.dimensions[0].value == 60
    context, sources = design_context(sid)
    assert context['drawing']['sources'][0]['attachment_id'] == sources[0]['id']
    assert context['status'] == ('clarifying' if clarify else 'proposed')
    assert context['question'] == question
    request = provider.chat_complete.call_args.kwargs
    assert request['tool_schema']['parameters']['properties']['decision']
    assert any(block.get('type') == 'image_url' for block in request['messages'][1]['content'])
    assert bus.broadcast_event.call_args_list[-1].kwargs['event_type'] == 'cad.intake.finished'
    # Reopening the persisted session must recover this exact interpretation.
    assert store.get(sid)['cad_context']['drawing'] == context['drawing']


@pytest.mark.asyncio
async def test_intake_rejects_foreign_sources_before_persistence():
    _, sid, _, drawing = fixture()
    foreign = {'attachment_id': 'att-000000000000', 'sha256': 'a' * 64}
    drawing['sources'] = [foreign]
    drawing['dimensions'][0]['sources'] = [foreign]
    provider = SimpleNamespace(entry=SimpleNamespace(vision=True), chat_complete=AsyncMock(
        return_value=json.dumps({'decision': {'drawing': drawing, 'question': None}})))
    with pytest.raises(ValueError, match='extérieure'):
        await prepare_drawing(provider, {'session_id': sid, 'user_request': 'Créer la pièce'},
            SimpleNamespace(broadcast_event=AsyncMock()), 'orchestrator_default')
    assert design_context(sid)[0] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['cancel', 'revision_changed'])
async def test_intake_preserves_revision_when_provider_cannot_commit(outcome):
    store, sid, _, drawing = fixture()
    async def respond(**kwargs):
        if outcome == 'cancel':
            raise asyncio.CancelledError()
        store.set_cad_context(sid, {'status': 'clarifying', 'question': 'Nouvelle précision'})
        return json.dumps({'decision': {'drawing': drawing, 'question': None}})
    provider = SimpleNamespace(entry=SimpleNamespace(vision=True), chat_complete=respond)
    error = asyncio.CancelledError if outcome == 'cancel' else ValueError
    with pytest.raises(error):
        await prepare_drawing(provider, {'session_id': sid, 'user_request': 'Créer la pièce'},
            SimpleNamespace(broadcast_event=AsyncMock()), 'orchestrator_default')
    context = store.get(sid).get('cad_context')
    assert context is None if outcome == 'cancel' else context['question'] == 'Nouvelle précision'


@pytest.mark.asyncio
async def test_normal_proposal_uses_selected_cad_provider_and_waits_for_confirmation(tmp_path, monkeypatch):
    from bigbrain.bus.bus import MessageBus
    from bigbrain.bus.message import BusMessage, MessageType
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator
    from bigbrain.brains import cad_brain
    store, sid, _, drawing = fixture()
    planner = SimpleNamespace(chat_complete=AsyncMock(side_effect=AssertionError('Planner must preserve CAD role ownership')))
    specialist = SimpleNamespace(entry=SimpleNamespace(vision=True), chat_complete=AsyncMock(
        return_value=json.dumps({'decision': {'drawing': drawing, 'question': None}})))
    bus = MessageBus(tmp_path / 'bus', auth=None)
    orchestrator = WorkspaceOrchestrator('default', bus, llm_provider=planner)
    orchestrator.cad_intake_provider = specialist
    orchestrator.register_brain('cad_brain', {'description': 'CAD'})
    request = BusMessage(type=MessageType.TASK, source='front_brain', target=orchestrator.name,
        payload={'brain': 'cad_brain', 'type': 'model_cad', 'intake': True,
                 'session_id': sid, 'user_request': 'Créer le support du dessin.'})
    plan = await orchestrator._create_task_plan(request)
    store.set_cad_context(sid, {'run_id': plan.id, 'status': 'proposed'})
    monkeypatch.setattr(cad_brain, 'solidcraft_executable', lambda: tmp_path / 'unused-native')
    spec = await orchestrator._propose_contracts(plan, request.payload['user_request'])
    assert spec.metadata['cad']['definition']['drawing']['title'] == drawing['title']
    assert specialist.chat_complete.await_count == 1
    assert planner.chat_complete.await_count == 0
    assert plan.awaiting_approval
    assert not plan.subtasks[0].result
    await bus.close()
