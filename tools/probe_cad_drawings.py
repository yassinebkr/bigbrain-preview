"""Bounded browser probe for an artificial drawing and the native CAD pipeline.

Run with --live after local CAD tests and the UI build. The probe uses at most
three Codex Sol 6.1 low calls within three minutes, with isolated application data.
The report distinguishes completed geometry from clarification and stopped work.
"""

import argparse
import asyncio
import json
import os
import re
from pathlib import Path
import tempfile
import time


async def probe(root):
    # Select only the local executable setting from the developer environment.
    # Personal provider keys and project data stay outside this isolated server.
    from dotenv import dotenv_values
    binary = os.environ.get('BIGBRAIN_CODEX_BINARY') or dotenv_values('.env').get('BIGBRAIN_CODEX_BINARY')
    if binary:
        os.environ['BIGBRAIN_CODEX_BINARY'] = binary
    for key, name in {'EVIDENCE_ROOT': 'evidence', 'SESSIONS_DIR': 'sessions', 'MEMORY_DIR': 'memory',
        'SOUL_FILE': 'soul.json', 'ATTACHMENTS_DIR': 'attachments', 'LOCAL_PROJECTS_DIR': 'local',
        'WORKSPACE_DIR': 'workspace', 'TASKS_FILE': 'tasks.json', 'CAD_DIR': 'cad'}.items():
        os.environ['BIGBRAIN_' + key] = str(root / name)
    os.environ['BIGBRAIN_RECALL'] = '0'
    os.environ['BIGBRAIN_FRONT_MODEL_KEY'] = 'codex-sol-6.1'
    os.environ['BIGBRAIN_PLANNER_MODEL_KEY'] = 'codex-sol-6.1'
    os.environ.pop('BIGBRAIN_WEB_PASSWORD', None)

    from playwright.async_api import async_playwright
    from bigbrain.bus.bus import MessageBus
    from bigbrain.brains.cad_brain import CadBrain
    from bigbrain.front.front_brain import FrontBrain
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator
    from bigbrain.web.server import WebServer
    from bigbrain.llm.codex_provider import CodexProvider, close_codex_app_server
    from bigbrain.llm.usage import get_tracker

    report = {'calls': [], 'events': [], 'outcome': 'incomplete'}
    started = time.monotonic()
    stopped = asyncio.Event()

    class BoundedProvider:
        def __init__(self):
            self.provider = CodexProvider('codex-sol-6.1')

        def __getattr__(self, key):
            return getattr(self.provider, key)

        async def chat_complete(self, **arguments):
            if len(report['calls']) >= 3:
                raise RuntimeError('CAD probe reached its three-call limit')
            call = {'phase': 'front' if arguments.get('tool_schema') else 'cad',
                    'started_seconds': time.monotonic() - started}
            report['calls'].append(call)
            try:
                result = await self.provider.chat_complete(**arguments)
                call['response'] = result
                return result
            finally:
                call['finished_seconds'] = time.monotonic() - started
                (root / 'progress.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    provider = BoundedProvider()
    bus = MessageBus(root / 'logs', auth=None)
    front = FrontBrain(bus, llm_provider=provider)
    orchestrator = WorkspaceOrchestrator('default', bus, llm_provider=provider)
    cad = CadBrain('cad_brain', bus, llm_provider=provider)
    front.register_brain('cad_brain', 'Mechanical CAD from dimensioned drawings')
    orchestrator.register_brain('cad_brain', {'description': 'Mechanical CAD'})
    server = WebServer(bus, host='127.0.0.1', port=0)
    services = []

    async def record(message):
        if message.type == 'event' or message.payload.get('cad'):
            report['events'].append({'type': str(message.type), 'source': message.source,
                                     'payload': message.payload})
            if message.payload.get('event') in {'task.failed', 'task.cancelled'}:
                report['runtime_diagnostic'] = message.payload.get('error') or message.payload.get('reason')
                stopped.set()

    bus.subscribe('*', record)
    try:
        for service in (orchestrator, cad, front, server):
            await service.start()
            services.append(service)
        port = server._site._server.sockets[0].getsockname()[1]
        print(f'CAD_DRAWING_PROBE {root} http://127.0.0.1:{port}', flush=True)
        async with asyncio.timeout(180):
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True, args=['--no-sandbox'])
                try:
                    context = await browser.new_context(viewport={'width': 1600, 'height': 1050})
                    await context.add_init_script("localStorage.setItem('aplot_auth_token', 'isolated-cad-probe');")
                    drawing_page = await context.new_page()
                    await drawing_page.set_content(Path('tests/fixtures/cad/stepped-support.svg').read_text())
                    drawing_path = root / 'stepped-support.png'
                    await drawing_page.locator('svg').screenshot(path=str(drawing_path))
                    await drawing_page.close()
                    page = await context.new_page()
                    report['browser_errors'] = []
                    page.on('pageerror', lambda error: report['browser_errors'].append(str(error)))
                    await page.goto(f'http://127.0.0.1:{port}')
                    await page.locator('input[type=file]').set_input_files(str(drawing_path))
                    await page.get_by_placeholder('Initiate a query or send a command to the AI...').fill(
                        'Crée la pièce du plan joint dans un nouveau document CAD éditable. '
                        'Respecte toutes les cotes et les vues. Vérifie la marche, la position du '
                        'perçage, son diamètre et son caractère traversant. Demande une précision si nécessaire.')
                    await page.get_by_placeholder('Initiate a query or send a command to the AI...').press('Enter')
                    # The browser confirms the proposal only after it is visible.
                    approve = page.get_by_role('button', name=re.compile(r'^(Approve & run|Approuver et lancer)$')).first
                    approval_wait = asyncio.create_task(approve.wait_for(timeout=125000))
                    failure_wait = asyncio.create_task(stopped.wait())
                    try:
                        done, _ = await asyncio.wait({approval_wait, failure_wait}, return_when=asyncio.FIRST_COMPLETED)
                        if failure_wait in done:
                            raise RuntimeError(report.get('runtime_diagnostic') or 'CAD work stopped before confirmation')
                        await approval_wait
                    finally:
                        for waiter in (approval_wait, failure_wait):
                            if not waiter.done():
                                waiter.cancel()
                        await asyncio.gather(approval_wait, failure_wait, return_exceptions=True)
                    await page.screenshot(path=str(root / 'proposal.png'))
                    await approve.click()
                    while not list((root / 'cad').glob('*/current.json')):
                        if stopped.is_set():
                            break
                        await asyncio.sleep(0.25)
                    await page.screenshot(path=str(root / 'result.png'))
                    pointers = list((root / 'cad').glob('*/current.json'))
                    if pointers:
                        from bigbrain.cad_store import CadStore
                        from bigbrain.solidcraft import SolidCraftSession
                        from bigbrain.cad_contracts import CadRevision
                        pointer = pointers[0]
                        owner = json.loads((pointer.parent / 'owner.json').read_text())['session_id']
                        view = CadStore().view(pointer.parent.name, owner)
                        report['cad'] = view
                        # Independent geometric expectations derive from the fixture.
                        assert all(abs(a - b) < 0.01 for a, b in zip(view['geometry']['bounds_max_mm'], (80, 40, 20)))
                        async with SolidCraftSession(pointer.parent) as engine:
                            await engine.reopen(CadRevision.model_validate(view['document']).native)
                            design = await engine.tool('inspect_design', {'sketches': False})
                            topology = await engine.tool('body_topology', {'body': design['bodies'][0]['name']})
                            report['topology'] = topology
                            cylinders = [face['cylinder'] for face in topology['faces'] if face.get('cylinder')]
                            assert any(abs(item['radius'] - 3) < 0.01 and
                                abs(item['origin'][0] - 60) < 0.01 and abs(item['origin'][1] - 20) < 0.01
                                for item in cylinders), 'Expected through-hole cylinder was absent'
                        assert not report['browser_errors'], report['browser_errors']
                        report['outcome'] = 'ready'
                finally:
                    await browser.close()
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    finally:
        for service in reversed(services):
            await service.stop()
        await bus.close()
        await close_codex_app_server()
        report['duration_seconds'] = time.monotonic() - started
        report['usage'] = get_tracker().totals()
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        print(json.dumps({'outcome': report['outcome'], 'calls': len(report['calls']),
                          'error': report.get('error'), 'report': str(root / 'report.json')}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Authorize the bounded subscription probe')
    args = parser.parse_args()
    if not args.live:
        parser.error('--live is required to run subscription calls')
    report = asyncio.run(probe(Path(tempfile.mkdtemp(prefix='bigbrain-cad-drawing-probe-'))))
    raise SystemExit(0 if report['outcome'] == 'ready' else 1)


if __name__ == '__main__':
    main()
