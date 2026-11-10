"""HTTP scope and immutable checkpoint ticket qualification."""

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from bigbrain.cad_browser import BrowserCadBridge, digest
from bigbrain.cad_store import CadStore
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
