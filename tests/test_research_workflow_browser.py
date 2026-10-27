"""Chromium replay of real workflow events through production Atelier components."""
import asyncio
from pathlib import Path
import subprocess
from unittest.mock import AsyncMock

import httpx
import pytest

from bigbrain.research import Limits, ModelPolicy, ResearchRuntime
from tests.test_research_runtime import page
from tests.test_research_workflow import FACT, StageInference


@pytest.mark.asyncio
async def test_staged_atelier_tracks_control_reload_and_conversation_isolation(tmp_path):
    api = pytest.importorskip('playwright.async_api')
    root = Path(__file__).resolve().parents[1]
    if not (root / 'web-ui/node_modules/.bin/vite').is_file():
        pytest.skip('Production UI dependencies are required for the Chromium Atelier journey')
    reader = AsyncMock()
    reader.read.return_value = page(FACT)
    frames = [{'type': 'task.received', 'detail': {'task_id': 'audit-run', 'session_id': 'audit-chat',
                                                 'description': 'Documentary workflow audit'}}]
    async def progress(event):
        frames.append({'type': 'task.progress', 'detail': {
            'task_id': 'audit-run', 'session_id': 'audit-chat', 'subtask_id': 'research-step', **event}})
    runtime = ResearchRuntime(AsyncMock(), reader, ModelPolicy(StageInference()), progress,
                              staged=True, limits=Limits(seconds=120))
    result = await runtime.run('Establish the API behavior and its input restriction')
    assert result.execution_outcome == 'complete', result.reason
    frames.append({'type': 'task.complete', 'detail': {'task_id': 'audit-run', 'session_id': 'audit-chat'}})
    control = next(i for i, f in enumerate(frames) if f['detail'].get('phase') == 'control')
    fixture = root / 'tests/fixtures/research_atelier_browser'
    with (tmp_path / 'vite.log').open('w') as log:
        server = subprocess.Popen([str(root / 'web-ui/node_modules/.bin/vite'), '--configLoader', 'native',
                                   '--config', str(fixture / 'vite.config.mjs')],
                                  cwd=root / 'web-ui', stdout=log, stderr=subprocess.STDOUT)
        try:
            async with httpx.AsyncClient() as client:
                for _ in range(100):
                    if server.poll() is not None:
                        pytest.fail((tmp_path / 'vite.log').read_text())
                    try:
                        if (await client.get('http://127.0.0.1:43281/')).status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    await asyncio.sleep(.05)
                else:
                    pytest.fail('Offline Atelier fixture did not start')
            errors = []
            async with api.async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                tab = await browser.new_page(viewport={'width': 1600, 'height': 1000}, reduced_motion='reduce')
                tab.on('pageerror', lambda error: errors.append(str(error)))
                await tab.goto('http://127.0.0.1:43281/')
                await tab.wait_for_function('!!window.audit')
                await tab.evaluate('(frames) => window.audit.replay(frames)', frames[:control + 1])
                await api.expect(tab.get_by_text('Vérification des conclusions et des réserves', exact=True)).to_be_visible()
                await tab.evaluate('window.audit.switchTo("other-chat")')
                await api.expect(tab.get_by_label('Surface contextuelle')).to_have_count(0)
                await tab.evaluate('(frames) => window.audit.replay(frames, false)', frames[control + 1:])
                assert (await tab.evaluate('window.audit.state()'))['session'] == 'other-chat'
                await tab.reload()
                await tab.wait_for_function('!!window.audit')
                await tab.evaluate('(frames) => window.audit.replay(frames)', frames)
                await api.expect(tab.get_by_text('Recherche terminée', exact=True)).to_be_visible()
                await api.expect(tab.locator('.animate-spin')).to_have_count(0)
                before = await tab.evaluate('window.audit.state()')
                await tab.evaluate('(frames) => window.audit.replay(frames, false)', frames)
                assert await tab.evaluate('window.audit.state()') == before
                await tab.screenshot(path=str(tmp_path / 'atelier-reloaded.png'))
                assert not errors, errors
                await browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
