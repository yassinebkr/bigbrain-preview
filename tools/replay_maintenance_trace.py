"""Offline maintenance replay through the production stdio reader and runtime.

The server mode is a deterministic protocol fixture: it cannot call a model.
Recorded replies remain unchanged; an unrecorded independent review fails closed.
Synthetic cross-module review validates runtime plumbing, not model competence.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def digest_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def recorded_bundle(trace, native):
    """Read only this explicitly selected trace, never scan other conversations."""
    files = sorted(trace.glob('call-*.json')) or sorted((trace / 'model-calls').glob('[0-9][0-9][0-9].json'))
    planning, workers, reviews, originals = None, [], [], []
    for path in files:
        saved = json.loads(path.read_text())
        response = saved['response']
        value = json.loads(response)
        schema = (saved.get('tool_schema') or {}).get('name', '')
        if schema.startswith('acceptance_review') or isinstance(value, dict) and 'decision' in value and 'action' not in value:
            reviews.append(response)
        elif isinstance(value, dict) and 'action' in value:
            workers.append(response)
        elif isinstance(value, list):
            planning = response
        else:
            raise ValueError('Unrecognized recorded response shape')
        originals.append(response)
    archived_input = ''
    if native:
        items = [json.loads(line) for line in native.read_text().splitlines()]
        assistants = [x['payload'] for x in items if x['type'] == 'response_item' and x['payload'].get('role') == 'assistant']
        users = [x['payload'] for x in items if x['type'] == 'response_item' and x['payload'].get('role') == 'user']
        if len(assistants) == len(workers) + 1:
            recovered = ''.join(c.get('text', '') for c in assistants[-1]['content'])
            if not isinstance(json.loads(recovered).get('action'), dict):
                raise ValueError('Missing native worker response is not an action')
            workers.append(recovered)
            originals.append(recovered)
        elif len(assistants) != len(workers):
            raise ValueError('Native worker trace and application trace cannot be reconciled')
        archived_input = ''.join(c.get('text', '') for c in users[-1]['content'])
    if not workers:
        raise ValueError('No recorded worker responses')
    return {'planning': planning, 'worker': workers, 'review': reviews,
            'archived_notification': archived_input,
            'reply_hashes': [digest_bytes(s.encode()) for s in originals],
            'review_policy': 'Recorded responses only; fail when continuation is unavailable, never manufacture acceptance'}


def synthetic_bundle(bus=False):
    from tools.run_maintenance_campaign import fixture
    files, _ = fixture('cross-module')
    action = lambda a: json.dumps({'action': a, 'notebook': 'Synthetic offline protocol fixture'})
    coverage = [{'criterion_id': str(i), 'tests': ['test_arithmetic.py::test_add', 'test_arithmetic.py::test_preserved'],
                'runtime': ['validation_unchanged'], 'sources': ['arithmetic.py', 'test_arithmetic.py'],
                'reason': 'Synthetic reviewer fixture; actual assertions execute addition and unchanged().'}
                for i in range(1)]
    return {'planning': json.dumps(['Addition works; unchanged() and existing tests are preserved.']),
        'planning_repetitions': 2 if bus else 1,
        'worker': [action({'type': 'read_many', 'reads': [{'path': 'arithmetic.py'}, {'path': 'test_arithmetic.py'}]}),
                   action({'type': 'patch', 'path': 'arithmetic.py',
                       'sha256': digest_bytes(files['arithmetic.py'].encode()),
                       'edits': [{'old': 'return a - b', 'new': 'return a + b'}]})],
        'review': [json.dumps({'decision': 'pass', 'contradictions': [], 'missing_evidence': [],
            'coverage': coverage,
            'notebook': 'This is not an independent model verdict.'})],
        'archived_notification': '', 'review_policy': 'Synthetic protocol assertion, not model judgment'}


def stdio_server(bundle_path, log_path, disconnect=False):
    bundle = json.loads(Path(bundle_path).read_text())
    threads, turns = 0, 0
    cursors = {'planning': 0, 'worker': 0, 'review': 0}
    def emit(message):
        sys.stdout.write(json.dumps(message, ensure_ascii=False) + '\n')
        sys.stdout.flush()
    for line in sys.stdin:
        request = json.loads(line)
        method, params = request['method'], request.get('params', {})
        if 'id' not in request:
            continue
        if method == 'initialize':
            result = {}
        elif method == 'account/read':
            result = {'account': {'type': 'chatgpt', 'email': 'offline-replay@example.invalid'},
                      'workspaceRouting': {'chatgptAccountId': 'offline-replay'}}
        elif method in {'thread/start', 'thread/resume'}:
            threads += 1
            result = {'thread': {'id': params.get('threadId', f'offline-thread-{threads}')}}
        elif method == 'turn/interrupt':
            result = {}
        elif method == 'turn/start':
            turns += 1
            turn = f'offline-turn-{turns}'
            properties = (params.get('outputSchema') or {}).get('properties', {})
            phase = 'review' if 'decision' in properties else 'worker' if 'action' in properties else 'planning'
            index = cursors[phase]
            cursors[phase] += 1
            with open(log_path, 'a') as log:
                log.write(json.dumps({'phase': phase, 'index': index, 'params': params}) + '\n')
            emit({'id': request['id'], 'result': {'turn': {'id': turn}}})
            if disconnect and phase == 'worker' and index == len(bundle['worker']) - 1:
                return
            if phase == 'worker' and index == len(bundle['worker']) - 1 and bundle['archived_notification']:
                # Reconstructed framing around the EXACT archived native input.
                emit({'method': 'item/started', 'params': {'threadId': params['threadId'],
                    'item': {'type': 'userMessage', 'content': [{'type': 'text', 'text': bundle['archived_notification']}]}}})
            replies = ([bundle['planning']] * bundle.get('planning_repetitions', 1) if bundle['planning'] is not None else []) if phase == 'planning' else bundle[phase]
            if index >= len(replies):
                emit({'method': 'turn/completed', 'params': {'threadId': params['threadId'],
                    'turn': {'id': turn, 'status': 'failed', 'error': {'message': 'No recorded response for this phase'}}}})
                continue
            emit({'method': 'item/completed', 'params': {'threadId': params['threadId'],
                'item': {'type': 'agentMessage', 'text': replies[index]}}})
            emit({'method': 'turn/completed', 'params': {'threadId': params['threadId'],
                'turn': {'id': turn, 'status': 'completed'}}})
            continue
        else:
            emit({'id': request['id'], 'error': {'message': 'Unsupported offline RPC method'}})
            continue
        emit({'id': request['id'], 'result': result})


async def run_bus_fixture(provider, scratch):
    """Exercise real proposal, approval, bus dispatch, progress and terminal owner."""
    import sysconfig
    import venv
    from tools.run_maintenance_campaign import fixture
    from bigbrain.brains.python_brain import PythonBrain
    from bigbrain.bus.bus import MessageBus
    from bigbrain.bus.message import BusMessage, MessageType
    from bigbrain.execution_target import ExecutionTarget
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator
    workspace = scratch / 'workspace'
    project = workspace / 'sandbox/cross-module'
    project.mkdir(parents=True)
    for path, text in fixture('cross-module')[0].items():
        (project / path).write_text(text)
    (project / '.project.json').write_text(json.dumps({'entry_point': 'main.py', 'deliverable_type': 'python'}))
    venv.EnvBuilder(with_pip=False).create(project / '.venv')
    site = next((project / '.venv/lib').glob('python*/site-packages'))
    (site / 'fixture-dependencies.pth').write_text(sysconfig.get_path('purelib') + '\n')
    target = ExecutionTarget('existing', 'sandbox/cross-module', str(workspace)).prepare()
    os.environ['BIGBRAIN_WORKSPACE_DIR'] = str(workspace)
    bus = MessageBus(scratch / 'logs', auth=None)
    brain = PythonBrain('python_brain', bus, work_dir=workspace, llm_provider=provider)
    orchestrator = WorkspaceOrchestrator('default', bus, llm_provider=provider)
    events, finished = [], asyncio.Event()
    async def observe(message):
        events.append(message.payload)
        if message.payload.get('event') in {'task.complete', 'task.failed'}:
            finished.set()
    bus.subscribe('*', observe)
    await orchestrator.start()
    await brain.start()
    orchestrator.register_brain(brain.name, {'type': 'PythonBrain'})
    try:
        await bus.send(BusMessage(type=MessageType.TASK, source='morphable_ui', target=orchestrator.name,
            payload={'type': 'maintain_project', 'deliverable_type': 'python',
                'user_request': fixture('cross-module')[1], 'project_target': target.public(), 'session_id': 'replay-bus'}))
        proposal = next(e for e in events if e.get('event') == 'contracts.proposal')
        if 'return a - b' not in (project / 'arithmetic.py').read_text():
            raise AssertionError('Sources changed before approval')
        await bus.send(BusMessage(type=MessageType.TASK, source='morphable_ui', target=orchestrator.name,
            payload={'type': 'contracts.approval', 'design_id': proposal['design_id'],
                     'plan_id': proposal['plan_id'], 'approve': True}))
        await asyncio.wait_for(finished.wait(), 30)
        terminal = next(e for e in events if e.get('event') in {'task.complete', 'task.failed'})
        journals = [json.loads(p.read_text()) for p in (workspace / '.bigbrain-transactions').glob('*.json')]
        return {'success': terminal['event'] == 'task.complete', 'terminal': terminal,
                'transaction': {'state': journals[-1]['state']},
                'event_names': [e.get('event', e.get('stage')) for e in events],
                'approval': 'synthetic replay approval through the actual bus; no UI exercised'}
    finally:
        await brain.stop()
        await orchestrator.stop()
        await bus.close()


async def replay(args):
    from tools.run_maintenance_campaign import run_case, load_frozen_contracts
    from bigbrain.brains.python_brain import PythonBrain
    from bigbrain.llm.codex_provider import CodexProvider, CodexJsonRpcClient, RPC_FRAME_LIMIT
    scratch = Path(tempfile.mkdtemp(prefix='bigbrain-maintenance-replay-'))
    bundle = synthetic_bundle(args.bus) if args.case == 'cross-module' else recorded_bundle(args.trace_root, args.native_trace)
    if bundle['planning'] is None and not args.contract_file:
        raise ValueError('No recorded planning reply; an explicit frozen contract file is required')
    if args.case == 'gcode':
        # Exact input equality is a precondition, not a claim based on names.
        frozen = args.trace_root / 'gcode-maintenance/workspace/sandbox/gcode'
        original = ROOT / 'workspace/sandbox/klipper-gcode-offline'
        for path in frozen.rglob('*'):
            relative = path.relative_to(frozen)
            if path.is_file() and not any(p.startswith('.') or p == '__pycache__' for p in relative.parts):
                if path.read_bytes() != (original / relative).read_bytes():
                    raise ValueError('Original project differs from recorded replay input: ' + str(relative))
    bundle_path, rpc_log = scratch / 'bundle.json', scratch / 'rpc.jsonl'
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False))
    for key in ('SESSIONS_DIR', 'MEMORY_DIR', 'ATTACHMENTS_DIR', 'EVIDENCE_ROOT'):
        os.environ['BIGBRAIN_' + key] = str(scratch / key.lower())
    os.environ['BIGBRAIN_SOUL_FILE'] = str(scratch / 'soul.json')
    os.environ['CODEX_CHATGPT_MODEL'] = 'gpt-6.1-sol'
    os.environ['BIGBRAIN_CODEX_EFFORT'] = 'low'
    old_start, old_verify = CodexJsonRpcClient.start, PythonBrain.maintenance_verify
    candidate = {}
    async def start():
        proc = await asyncio.create_subprocess_exec(sys.executable, __file__, '--stdio-server',
            str(bundle_path), str(rpc_log), *(['--disconnect'] if args.disconnect else []),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, limit=RPC_FRAME_LIMIT)
        client = CodexJsonRpcClient(proc)
        client._reader_task = asyncio.create_task(client._read_loop())
        return client
    async def verify(brain, payload, tools):
        # Observe before rollback; always delegate judgments to production gates.
        candidate['sources'] = {p: tools.source(p) for p in tools.inventory()}
        result = await old_verify(brain, payload, tools)
        candidate['verification'] = result.get('verification')
        return result
    CodexJsonRpcClient.start = staticmethod(start)
    PythonBrain.maintenance_verify = verify
    provider = CodexProvider()
    started = time.monotonic()
    print('Replay evidence:', scratch, flush=True)
    try:
        if args.bus:
            result = await asyncio.wait_for(run_bus_fixture(provider, scratch), timeout=90)
        else:
            result = await asyncio.wait_for(run_case(args.case, 'maintenance', provider, scratch,
                approve_gcode_conflicts=args.case == 'gcode',
                frozen_contracts=load_frozen_contracts(args.contract_file) if args.contract_file else None), timeout=90)
    finally:
        await asyncio.wait_for(provider.aclose(), timeout=10)
        CodexJsonRpcClient.start, PythonBrain.maintenance_verify = old_start, old_verify
    frames = [json.loads(line) for line in rpc_log.read_text().splitlines()]
    worker_inputs = [f['params']['input'][0]['text'] for f in frames if f['phase'] == 'worker']
    transmitted_ids = []
    for text in worker_inputs:
        for part in text.split('\n\nUSER: '):
            part = part.removeprefix('USER: ')
            try:
                decoded = json.loads(part)
                transmitted_ids.extend(e['event_id'] for e in decoded.get('events', []))
            except ValueError:
                pass
    if len(transmitted_ids) != len(set(transmitted_ids)):
        raise AssertionError('An already transmitted event was replayed')
    result.update(offline_only=True, real_inference_calls=0, provider_usage='not emitted by offline protocol fixture',
        review_policy=bundle['review_policy'], replay_seconds=round(time.monotonic() - started, 3),
        transmitted_event_ids=transmitted_ids, worker_threads=sorted({f['params']['threadId'] for f in frames if f['phase'] == 'worker'}),
        recorded_reply_hashes=bundle.get('reply_hashes'), disconnect_injected=args.disconnect)
    exhausted = [f for f in frames if f['index'] >= (bundle.get('planning_repetitions', 1) if f['phase'] == 'planning' else len(bundle[f['phase']]))]
    if exhausted:
        result['trace_boundary'] = {'phase': exhausted[0]['phase'], 'index': exhausted[0]['index'],
            'reason': 'No further recorded reply; no continuation was invented',
            'last_verification': candidate.get('verification')}
    (scratch / 'candidate.json').write_text(json.dumps(candidate, indent=2))
    (scratch / 'replay-result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result.get(k) for k in ('success', 'status', 'error', 'transaction',
        'transmitted_event_ids', 'worker_threads', 'replay_seconds', 'review_policy')}), flush=True)
    return result


if __name__ == '__main__':
    if '--stdio-server' in sys.argv:
        stdio_server(sys.argv[2], sys.argv[3], '--disconnect' in sys.argv)
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--case', choices=['gcode', 'cross-module'], required=True)
        parser.add_argument('--trace-root', type=Path)
        parser.add_argument('--native-trace', type=Path)
        parser.add_argument('--disconnect', action='store_true')
        parser.add_argument('--bus', action='store_true')
        parser.add_argument('--contract-file', type=Path)
        args = parser.parse_args()
        if args.case == 'gcode' and args.trace_root is None:
            parser.error('G-code replay requires an explicit archived trace root')
        if args.bus and args.case != 'cross-module':
            parser.error('--bus is the synthetic cross-module protocol fixture')
        if args.bus and args.contract_file:
            parser.error('--bus exercises actual contract generation/approval, not frozen fixture acceptance')
        asyncio.run(replay(args))
