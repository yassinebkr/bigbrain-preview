"""Durable presentation identities survive process reconstruction and reject foreign readers."""

import json

import pytest

from bigbrain.cad_live import retain_progress, retained_activities, working_checkpoint
from bigbrain.cad_store import CadStore
from bigbrain.solidcraft import CadError


def test_progress_survives_store_recreation_and_keeps_run_scope(tmp_path):
    store = CadStore(tmp_path)
    document = store.create('conversation')
    progress = {'stage': 'cad_group_checkpoint', 'cad': {'sequence': 2, 'working': None}}
    context = {'session_id': 'conversation', 'task_id': 'run', 'subtask_id': 'construction'}
    retain_progress(store, document, 'conversation', context, progress)
    reopened = CadStore(tmp_path)
    root = reopened.authorize(document, 'conversation')
    recorded = json.loads((root / 'working-state.json').read_text())
    assert recorded['context'] == context
    assert recorded['progress'] == progress
    assert recorded['document_id'] == document
    assert working_checkpoint(reopened, document, 'conversation') is None
    assert len(retained_activities(reopened, 'conversation')) == 1
    assert retained_activities(reopened, 'foreign') == []
    resumed = {'stage': 'cad_group_checkpoint', 'cad': {'sequence': 1, 'working': None}}
    retain_progress(reopened, document, 'conversation', context, resumed)
    assert retained_activities(reopened, 'conversation')[0]['progress']['cad']['sequence'] == 3
    with pytest.raises(CadError, match='another conversation'):
        working_checkpoint(reopened, document, 'foreign')
    with pytest.raises(CadError, match='another conversation'):
        retain_progress(reopened, document, 'foreign', context, progress)


def test_latency_milestones_survive_progress_and_store_restart(tmp_path, monkeypatch):
    store = CadStore(tmp_path)
    document = store.create('conversation')
    context = {'session_id': 'conversation', 'task_id': 'run'}
    clock = iter([100.0, 104.0, 120.0])
    monkeypatch.setattr('bigbrain.cad_live.time.time', lambda: next(clock))
    for sequence, (status, working) in enumerate([
        ('modeling', {'design': {'bodies': []}}),
        ('modeling', {'design': {'bodies': [{'name': 'Plate'}]}}),
        ('ready', None),
    ], start=1):
        retain_progress(CadStore(tmp_path), document, 'conversation', context,
            {'cad': {'sequence': sequence, 'status': status, 'working': working}})
    record = json.loads((store.directory(document) / 'working-state.json').read_text())
    assert record['milestones'] == {
        'first_progress_at': 100.0,
        'first_solid_checkpoint_at': 104.0,
        'first_verified_delivery_at': 120.0,
    }


def test_checkpoint_head_symlink_is_rejected(tmp_path):
    store = CadStore(tmp_path / 'cad')
    document = store.create('conversation')
    root = store.authorize(document, 'conversation')
    (root / 'execution-checkpoints').mkdir()
    target = tmp_path / 'foreign.json'
    target.write_text('{}')
    (root / 'execution-checkpoints/head.json').symlink_to(target)
    with pytest.raises(CadError, match='identity changed'):
        working_checkpoint(store, document, 'conversation')


def test_retained_activity_reopens_cad_after_journal_rotation(tmp_path):
    from bigbrain.web.run_history import conversation_activity

    store = CadStore(tmp_path / 'cad')
    document = store.create('conversation')
    context = {'session_id': 'conversation', 'task_id': 'run', 'subtask_id': 'construction'}
    progress = {'stage': 'cad_group_checkpoint', 'cad': {
        'title': 'Plate', 'sequence': 1, 'working': None, 'status': 'modeling'}}
    retain_progress(store, document, 'conversation', context, progress)
    logs = tmp_path / 'logs'
    logs.mkdir()
    frames = conversation_activity(logs, 'conversation', float('inf'), cad_store=CadStore(store.root))
    assert [frame['payload']['event'] for frame in frames] == [
        'task.received', 'task.progress', 'task.failed']
    assert frames[1]['payload']['cad']['title'] == 'Plate'
    assert frames[1]['payload']['brain'] == 'cad_brain'
    assert 'redémarrage' in frames[2]['payload']['error']
    assert conversation_activity(logs, 'foreign', float('inf'), cad_store=store) == []


@pytest.mark.asyncio
async def test_native_working_artifact_is_bound_to_the_accepted_head(tmp_path, cad_native_engine):
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    from bigbrain.cad_execution import CadExecutionStore
    from bigbrain.solidcraft import SolidCraftSession
    from bigbrain.web.cad_api import setup_cad_routes
    from tests.test_cad_execution import group, accept

    store = CadStore(tmp_path / 'cad')
    document = store.create('conversation')
    root = store.authorize(document, 'conversation')
    execution = CadExecutionStore(root, 'a' * 64)
    async with SolidCraftSession(root) as session:
        record = await execution.execute(session, group(), validate=accept)
    working = working_checkpoint(CadStore(store.root), document, 'conversation')
    assert working['checkpoint_id'] == record.id
    assert working['native']['sha256'] == record.native.sha256
    assert working['mesh']['source_sha256'] == record.native.sha256
    assert working['design']['bodies'][0]['name'] == 'Base'
    app = web.Application()
    setup_cad_routes(app, store=store)
    async with TestClient(TestServer(app)) as client:
        headers = {'Origin':str(client.make_url('')).rstrip('/'), 'X-BigBrain-CAD':'1'}
        body = {'documentId':document, 'sessionId':'conversation', 'checkpointId':record.id}
        response = await client.post('/api/cad/working-artifact', json=body, headers=headers)
        assert response.status == 200
        assert await response.read() == (root / record.native.path).read_bytes()
        mesh = await client.post('/api/cad/working-artifact', json={**body, 'kind': 'stl'}, headers=headers)
        assert mesh.status == 200
        assert mesh.headers['X-BigBrain-CAD-SHA256'] == record.mesh.sha256
        assert await mesh.read() == (root / record.mesh.path).read_bytes()
        for changed in ({'checkpointId': 'f' * 32}, {'sessionId': 'foreign'}, {'kind': 'unsupported'}):
            rejected = await client.post('/api/cad/working-artifact', json={**body, 'kind': 'stl', **changed}, headers=headers)
            assert rejected.status == 400
        (root / record.mesh.path).write_bytes(b'changed mesh')
        rejected = await client.post('/api/cad/working-artifact', json={**body, 'kind': 'stl'}, headers=headers)
        assert rejected.status == 400

        for changed in ({'checkpointId':'f' * 32}, {'sessionId':'foreign'}):
            response = await client.post('/api/cad/working-artifact', json={**body, **changed}, headers=headers)
            assert response.status == 400
        (root / record.native.path).write_bytes(b'replaced')
        response = await client.post('/api/cad/working-artifact', json=body, headers=headers)
        assert response.status == 400


@pytest.mark.asyncio
async def test_memory_discovers_unpublished_checkpoint_after_store_recreation(tmp_path, monkeypatch):
    """A retained construction remains discoverable through conversation memory."""
    from bigbrain.cad_execution import CadExecutionStore
    from bigbrain.memory.shared import execute_memory
    from bigbrain.web.sessions import SessionStore
    from tests.test_cad_execution import Session, accept, group

    monkeypatch.setenv('BIGBRAIN_CAD_DIR', str(tmp_path / 'cad'))
    monkeypatch.setenv('BIGBRAIN_SESSIONS_DIR', str(tmp_path / 'sessions'))
    sessions = SessionStore()
    conversation = sessions.create()['id']
    store = CadStore()
    document = store.create(conversation)
    root = store.authorize(document, conversation)
    execution = CadExecutionStore(root, 'a' * 64)
    record = await execution.execute(Session(root), group(), validate=accept)
    listing = execute_memory({'tool': 'cad.list', 'arguments': {}}, None, None, conversation)
    assert listing['status'] == 'ok'
    item, = listing['documents']
    assert item['document_id'] == document and item['revision'] == 0
    assert item['delivery_status'] == 'incomplete'
    assert item['working']['checkpoint_id'] == record.id
    assert item['working']['accepted_steps'] == 1
    view = execute_memory({'tool': 'cad.read', 'arguments': {'id': document}}, None, None, conversation)
    assert view['piece']['working'] == item['working']
    assert view['piece']['checks'] == []
    assert CadStore().list('foreign')['documents'] == []
    with pytest.raises(CadError, match='another conversation'):
        CadStore().memory_view(document, 'foreign')
    # A modified native artifact invalidates the pointer before the next turn.
    (root / record.native.path).write_bytes(b'changed')
    assert CadStore().list(conversation)['documents'] == []
