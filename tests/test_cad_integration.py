"""CAD contract, worker, durable artifacts and HTTP reads with the real engine."""

import json

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from bigbrain.brains.cad_brain import CadBrain
from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.cad_store import CadStore
from bigbrain.front.decision import FrontDecision
from bigbrain.front.front_brain import FrontBrain
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator
from bigbrain.solidcraft import CadError, solidcraft_executable
from bigbrain.verification.evidence import default_repository
from bigbrain.web.cad_api import setup_cad_routes


def recipe(width=60):
    return {'title': 'Plaque dimensionnée', 'commands': [
        {'command': 'parameters.change', 'params': {'name': 'width', 'expression': f'{width} mm'}},
        {'command': 'solid.box', 'params': {'length': 'width', 'width': 40, 'height': 6}}],
        'criteria': [{'id': 'dimensions', 'label': 'Dimensions de la plaque',
                      'metric': 'dimensions_mm', 'expected': [width, 40, 6]},
                     {'id': 'volume', 'label': 'Volume de la plaque',
                      'metric': 'volume_mm3', 'expected': [width * 40 * 6]}]}


class Provider:
    """Deterministic planning input; native measurements remain actual tool results."""

    def __init__(self, plan):
        self.plan = plan
        self.calls = []

    async def chat_complete(self, **kwargs):
        self.calls.append(kwargs)
        return json.dumps(self.plan)


@pytest.fixture
def engine():
    try:
        return solidcraft_executable()
    except CadError:
        pytest.skip('Native SolidCraft 0.28.0 installation is required')


def test_native_front_route_preserves_cad_edit_identity():
    decision = FrontDecision.model_validate({'decision': {
        'operation': 'delegate', 'reply': 'Je prépare la pièce.', 'objective': 'Créer une plaque 60×40×6 mm.',
        'route': {'brain': 'cad_brain', 'payload': {'type': 'model_cad'}}}})
    assert decision.decision.task_payload()['route']['brain'] == 'cad_brain'
    assert decision.decision.task_payload()['route']['payload']['user_request'].startswith('Créer une plaque')


async def prepared(bus, plan_data, *, document_id=None, revision=None):
    provider = Provider(plan_data)
    orchestrator = WorkspaceOrchestrator('default', bus, llm_provider=provider)
    orchestrator.register_brain('cad_brain', {'description': 'CAD'})
    payload = {'brain': 'cad_brain', 'type': 'model_cad', 'session_id': 'session-cad',
               'user_request': 'Plaque mécanique ' + str(plan_data['criteria'][0]['expected'])}
    if document_id:
        payload.update(document_id=document_id, base_revision=revision)
    message = BusMessage(type=MessageType.TASK, source='morphable_ui', target=orchestrator.name, payload=payload)
    plan = await orchestrator._create_task_plan(message)
    assert len(plan.subtasks) == 1 and plan.subtasks[0].brain_target == 'cad_brain'
    spec = await orchestrator._propose_contracts(plan, payload['user_request'])
    return plan, spec, provider


def task(plan, spec):
    return BusMessage(type=MessageType.TASK, source='orchestrator_default', target='cad_brain', payload={
        **plan.subtasks[0].payload, '_plan_id': plan.id, '_subtask_id': plan.subtasks[0].id,
        'session_id': 'session-cad', 'contract_revision': {'design_id': spec.design_id, 'revision': spec.revision}})


@pytest.mark.asyncio
async def test_real_contract_worker_atelier_artifacts_and_scope(tmp_path, engine):
    bus = MessageBus(tmp_path / 'bus', auth=None)
    events = []
    async def collect(message):
        if message.type == MessageType.PROGRESS:
            events.append(message.payload)
    bus.subscribe('*', collect)
    try:
        plan, spec, provider = await prepared(bus, recipe())
        store = CadStore()
        assert not store.root.exists()
        assert spec.metadata['cad']['plan']['criteria'][0]['expected'] == [60, 40, 6]
        assert len(provider.calls) == 1
        worker = CadBrain('cad_brain', bus)
        with pytest.raises(CadError, match='confirmed contract'):
            await worker.handle_task(task(plan, spec))
        assert not store.root.exists()
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        result = await worker.handle_task(task(plan, confirmed))
        assert result['success'], result
        view = result['cad']
        document_id = view['document']['document_id']
        assert view['geometry']['bounds_max_mm'] == pytest.approx([60, 40, 6])
        assert len(view['checks']) == 2 and all(check['status'] == 'passed' for check in view['checks'])
        assert [event['cad']['status'] for event in events] == ['modeling', 'checking', 'ready']
        assert CadStore().view(document_id, 'session-cad') == view

        app = web.Application()
        setup_cad_routes(app, store=store)
        async with TestClient(TestServer(app)) as client:
            headers = {'Origin': str(client.make_url('')).rstrip('/'), 'X-BigBrain-CAD': '1'}
            body = {'documentId': document_id, 'sessionId': 'session-cad', 'revision': 1}
            response = await client.post('/api/cad/view', json=body, headers=headers)
            assert response.status == 200 and (await response.json()) == view
            for kind in ('preview', 'native', 'step', 'stl'):
                response = await client.post('/api/cad/artifact', json={**body, 'kind': kind}, headers=headers)
                assert response.status == 200, await response.text() if response.status != 200 else ''
                data = await response.read()
                assert len(data) > 100
                if kind == 'preview':
                    assert data.startswith(b'\x89PNG\r\n\x1a\n')
            denied = await client.post('/api/cad/artifact', json={**body, 'kind': 'native'})
            assert denied.status == 403
            denied = await client.post('/api/cad/view', json={**body, 'sessionId': 'another'}, headers=headers)
            assert denied.status == 400
            denied = await client.post('/api/cad/artifact', json={**body, 'kind': '../../owner.json'}, headers=headers)
            assert denied.status == 400

        native = store.directory(document_id) / view['document']['native']['path']
        native.write_bytes(b'changed native')
        with pytest.raises(CadError, match='identity changed|bytes changed'):
            store.artifact(document_id, 'session-cad', 1, 'native')
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_real_failed_criterion_preserves_previous_piece(tmp_path, engine):
    bus = MessageBus(tmp_path / 'bus', auth=None)
    try:
        first_plan, spec, _ = await prepared(bus, recipe())
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=first_plan.id)
        worker = CadBrain('cad_brain', bus)
        first = await worker.handle_task(task(first_plan, confirmed))
        assert first['success'], first
        document_id = first['cad']['document']['document_id']
        bad = recipe(80)
        bad['commands'] = [{'command': 'parameters.change', 'params': {'name': 'unused', 'expression': '80 mm'}}]
        edit_plan, spec, _ = await prepared(bus, bad, document_id=document_id, revision=1)
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=edit_plan.id)
        failed = await worker.handle_task(task(edit_plan, confirmed))
        assert failed['success'] is False and failed['delivery_status'] == 'incomplete'
        assert CadStore().view(document_id, 'session-cad')['document']['revision'] == 1
        assert CadStore().view(document_id, 'session-cad')['geometry']['bounds_max_mm'] == pytest.approx([60, 40, 6])
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_real_parameter_edit_and_on_demand_memory(tmp_path, engine):
    from bigbrain.memory.shared import SharedMemory, execute_memory
    bus = MessageBus(tmp_path / 'bus', auth=None)
    try:
        initial, spec, _ = await prepared(bus, recipe())
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=initial.id)
        worker = CadBrain('cad_brain', bus)
        first = await worker.handle_task(task(initial, confirmed))
        document_id = first['cad']['document']['document_id']
        root = CadStore().directory(document_id)
        original = (root / first['cad']['document']['native']['path']).read_bytes()
        edit = recipe(80)
        edit['commands'] = edit['commands'][:1]
        plan, spec, provider = await prepared(bus, edit, document_id=document_id, revision=1)
        assert provider.calls[0]['messages'][-1]['content'].find('geometry') >= 0
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        result = await worker.handle_task(task(plan, confirmed))
        assert result['success'], result
        assert result['cad']['document']['revision'] == 2
        assert result['cad']['geometry']['bounds_max_mm'] == pytest.approx([80, 40, 6])
        assert (root / first['cad']['document']['native']['path']).read_bytes() == original
        shared = SharedMemory(tmp_path / 'bus')
        listing = execute_memory({'tool': 'cad.list', 'arguments': {}}, shared, None, 'session-cad')
        assert listing['documents'][0]['document_id'] == document_id
        assert listing['documents'][0]['revision'] == 2
        assert 'geometry' not in listing['documents'][0]
        view = execute_memory({'tool': 'cad.read', 'arguments': {'id': document_id}}, shared, None, 'session-cad')
        assert view['piece']['geometry']['bounds_max_mm'] == pytest.approx([80, 40, 6])
        assert execute_memory({'tool': 'cad.list', 'arguments': {}}, shared, None, 'another')['documents'] == []
        with pytest.raises(CadError, match='changed'):
            await prepared(bus, edit, document_id=document_id, revision=1)
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_cad_confirmation_reaches_chat_without_another_inference(tmp_path):
    class NoInference:
        async def chat_complete(self, **kwargs):
            raise AssertionError('CAD confirmation already exists')
    bus = MessageBus(tmp_path / 'bus', auth=None)
    frames = []
    async def collect(message):
        frames.append(message.payload)
    bus.subscribe('*', collect)
    try:
        front = FrontBrain(bus, llm_provider=NoInference())
        await front._handle_task_result(BusMessage(type=MessageType.RESULT, source='orchestrator_default',
            target='front_brain', payload={'success': True, 'session_id': 'session-cad', 'results': {
                's1': {'success': True, 'data': {'success': True, 'result_kind': 'cad',
                     'message': 'Pièce vérifiée dans l’Atelier.'}}}}))
        assert any(frame.get('text') == 'Pièce vérifiée dans l’Atelier.' for frame in frames), frames
    finally:
        await bus.close()
