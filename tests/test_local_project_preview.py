"""Leased browser previews preserve isolation, interaction and resource cleanup."""

import base64
import pytest

from bigbrain.local_projects import ProjectRegistry, ProjectAccessError
from bigbrain.local_project_preview import ProjectPreviews


@pytest.mark.asyncio
async def test_live_preview_click_storage_and_revocation(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'index.html').write_text('<main><button style="width:200px;height:80px" onclick="'
        'localStorage.setItem(\'count\',\'1\');document.querySelector(\'p\').textContent=\'1\'">Add</button>'
        '<p>0</p><script>fetch("https://example.invalid/blocked").catch(()=>{});</script></main>')
    registry = ProjectRegistry(tmp_path / 'state/registry.json')
    project = registry.attach(root, ('read', 'execute'))
    previews = ProjectPreviews(registry)
    try:
        lease = await previews.open(project['id'], 1, 'index.html')
        identifier = lease['previewId']
        frame = await previews.frame(identifier, project['id'], 1, {'type': 'click', 'x': 50, 'y': 30})
        assert base64.b64decode(frame['image']).startswith(b'\x89PNG')
        assert frame['blockedRequests'] >= 1
        page = previews.sessions[identifier].page
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
