import json
import time

import aiohttp
import pytest

from bigbrain.web.preview_leases import PreviewLeases


@pytest.mark.asyncio
async def test_shared_preview_releases_last_viewer_and_blocks_private_files(tmp_path):
    (tmp_path / 'index.html').write_text('<h1>Real preview</h1>')
    (tmp_path / '.project.json').write_text('private')
    manager = PreviewLeases()
    first = await manager.acquire(tmp_path)
    second = await manager.acquire(tmp_path)
    assert first['previewUrl'] == second['previewUrl']
    async with aiohttp.ClientSession() as client:
        async with client.get(first['previewUrl']) as response:
            assert await response.text() == '<h1>Real preview</h1>'
        async with client.get(first['previewUrl'] + '/.project.json') as response:
            assert response.status == 404
    await manager.release(first['leaseId'])
    assert len(manager.servers) == 1
    await manager.release(second['leaseId'])
    assert not manager.servers
    async with aiohttp.ClientSession() as client:
        with pytest.raises(aiohttp.ClientConnectionError):
            await client.get(first['previewUrl'])


@pytest.mark.asyncio
async def test_abandoned_lease_expires_and_shutdown_closes_servers(tmp_path):
    manager = PreviewLeases()
    lease = await manager.acquire(tmp_path)
    key, _ = manager.leases[lease['leaseId']]
    manager.leases[lease['leaseId']] = (key, time.monotonic() - 46)
    async with manager.lock:
        await manager._prune()
    assert not manager.servers
    await manager.acquire(tmp_path)
    lifecycle = manager.lifecycle(None)
    await anext(lifecycle)
    await lifecycle.aclose()
    assert not manager.servers
    assert not manager.leases


@pytest.mark.asyncio
async def test_api_validates_project_and_reopens_after_server_restart(tmp_path, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer
    from aiohttp import web
    from bigbrain.web.fs_api import setup_fs_routes
    monkeypatch.setenv('BIGBRAIN_WORKSPACE_DIR', str(tmp_path))
    project = tmp_path / 'demo'
    project.mkdir()
    (project / 'index.html').write_text('Preview')
    manifest = project / '.project.json'
    manifest.write_text(json.dumps({'deliverable_type': 'web_app', 'entry_point': 'index.html', 'verified': True}))
    previous_url = None
    for _ in range(2):
        app = web.Application()
        setup_fs_routes(app)
        async with TestClient(TestServer(app)) as client:
            response = await client.post('/api/fs/preview', json={'path': 'demo/index.html'})
            assert response.status == 200
            lease = await response.json()
            if previous_url:
                assert lease['previewUrl'] == previous_url
            previous_url = lease['previewUrl']
            async with aiohttp.ClientSession() as browser:
                async with browser.get(lease['previewUrl']) as page:
                    assert await page.text() == 'Preview'
            response = await client.post('/api/fs/preview', json={'leaseId': lease['leaseId']})
            assert response.status == 200
        async with aiohttp.ClientSession() as browser:
            with pytest.raises(aiohttp.ClientConnectionError):
                await browser.get(lease['previewUrl'])
    manifest.unlink()
    app = web.Application()
    setup_fs_routes(app)
    async with TestClient(TestServer(app)) as client:
        response = await client.post('/api/fs/preview', json={'path': 'demo/index.html'})
        assert response.status == 400


@pytest.mark.asyncio
async def test_distinct_project_origins_and_corrupt_registry_are_safe(tmp_path):
    from aiohttp import web
    registry = tmp_path / '.preview-ports.json'
    first = tmp_path / 'one'
    second = tmp_path / 'two'
    first.mkdir()
    second.mkdir()
    manager = PreviewLeases(registry)
    one = await manager.acquire(first)
    await manager.release(one['leaseId'])
    two = await manager.acquire(second)
    assert one['previewUrl'] != two['previewUrl']
    await manager.release(two['leaseId'])
    reopened = await manager.acquire(first)
    assert reopened['previewUrl'] == one['previewUrl']
    await manager.release(reopened['leaseId'])
    registry.write_text('invalid')
    with pytest.raises(web.HTTPConflict):
        await manager.acquire(first)
    assert not manager.servers
