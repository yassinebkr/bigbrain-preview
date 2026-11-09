"""Isolated CAD server for a bounded manual browser qualification campaign.

Run from the repository with PYTHONPATH=. and the project interpreter. The
server uses artificial attachments selected through the UI. It preserves its
temporary session and call reports for subsequent inspection.
"""

import asyncio
import json
import os
from pathlib import Path
import tempfile
import time


async def main():
    maximum_calls = int(os.environ.get('CAD_PROBE_MAX_CALLS', '10'))
    if not 1 <= maximum_calls <= 128:
        raise ValueError('Qualification campaign supports at most 128 explicitly authorized cumulative calls')
    baseline_calls = int(os.environ.get('CAD_PROBE_BASE_CALLS', '0'))
    inspection_reserve = int(os.environ.get('CAD_PROBE_INSPECTION_RESERVE', '0'))
    if not 0 <= baseline_calls < maximum_calls or not 0 <= inspection_reserve < maximum_calls - baseline_calls:
        raise ValueError('Campaign reserve and baseline must fit its call envelope')
    maximum_seconds = float(os.environ.get('CAD_PROBE_MAX_INFERENCE_SECONDS', '600'))
    if not 0 < maximum_seconds <= 3600:
        raise ValueError('Qualification inference ceiling must be positive and at most one hour')
    root = Path(os.environ['CAD_PROBE_ROOT']) if os.environ.get('CAD_PROBE_ROOT') else Path(tempfile.mkdtemp(prefix='cad-clarification-live-'))
    ledger_name = os.environ.get('CAD_PROBE_LEDGER', 'calls.json')
    if Path(ledger_name).name != ledger_name or not ledger_name.endswith('.json'):
        raise ValueError('Campaign ledger must be a local JSON filename')
    ledger = root / ledger_name
    for key, name in {'EVIDENCE_ROOT': 'evidence', 'SESSIONS_DIR': 'sessions',
        'MEMORY_DIR': 'memory', 'SOUL_FILE': 'soul.json', 'ATTACHMENTS_DIR': 'attachments',
        'LOCAL_PROJECTS_DIR': 'local', 'WORKSPACE_DIR': 'workspace',
        'TASKS_FILE': 'tasks.json', 'CAD_DIR': 'cad'}.items():
        os.environ['BIGBRAIN_' + key] = str(root / name)
    os.environ['BIGBRAIN_RECALL'] = '0'
    os.environ['BIGBRAIN_FRONT_MODEL_KEY'] = 'codex-sol-6.1'
    os.environ['BIGBRAIN_PLANNER_MODEL_KEY'] = 'codex-sol-6.1'
    os.environ.pop('BIGBRAIN_WEB_PASSWORD', None)
    from dotenv import dotenv_values
    binary = os.environ.get('BIGBRAIN_CODEX_BINARY') or dotenv_values('.env').get('BIGBRAIN_CODEX_BINARY')
    if binary:
        os.environ['BIGBRAIN_CODEX_BINARY'] = binary
    from bigbrain.bus.bus import MessageBus
    from bigbrain.brains.cad_brain import CadBrain
    from bigbrain.front.front_brain import FrontBrain
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator
    from bigbrain.web.server import WebServer
    from bigbrain.llm.codex_provider import CodexProvider, close_codex_app_server

    class BoundedProvider:
        def __init__(self):
            self.provider = CodexProvider('codex-sol-6.1')
            self.calls = json.loads(ledger.read_text()) if ledger.exists() else []
            self.duration = sum(call.get('seconds', 0) for call in self.calls)

        def __getattr__(self, name):
            return getattr(self.provider, name)

        async def chat_complete(self, **arguments):
            from bigbrain.cad_resources import inference_phase, CadBudgetExceeded
            phase = inference_phase.get()
            if len(self.calls) >= maximum_calls or self.duration >= maximum_seconds:
                raise CadBudgetExceeded(f'CAD qualification reached its {maximum_calls}-call / {maximum_seconds:g}-second inference limit')
            if phase != 'inspection' and len(self.calls) >= maximum_calls - inspection_reserve:
                raise CadBudgetExceeded('CAD construction allowance reached; final inspection calls remain reserved')
            call = {'phase': 'front' if arguments.get('tool_schema') else 'cad', 'status': 'running'}
            call['cad_phase'] = phase
            self.calls.append(call)
            # Reserve the call durably before inference so an interrupted
            # campaign retains its consumed allowance at the next startup.
            ledger.write_text(json.dumps(self.calls, ensure_ascii=False, indent=2))
            started = time.monotonic()
            try:
                response = await asyncio.wait_for(self.provider.chat_complete(**arguments),
                                                  maximum_seconds - self.duration)
                call['response'] = response
                call['status'] = 'completed'
                return response
            except BaseException as error:
                call['error'] = str(error) or type(error).__name__
                call['status'] = 'cancelled' if isinstance(error, asyncio.CancelledError) else 'failed'
                raise
            finally:
                call['seconds'] = time.monotonic() - started
                self.duration += call['seconds']
                ledger.write_text(json.dumps(self.calls, ensure_ascii=False, indent=2))

    provider = BoundedProvider()
    bus = MessageBus(root / 'logs', auth=None)
    front = FrontBrain(bus, llm_provider=provider)
    orch = WorkspaceOrchestrator('default', bus, llm_provider=provider)
    cad = CadBrain('cad_brain', bus, llm_provider=provider)
    front.register_brain('cad_brain', 'Mechanical CAD from language, drawings and photographs with supplied dimensions')
    orch.register_brain('cad_brain', {'description': 'Mechanical CAD'})
    server = WebServer(bus, host='127.0.0.1', port=int(os.environ.get('CAD_PROBE_PORT', '0')))
    services = []
    try:
        for service in (orch, cad, front, server):
            await service.start()
            services.append(service)
        port = server._site._server.sockets[0].getsockname()[1]
        print(f'CAD_CLARIFICATION_READY {root} http://127.0.0.1:{port}/', flush=True)
        await asyncio.Event().wait()
    finally:
        for service in reversed(services):
            await service.stop()
        await bus.close()
        await close_codex_app_server()


if __name__ == '__main__':
    asyncio.run(main())
