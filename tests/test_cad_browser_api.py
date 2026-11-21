"""HTTP scope and immutable checkpoint ticket qualification."""

from base64 import b64encode

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from bigbrain.cad_browser import BrowserCadBridge, digest
from bigbrain.cad_contracts import CadArtifact, CadRevision, GeometryObservation
from bigbrain.cad_store import CadStore
from bigbrain.solidcraft import CadCapture
from bigbrain.web.cad_browser_api import setup_browser_cad_routes


@pytest.mark.asyncio
async def test_scope_tickets_and_results(tmp_path):
    store = CadStore(tmp_path)
    document = store.create('session-a')
    bridge = BrowserCadBridge(store.authorize(document, 'session-a') / 'browser')
    bridge.initialize(b'native checkpoint')
    app = web.Application()
    setup_browser_cad_routes(app, store=store)
    async with TestClient(TestServer(app)) as client:
        headers = {'Origin': str(client.make_url('')).rstrip('/'), 'X-BigBrain-CAD': '1'}
        scope = {'documentId': document, 'sessionId': 'session-a'}
        async def call(action, data=None, **kwargs):
            return await client.post('/api/cad/browser/' + action,
                                     json={**scope, **(data or {})}, headers=headers, **kwargs)
        assert (await client.post('/api/cad/browser/state', json=scope)).status == 403
        assert (await call('state', {'sessionId': 'session-b'})).status == 400
        assert (await call('load', {'hash': 'stale'})).status == 409
        response = await call('load', {'hash': digest(b'native checkpoint')})
        ticket = (await response.json())['value']
        checkpoint = await client.get(ticket)
        assert await checkpoint.read() == b'native checkpoint'
        assert checkpoint.headers['Cache-Control'] == 'no-store'
        assert (await client.get(ticket)).status == 404
        response = await call('connect', {'capabilities': {'build': 'test-0.28.0'}})
        generation = (await response.json())['value']['generation']
        assert (await call('resume', {'revision': 0, 'hash': digest(b'native checkpoint')})).status == 200
        request = {'operationId': 'build-1', 'revision': 0, 'hash': digest(b'native checkpoint'),
                   'command': 'parameters.change', 'params': {'name': 'width', 'expression': '61 mm'}}
        assert (await call('enqueue', request)).status == 200
        assert (await call('claim', {'generation': 'replaced'})).status == 409
        assert (await call('claim', {'generation': generation})).status == 200
        assert (await call('accept', {'generation': generation, 'operationId': 'build-1',
                                      'native': 'bmV3', 'result': {'width': 61}})).status == 200
        result = (await (await call('result', {'operationId': 'build-1'})).json())['value']
        assert result['revision'] == 1
        assert result['observation']['result']['width'] == 61
        assert (await call('save', {'generation': generation, 'revision': 1,
                                   'hash': digest(b'new'), 'native': 'bWFudWFs'})).status == 409


@pytest.mark.asyncio
async def test_reopen_saved_copy_after_new_publication(tmp_path):
    store = CadStore(tmp_path)
    session = 'session-a'
    document = store.create(session)

    def publish(revision, native):
        path = store.directory(document) / f'revision-{revision}' / 'part.sc'
        path.parent.mkdir()
        path.write_bytes(native)
        artifact = CadArtifact(path=f'revision-{revision}/part.sc', format='solidcraft',
                               sha256=digest(native), size_bytes=len(native))
        capture = CadCapture(
            CadRevision(project_id=document, document_id=document, revision=revision,
                        engine_version='0.28.0', native=artifact, exports=()),
            GeometryObservation(source_sha256=artifact.sha256, evidence_ref='geometry',
                                body_count=1, closed_solid=True, bounds_min_mm=(0, 0, 0),
                                bounds_max_mm=(1, 1, 1), volume_mm3=1),
            None, None,
        )
        store.publish(session, capture, base_revision=revision - 1)

    def new_app():
        app = web.Application()
        setup_browser_cad_routes(app, store=CadStore(tmp_path))
        return app

    async def call(client, action, **data):
        headers = {'Origin': str(client.make_url('')).rstrip('/'), 'X-BigBrain-CAD': '1'}
        response = await client.post('/api/cad/browser/' + action, headers=headers,
                                     json={'documentId': document, 'sessionId': session, **data})
        assert response.status == 200, await response.text()
        return (await response.json())['value']

    publish(1, b'first publication')
    saved = b'edited working copy'
    async with TestClient(TestServer(new_app())) as client:
        initialized = await call(client, 'initialize', revision=1)
        assert initialized['base_revision'] == 1
        state = await call(client, 'connect', capabilities={'build': '0.28.0-test'})
        await call(client, 'save', generation=state['generation'], revision=state['revision'],
                   hash=state['hash'], native=b64encode(saved).decode('ascii'))

    publish(2, b'second publication')
    async with TestClient(TestServer(new_app())) as client:
        restored = await call(client, 'initialize', revision=2)
        assert restored['base_revision'] == 1
        assert restored['base_conflict'] is True
        state = await call(client, 'connect', capabilities={'build': '0.28.0-test'})
        assert state['revision'] == 1
        assert state['hash'] == digest(saved)
        ticket = await call(client, 'load', hash=state['hash'])
        response = await client.get(ticket)
        assert await response.read() == saved
        assert store.artifact(document, session, 2, 'native')[1] == b'second publication'
