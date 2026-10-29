"""Exercise chooser authority and project read access through HTTP."""

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
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
async def test_cross_origin_requests_rejected(tmp_path):
    app = web.Application()
    setup_local_project_routes(app, registry=ProjectRegistry(tmp_path / 'registry.json'))
    async with TestClient(TestServer(app)) as client:
        for headers in ({}, {'Origin': 'https://example.com', 'X-BigBrain-Local': '1'}):
            response = await client.get('/api/local-projects', headers=headers)
            assert response.status == 403
