"""Opt-in live comparison on disposable projects; never edits production examples.

Run: .venv/bin/python tools/run_maintenance_campaign.py --live --case cross-module
No paid call without --live. Results and raw evidence remain in a private temp
folder. Fixture approvals are synthetic harness approvals, not UI validation.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import sys
import sysconfig
import tempfile
import time
import venv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def fixture(case):
    if case == 'local':
        return {'main.py': 'def twice(n):\n    return n + 2\n\nif __name__ == "__main__":\n    print(twice(3))\n',
                'test_main.py': 'from main import twice\ndef test_twice():\n    assert twice(3) == 6\n    assert twice(0) == 0\n'}, 'Fix twice(n) to double n, preserving CLI and tests.'
    files = {'main.py': 'from arithmetic import add\nprint(add(2, 3))\n',
             'arithmetic.py': 'def add(a, b):\n    return a - b\n\ndef unchanged():\n    return "keep"\n',
             'test_arithmetic.py': 'from arithmetic import add, unchanged\ndef test_add():\n    assert add(2, 3) == 5\n    assert add(-2, 3) == 1\ndef test_preserved():\n    assert unchanged() == "keep"\n'}
    request = 'Repair add(a,b) to add its arguments; preserve CLI, interfaces, unrelated behavior and existing tests.'
    if case == 'contradiction':
        files['test_arithmetic.py'] = 'from arithmetic import add\ndef test_add():\n    assert add(2, 3) == -1\n'
        request += ' Existing tests must not override this addition requirement; report any contradiction explicitly.'
    if case == 'large':
        files.update({f'unrelated{i}.py': '# Unrelated module must be preserved\n' * 2000 for i in range(8)})
    return files, request


async def run_case(case, workflow, provider, scratch, *, approve_gcode_conflicts=False):
    from bigbrain.brains.python_brain import PythonBrain
    from bigbrain.bus.bus import MessageBus
    from bigbrain.bus.message import BusMessage, MessageType
    from bigbrain.execution_target import ExecutionTarget
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, TaskPlan
    from bigbrain.project_inspection import digest
    from bigbrain.project_transaction import ProjectTransaction
    from bigbrain.verification.evidence import default_repository
    from bigbrain.verification.contracts import build_proposal_spec
    from bigbrain.llm.usage import get_tracker
    folder = scratch / f'{case}-{workflow}'
    workspace, evidence = folder / 'workspace', folder / 'evidence'
    directory = workspace / 'sandbox' / case
    directory.mkdir(parents=True)
    for key, name in {'BIGBRAIN_WORKSPACE_DIR': workspace, 'BIGBRAIN_EVIDENCE_ROOT': evidence,
            'BIGBRAIN_MEMORY_DIR': folder / 'memory', 'BIGBRAIN_SOUL_FILE': folder / 'soul.json',
            'BIGBRAIN_SESSIONS_DIR': folder / 'sessions', 'BIGBRAIN_ATTACHMENTS_DIR': folder / 'attachments'}.items():
        os.environ[key] = str(name)
    original_hashes = {}
    decisions = []
    if case == 'gcode':
        from bigbrain.project_inspection import SENSITIVE_NAME, SENSITIVE_TEXT
        import hashlib
        original = ROOT / 'workspace/sandbox/klipper-gcode-offline'
        # Only project sources, no credentials/runtime caches, no external links.
        for base, dirs, names in os.walk(original, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'__pycache__', 'node_modules'}
                       and not (Path(base) / d).is_symlink()]
            for name in names:
                source = Path(base) / name
                if (source.suffix not in {'.py', '.md', '.txt', '.json'} or name.startswith('.')
                        or source.is_symlink() or SENSITIVE_NAME.search(name)):
                    continue
                if SENSITIVE_TEXT.search(source.read_text(errors='replace')):
                    continue
                destination = directory / source.relative_to(original)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                original_hashes[str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
        request = ('Repair the existing offline Klipper G-code analyzer: inspect the real entry point and tests, '
                   'reproduce failures, preserve both existing APIs and unrelated behavior, and apply minimal corrections. '
                   'Explicit command temperature setpoints are calculated, comments are declared, neither are measured. '
                   'Do not communicate with printers or invent geometry. If tests contradict requirements, '
                   'request arbitration with precise evidence instead of weakening them. Keep main.py runnable.')
        if approve_gcode_conflicts:
            request += (' User-approved arbitration for this disposable copy ONLY: correct the contradictory tests. '
                'Explicit command temperature setpoints are calculated, comment declarations are declared; neither is measured. '
                'For Klipper G91 makes E relative even after M82; G90 restores absolute E when M82 remains active. '
                'Preserve the safety assertions and other behavior. Authority verified in the official source: '
                'https://github.com/Klipper3d/klipper/blob/master/klippy/extras/gcode_move.py '
                '(cmd_G1 uses absolute_coord; M82 only allows absolute extrusion; G91 sets absolute_coord=False).')
            decisions = [
                {'path': 'tests/test_analysis.py', 'reason': 'Resolve contradictory M82/G91 expectations',
                 'expected_behavior': 'Relative E under G91 even with M82; G90 restores absolute when M82 active; retain geometry/retraction safety assertions',
                 'authority': 'Explicit user approval in this thread; official Klipper klippy/extras/gcode_move.py cmd_G1/M82/G90/G91 verified'},
                {'path': 'tests/test_gcode_analyzer.py', 'reason': 'Align temperature provenance tests with the approved requirement',
                 'expected_behavior': 'Command setpoints calculated; comments declared; neither is a measured temperature; preserve value/identity/safety assertions',
                 'authority': 'Explicit user approval in this thread for the disposable copy only'}]
    else:
        files, request = fixture(case)
        for path, text in files.items():
            (directory / path).write_text(text)
    # Harness supplies metadata/entry for these imported fixtures. This is not
    # evidence that an agent discovered a missing manifest or entry point.
    (directory / '.project.json').write_text(json.dumps({'entry_point': 'main.py', 'deliverable_type': 'python'}))
    if case != 'missing-environment':
        venv.EnvBuilder(with_pip=False).create(directory / '.venv')
        site = next((directory / '.venv/lib').glob('python*/site-packages'))
        (site / 'campaign-dependencies.pth').write_text(sysconfig.get_path('purelib') + '\n')
    target = ExecutionTarget('existing', 'sandbox/' + case, str(workspace)).prepare()
    before = {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob('*')
              if p.is_file() and '.venv' not in p.parts and '__pycache__' not in p.parts}
    bus = MessageBus(folder / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=workspace, llm_provider=provider)
    repo, tracker = default_repository(), get_tracker()
    tracker.reset()
    started, transaction, plan = time.monotonic(), None, None
    result = {}
    try:
        original_task = BusMessage(type=MessageType.TASK, source='campaign', target='orchestrator_default',
            payload={'type': 'compound', 'user_request': request, 'project_target': target.public(),
                     'test_changes': decisions, 'session_id': 'campaign'})
        orchestrator = WorkspaceOrchestrator('default', bus, llm_provider=provider)
        plan = TaskPlan(f'campaign-{case}-{workflow}', original_task)
        if workflow == 'maintenance':
            subtasks = await orchestrator._plan_maintenance(plan, request, 'python')
            contracts = plan.project_spec.acceptance_contracts
        else:
            subtasks = await orchestrator._plan_project(plan.id, request, False, [], deliverable_type='python', plan=plan)
            contracts = plan.project_spec.acceptance_contracts
        spec = build_proposal_spec(request, contracts)
        spec.metadata['business_criteria'] = contracts
        spec.metadata['maintenance'] = {'test_changes': decisions}
        repo.save_spec(spec)
        approved = repo.approve_spec(spec.design_id, plan_id=plan.id, by='synthetic-fixture-harness')
        paths = [s.payload['file_path'] for s in subtasks if s.payload.get('file_path')]
        transaction = ProjectTransaction.begin(target, paths)
        for subtask in subtasks:
            payload = {**subtask.payload, '_execution_target': target.to_payload(), '_transaction': str(transaction.journal),
                'contract_revision': {'design_id': approved.design_id, 'revision': approved.revision},
                'business_contracts': contracts, 'acceptance_contracts': contracts}
            result = await brain.handle_task(BusMessage(type=MessageType.TASK, source='campaign', target='python', payload=payload))
            if not result.get('success'):
                break
        rollback = transaction.finish(commit=bool(result.get('success')))
    except asyncio.CancelledError:
        if transaction:
            transaction.fence()
            transaction.finish()
        raise
    except Exception as exc:
        # Never print provider request/auth objects; record only exception class.
        result = {'success': False, 'error_class': type(exc).__name__}
        response = getattr(exc, 'response', None)
        if response is not None:
            result['provider_http_status'] = response.status_code
        rollback = transaction.finish() if transaction else None
    finally:
        await bus.close()
    after = {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob('*')
             if p.is_file() and '.venv' not in p.parts and '__pycache__' not in p.parts}
    if original_hashes:
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in original_hashes.items()), 'Original source unexpectedly changed'
    summary = {'case': case, 'workflow': workflow, 'success': result.get('success', False),
        'original_source_unchanged': True if original_hashes else None,
        'approved_test_changes': decisions,
        'status': result.get('maintenance_status'), 'error': result.get('error') or result.get('error_class'),
        'provider_http_status': result.get('provider_http_status'),
        'elapsed_seconds': round(time.monotonic() - started, 2), 'transaction': rollback,
        'changed_files_after_transaction': sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)),
        'usage': {k: v for k, v in tracker.totals().items() if k != 'cost_usd'},
        'verification': result.get('verification'), 'maintenance': result.get('maintenance'),
        'arbitration': result.get('arbitration'), 'fixture_approval': 'synthetic harness; not user UI validation'}
    (folder / 'result.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k not in {'maintenance', 'verification', 'arbitration'}}, ensure_ascii=False), flush=True)
    return summary


async def main(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    load_dotenv(ROOT / 'data/provider_keys.env')
    from bigbrain.auth.registry import build_provider
    from bigbrain.llm.model_registry import DEFAULT_CODE_MODEL_KEY
    provider = build_provider(args.model or DEFAULT_CODE_MODEL_KEY)
    scratch = Path(tempfile.mkdtemp(prefix='bigbrain-maintenance-campaign-'))
    print('Evidence directory:', scratch, flush=True)
    entry = getattr(provider, 'entry', None)
    (scratch / 'provider-profile.json').write_text(json.dumps({
        'registry_key': getattr(provider, 'registry_key', None),
        'model': getattr(entry, 'model_id', None),
        'reasoning_effort': getattr(entry, 'reasoning_effort_default', None),
        'reasoning_timeout_seconds': getattr(provider, 'reasoning_timeout_seconds', 0),
    }, indent=2))
    import hashlib
    snapshot = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [*sorted((ROOT / 'bigbrain').rglob('*.py')), Path(__file__)]}
    (scratch / 'implementation.json').write_text(json.dumps(snapshot, indent=2))
    original_chat = provider.chat_complete
    replies = scratch / 'model-calls'
    replies.mkdir()
    call_number = 0
    async def recorded_chat(messages=None, **kwargs):
        nonlocal call_number
        call_number += 1
        number = call_number
        try:
            response = await original_chat(messages=messages, **kwargs)
        except ValueError as exc:
            # Protocol exceptions contain runtime-authored diagnostics only;
            # keep them private to distinguish malformed output from API errors.
            (replies / f'{number:03}-error.json').write_text(json.dumps({
                'type': 'ValueError', 'reason': str(exc)[:1000]}))
            raise
        # Private local experiment evidence, not provider headers or secrets.
        (replies / f'{number:03}.json').write_text(json.dumps({'messages': messages,
            'response_format': kwargs.get('response_format'), 'tool_schema': kwargs.get('tool_schema'),
            'response': response}, ensure_ascii=False))
        return response
    provider.chat_complete = recorded_chat
    cases = ['local', 'cross-module', 'contradiction', 'missing-environment', 'large'] if args.case == 'all' else [args.case]
    try:
        for case in cases:
            for workflow in (['legacy', 'maintenance'] if args.compare else ['maintenance']):
                await run_case(case, workflow, provider, scratch, approve_gcode_conflicts=args.approve_gcode_conflicts)
    finally:
        if getattr(provider, '_client', None):
            await provider._client.aclose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--case', choices=['all', 'local', 'cross-module', 'contradiction', 'missing-environment', 'large', 'gcode'], default='cross-module')
    parser.add_argument('--compare', action='store_true')
    parser.add_argument('--approve-gcode-conflicts', action='store_true',
                        help='Requires explicit user approval for the documented test semantics on the copy')
    parser.add_argument('--model')
    args = parser.parse_args()
    if not args.live:
        parser.error('--live is required: this campaign makes paid model calls')
    asyncio.run(main(args))
