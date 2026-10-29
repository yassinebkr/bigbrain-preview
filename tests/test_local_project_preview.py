"""Leased browser previews preserve isolation, interaction and resource cleanup."""

import base64
import json
import pytest

from bigbrain.local_projects import ProjectRegistry, ProjectAccessError
from bigbrain.local_project_preview import ProjectPreviews


@pytest.mark.asyncio
async def test_live_preview_click_storage_and_revocation(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'index.html').write_text('<main><button style="width:200px;height:80px" onclick="'
        'localStorage.setItem(\'count\',\'1\');document.querySelector(\'p\').textContent=\'1\'">Add</button>'
        '<p>0</p><script>fetch("https://example.invalid/blocked").catch(()=>{window.fetchBlocked=true});</script></main>')
    registry = ProjectRegistry(tmp_path / 'state/registry.json')
    project = registry.attach(root, ('read', 'execute'))
    previews = ProjectPreviews(registry)
    try:
        lease = await previews.open(project['id'], 1, 'index.html')
        identifier = lease['previewId']
        frame = await previews.frame(identifier, project['id'], 1, {'type': 'click', 'x': 50, 'y': 30})
        assert base64.b64decode(frame['image']).startswith(b'\x89PNG')
        page = previews.sessions[identifier].page
        await page.wait_for_function('window.fetchBlocked === true')
        assert await page.locator('p').text_content() == '1'
        assert await page.evaluate('localStorage.getItem("count")') == '1'
        with pytest.raises(ProjectAccessError):
            await previews.frame(identifier, project['id'], 1, {'type': 'key', 'key': 'Control+O'})
        registry.change(project['id'], 1, state='revoked')
        with pytest.raises(ProjectAccessError):
            await previews.frame(identifier, project['id'], 1)
    finally:
        await previews.cleanup()
    assert not previews.sessions


@pytest.mark.asyncio
@pytest.mark.parametrize('transport', ['websocket', 'fetch'])
async def test_blob_worker_cannot_connect_to_another_loopback_service(tmp_path, transport):
    from aiohttp import web
    from aiohttp.test_utils import TestServer

    connections = []
    async def websocket(request):
        connections.append(request.path)
        if request.path == '/http':
            return web.Response(text='unexpected external connection')
        response = web.WebSocketResponse()
        await response.prepare(request)
        await response.close()
        return response

    app = web.Application()
    app.router.add_get('/ws', websocket)
    app.router.add_get('/http', websocket)
    async with TestServer(app) as target:
        root = tmp_path / 'source'
        root.mkdir()
        if transport == 'websocket':
            script = ('try {const ws = new WebSocket(' +
                json.dumps(str(target.make_url('/ws')).replace('http:', 'ws:')) +
                ');ws.onopen=()=>postMessage("opened");ws.onerror=()=>postMessage("blocked");}'
                'catch(e){postMessage("blocked");}')
        else:
            script = ('fetch(' + json.dumps(str(target.make_url('/http'))) +
                ').then(()=>postMessage("opened"),()=>postMessage("blocked"));')
        (root / 'index.html').write_text('<main>Worker isolation</main><script>'
            'const worker = new Worker(URL.createObjectURL(new Blob([' + json.dumps(script) + '],'
            '{type:"text/javascript"})));worker.onmessage=e=>{window.attackResult=e.data};</script>')
        registry = ProjectRegistry(tmp_path / 'state/registry.json')
        project = registry.attach(root, ('read', 'execute'))
        previews = ProjectPreviews(registry)
        try:
            lease = await previews.open(project['id'], 1, 'index.html')
            await previews.frame(lease['previewId'], project['id'], 1)
            page = previews.sessions[lease['previewId']].page
            await page.wait_for_function('window.attackResult !== undefined', timeout=5000)
            assert await page.evaluate('window.attackResult') == 'blocked'
            assert connections == []
        finally:
            await previews.cleanup()
