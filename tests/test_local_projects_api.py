"""Exercise chooser authority and project read access through HTTP."""

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import asyncio
import json
import pytest

from bigbrain.local_projects import ProjectRegistry
from bigbrain.web.local_projects_api import setup_local_project_routes


@pytest.mark.asyncio
async def test_native_ticket_grants_and_detachment(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'main.py').write_text('print(42)')
    registry = ProjectRegistry(tmp_path / 'registry.json')

    async def choose():
        return str(root)

    app = web.Application()
    setup_local_project_routes(app, registry=registry, chooser=choose)
    async with TestClient(TestServer(app)) as client:
        origin = str(client.make_url('')).rstrip('/')
        headers = {'Origin': origin, 'X-BigBrain-Local': '1'}
        response = await client.post('/api/local-projects/attach', json={'path': str(root)}, headers=headers)
        assert response.status == 400
        response = await client.post('/api/local-projects/choose', json={}, headers=headers)
        selection = await response.json()
        assert response.status == 200
        response = await client.post('/api/local-projects/attach',
                                     json={'ticket': selection['ticket']}, headers=headers)
        project = await response.json()
        assert response.status == 200
        request = {'projectId': project['id'], 'revision': project['revision']}
        response = await client.post('/api/local-projects/read',
                                     json={**request, 'path': 'main.py'}, headers=headers)
        assert (await response.json())['content'] == 'print(42)'
        response = await client.post('/api/local-projects/attach',
                                     json={'ticket': selection['ticket']}, headers=headers)
        assert response.status == 400
        response = await client.post('/api/local-projects/detach', json=request, headers=headers)
        assert response.status == 200
        response = await client.post('/api/local-projects/read',
                                     json={**request, 'path': 'main.py'}, headers=headers)
        assert response.status == 400
        assert (root / 'main.py').read_text() == 'print(42)'


@pytest.mark.asyncio
async def test_origin_is_server_owned_and_scoped_to_conversation(tmp_path):
    app = web.Application()
    setup_local_project_routes(app, registry=ProjectRegistry(tmp_path / 'state/registry.json'))
    async with TestClient(TestServer(app)) as client:
        headers = {'Origin': str(client.make_url('')).rstrip('/'), 'X-BigBrain-Local': '1'}
        response = await client.post('/api/local-projects/origin', headers=headers,
            json={'sessionId': 'a', 'origin': 'local'})
        assert (await response.json())['selectedOrigin'] == 'local'
        for session, expected in [('a', 'local'), ('b', 'workspace')]:
            response = await client.post('/api/local-projects/projects', headers=headers, json={'sessionId': session})
            assert (await response.json())['selectedOrigin'] == expected
        response = await client.post('/api/local-projects/origin', headers=headers,
            json={'sessionId': 'a', 'origin': 'arbitrary'})
        assert response.status == 400


@pytest.mark.asyncio
async def test_cross_origin_requests_rejected(tmp_path):
    app = web.Application()
    setup_local_project_routes(app, registry=ProjectRegistry(tmp_path / 'registry.json'))
    async with TestClient(TestServer(app)) as client:
        for headers in ({}, {'Origin': 'https://example.com', 'X-BigBrain-Local': '1'}):
            response = await client.get('/api/local-projects', headers=headers)
            assert response.status == 403


@pytest.mark.asyncio
async def test_stream_delivers_output_before_completion(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'main.py').write_text('import time\nprint("first", flush=True)\ntime.sleep(1)\nprint("last")\n')
    registry = ProjectRegistry(tmp_path / 'registry.json')
    project = registry.attach(root, ('read', 'execute'))
    app = web.Application()
    setup_local_project_routes(app, registry=registry)
    async with TestClient(TestServer(app)) as client:
        headers = {'Origin': str(client.make_url('')).rstrip('/'), 'X-BigBrain-Local': '1'}
        response = await client.post('/api/local-projects/run-stream', headers=headers,
                                     json={'projectId': project['id'], 'revision': 1,
                                           'argv': ['python', '-u', 'main.py']})
        first = json.loads(await asyncio.wait_for(response.content.readline(), 0.8))
        assert first['type'] == 'output' and 'first' in first['text']
        events = [json.loads(line) async for line in response.content]
        assert events[-1]['type'] == 'result'
        assert events[-1]['exitCode'] == 0
        assert any('last' in event.get('text', '') for event in events)


@pytest.mark.asyncio
async def test_preview_http_lifecycle_and_authority(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'index.html').write_text('<main>Preview fixture</main>')
    registry = ProjectRegistry(tmp_path / 'state/registry.json')
    project = registry.attach(root, ('read', 'execute'))
    app = web.Application()
    setup_local_project_routes(app, registry=registry)
    async with TestClient(TestServer(app)) as client:
        headers = {'Origin': str(client.make_url('')).rstrip('/'), 'X-BigBrain-Local': '1'}
        scope = {'projectId': project['id'], 'revision': 1}
        response = await client.post('/api/local-projects/preview-open', headers=headers,
            json={**scope, 'entryPoint': 'index.html'})
        assert response.status == 200, await response.text()
        lease = await response.json()
        request = {**scope, 'previewId': lease['previewId']}
        assert (await client.post('/api/local-projects/preview-frame', json=request)).status == 403
        response = await client.post('/api/local-projects/preview-frame', headers=headers, json=request)
        assert response.status == 200
        assert (await response.json())['image'].startswith('iVBOR')
        response = await client.post('/api/local-projects/preview-close', headers=headers, json=request)
        assert (await response.json())['closed']
        response = await client.post('/api/local-projects/preview-frame', headers=headers, json=request)
        assert response.status == 400
