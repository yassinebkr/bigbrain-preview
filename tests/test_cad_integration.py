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


async def prepared(bus, plan_data, *, document_id=None, revision=None, drawing=None):
    provider = Provider(plan_data)
    orchestrator = WorkspaceOrchestrator('default', bus, llm_provider=provider)
    orchestrator.register_brain('cad_brain', {'description': 'CAD'})
    payload = {'brain': 'cad_brain', 'type': 'model_cad', 'session_id': 'session-cad',
               'user_request': 'Plaque mécanique ' + str(plan_data['criteria'][0]['expected'])}
    if document_id:
        payload.update(document_id=document_id, base_revision=revision)
    if drawing is not None:
        payload['drawing'] = drawing
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


@pytest.mark.asyncio
@pytest.mark.parametrize('repair_succeeds', [True, False])
async def test_bounded_repair_preserves_confirmed_targets(tmp_path, engine, repair_succeeds):
    initial = recipe()
    initial['commands'][1]['params']['height'] = 5
    repair = recipe()
    if not repair_succeeds:
        repair['commands'][1]['params']['height'] = 4
    provider = Provider({'commands': repair['commands']})
    bus = MessageBus(tmp_path / 'bus', auth=None)
    try:
        plan, spec, _ = await prepared(bus, initial)
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        worker = CadBrain('cad_brain', bus, llm_provider=provider)
        result = await worker.handle_task(task(plan, confirmed))
        assert result['success'] is repair_succeeds, result
        assert len(provider.calls) == (1 if repair_succeeds else 2)
        contract = json.loads(provider.calls[0]['messages'][1]['content'])['confirmed_plan']
        assert contract['criteria'][0]['expected'] == [60, 40, 6]
        assert contract['max_repairs'] == 2
        if repair_succeeds:
            assert result['cad']['document']['revision'] == 2
            assert all(item['status'] == 'passed' for item in result['cad']['checks'])
        else:
            assert result['delivery_status'] == 'incomplete'
            assert not list(CadStore().root.glob('*/current.json'))
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_dimensioned_stepped_support_runs_through_contract_and_local_checks(tmp_path, engine):
    from pathlib import Path
    import hashlib
    source = {'attachment_id': 'att-012345abcdef',
              'sha256': hashlib.sha256(Path('tests/fixtures/cad/stepped-support.svg').read_bytes()).hexdigest()}
    dimensions = [('width', 80, 'length'), ('depth', 40, 'length'), ('height', 20, 'length'),
                  ('step', 20, 'length'), ('base', 8, 'depth'), ('diameter', 6, 'diameter'),
                  ('hole_x', 60, 'position'), ('hole_y', 20, 'position')]
    drawing = {'title': 'Stepped support', 'sources': [source], 'views': ['top', 'front'],
        'dimensions': [{'id': identity, 'feature_id': identity, 'label': identity,
            'kind': kind, 'value': value, 'unit': 'mm', 'origin': 'explicit',
            'sources': [source], 'annotation': str(value)} for identity, value, kind in dimensions]}
    def section(identity, axis, point, intervals, bindings=()):
        return {'id': identity, 'label': identity, 'axis': axis, 'point_mm': point,
                'intervals_mm': intervals, 'bindings': [
                    {'dimension_id': dimension, 'quantity': quantity, 'interval': index}
                    for dimension, quantity, index in bindings]}
    data = {'title': 'Stepped support', 'commands': [
        {'command': 'solid.box', 'params': {'length': 80, 'width': 40, 'height': 8, 'body_name': 'support'}},
        {'command': 'solid.box', 'params': {'length': 20, 'width': 40, 'height': 12,
            'corner': [0, 0, 8], 'operation': 'join', 'targets': ['support']}},
        {'command': 'solid.cylinder', 'params': {'radius': 3, 'height': 8,
            'base': [60, 20, 0], 'operation': 'cut', 'targets': ['support']}}],
        'criteria': [{'id': 'envelope', 'label': 'Envelope', 'metric': 'dimensions_mm',
            'expected': [80, 40, 20], 'dimension_bindings': {'width': 0, 'depth': 1, 'height': 2}}],
        'sections': [section('step_length', 0, [0, 10, 12], [[0, 20]], [('step', 'length', 0)]),
            section('base_thickness', 2, [30, 10, 0], [[0, 8]], [('base', 'length', 0)]),
            section('hole_x', 0, [0, 20, 4], [[0, 57], [63, 80]], [('hole_x', 'gap_center', 0), ('diameter', 'gap', 0)]),
            section('hole_y', 1, [60, 0, 4], [[0, 17], [23, 40]], [('hole_y', 'gap_center', 0)]),
            section('through', 2, [60, 20, 0], [])]}
    bus = MessageBus(tmp_path / 'bus', auth=None)
    try:
        plan, spec, _ = await prepared(bus, data, drawing=drawing)
        assert spec.metadata['cad']['plan']['drawing']['sources'] == [dict(source, schema_version='1.0', region=[0, 0, 1, 1])]
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        result = await CadBrain('cad_brain', bus).handle_task(task(plan, confirmed))
        assert result['success'], result
        assert len(result['cad']['checks']) == 6
        assert all(item['status'] == 'passed' for item in result['cad']['checks'])
        root = CadStore().directory(result['cad']['document']['document_id'])
        sections = json.loads((root / 'revision-1/sections.json').read_text())
        assert len(sections) == 5 and all(len(item['surface_sha256']) == 64 for item in sections)
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_native_command_rejection_enters_the_same_bounded_repair_loop(tmp_path, engine):
    initial = recipe()
    initial['commands'][0]['params']['expression'] = 'missing_parameter + 1'
    provider = Provider({'commands': recipe()['commands']})
    bus = MessageBus(tmp_path / 'bus', auth=None)
    try:
        plan, spec, _ = await prepared(bus, initial)
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        result = await CadBrain('cad_brain', bus, llm_provider=provider).handle_task(task(plan, confirmed))
        assert result['success'], result
        assert len(provider.calls) == 1
        diagnosis = json.loads(provider.calls[0]['messages'][1]['content'])['command_diagnostic']
        assert diagnosis['command'] == 'parameters.change' and diagnosis['index'] == 0
        root = CadStore().directory(result['cad']['document']['document_id'])
        assert len(list(root.glob('command-failure-*.json'))) == 1
        assert all(item['status'] == 'passed' for item in result['cad']['checks'])
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_transport_uncertainty_stops_before_repair(tmp_path, engine, monkeypatch):
    from bigbrain.solidcraft import SolidCraftSession
    provider = Provider({'commands': recipe()['commands']})
    bus = MessageBus(tmp_path / 'bus', auth=None)
    try:
        plan, spec, _ = await prepared(bus, recipe())
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        async def uncertain(*args, **kwargs):
            raise CadError('CAD response identity mismatch')
        monkeypatch.setattr(SolidCraftSession, 'batch', uncertain)
        result = await CadBrain('cad_brain', bus, llm_provider=provider).handle_task(task(plan, confirmed))
        assert not result['success'] and result['delivery_status'] == 'incomplete'
        assert provider.calls == []
        assert not list(CadStore().root.glob('*/current.json'))
    finally:
        await bus.close()
