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
from dataclasses import asdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def recorded_tokens(ledger):
    """Only reported per-call records count; missing usage is explicitly unknown."""
    return sum(record['total_tokens'] for call in ledger for record in call.get('usage_records', []))


def load_frozen_contracts(path):
    contracts = json.loads(Path(path).read_text())
    if (not isinstance(contracts, list) or not 1 <= len(contracts) <= 20
            or not all(isinstance(item, str) and item.strip() for item in contracts)):
        raise ValueError('Frozen contracts must contain 1..20 nonempty criteria')
    return contracts


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


async def run_case(case, workflow, provider, scratch, *, approve_gcode_conflicts=False, frozen_contracts=None):
    from bigbrain.brains.python_brain import PythonBrain
    from bigbrain.bus.bus import MessageBus
    from bigbrain.bus.message import BusMessage, MessageType
    from bigbrain.execution_target import ExecutionTarget
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, TaskPlan, SubTask
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
        if frozen_contracts is not None:
            if workflow != 'maintenance':
                raise ValueError('Frozen maintenance acceptance is not a creation-DAG contract')
            # Deliberately isolate maintenance from contract generation. This is
            # a preapproved fixture, not evidence of live UI/planner approval.
            contracts = list(frozen_contracts)
            subtasks = [SubTask(id='frozen-maintenance', description=request, brain_target='python_brain',
                payload={'type': 'maintain_project', 'project_name': case, 'user_request': request, 'entry_point': 'main.py',
                    'deliverable_type': 'python', 'executable': True,
                    '_maintenance_manifest_sha': digest((directory / '.project.json').read_text())})]
        elif workflow == 'maintenance':
            subtasks = await orchestrator._plan_maintenance(plan, request, 'python')
            contracts = plan.project_spec.acceptance_contracts
        else:
            subtasks = await orchestrator._plan_project(plan.id, request, False, [], deliverable_type='python', plan=plan)
            contracts = plan.project_spec.acceptance_contracts
        spec = build_proposal_spec(request, contracts)
        spec.metadata['business_criteria'] = contracts
        spec.metadata['maintenance'] = {'test_changes': decisions}
        spec.metadata['execution_target'] = target.public()
        repo.save_spec(spec)
        approved = repo.approve_spec(spec.design_id, plan_id=plan.id, by='synthetic-fixture-harness')
        paths = [s.payload['file_path'] for s in subtasks if s.payload.get('file_path')]
        transaction = ProjectTransaction.begin(target, paths)
        for subtask in subtasks:
            payload = {**subtask.payload, '_execution_target': target.to_payload(), '_transaction': str(transaction.journal),
                'session_id': original_task.payload['session_id'], '_plan_id': plan.id, '_subtask_id': subtask.id,
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
    frozen_contracts = load_frozen_contracts(args.contract_file) if getattr(args, 'contract_file', None) else None
    if frozen_contracts is not None and (args.case == 'all' or args.compare):
        raise ValueError('A frozen contract requires one maintenance case, no comparison')
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    load_dotenv(ROOT / 'data/provider_keys.env')
    if args.model == 'codex-chatgpt':
        os.environ['CODEX_CHATGPT_MODEL'] = args.native_model
        os.environ['BIGBRAIN_CODEX_EFFORT'] = args.reasoning
    from bigbrain.auth.registry import build_provider
    from bigbrain.llm.model_registry import DEFAULT_CODE_MODEL_KEY
    scratch = Path(tempfile.mkdtemp(prefix='bigbrain-maintenance-campaign-'))
    # Session stores bind their root during provider construction, before the
    # per-case directories exist. Isolate them here, not after the first call.
    for key in ('SESSIONS_DIR', 'MEMORY_DIR', 'ATTACHMENTS_DIR', 'EVIDENCE_ROOT'):
        os.environ['BIGBRAIN_' + key] = str(scratch / key.lower())
    os.environ['BIGBRAIN_SOUL_FILE'] = str(scratch / 'soul.json')
    provider = build_provider(args.model or DEFAULT_CODE_MODEL_KEY)
    print('Evidence directory:', scratch, flush=True)
    entry = getattr(provider, 'entry', None)
    (scratch / 'provider-profile.json').write_text(json.dumps({
        'registry_key': getattr(provider, 'registry_key', None),
        'model': getattr(entry, 'model_id', None),
        'reasoning_effort': getattr(provider, 'reasoning_effort', getattr(entry, 'reasoning_effort_default', None)),
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
    ledger = []
    from bigbrain.llm.usage import get_tracker
    from bigbrain.llm.conversation import current_conversation
    async def recorded_chat(messages=None, **kwargs):
        nonlocal call_number
        if (call_number >= args.max_calls or recorded_tokens(ledger) >= args.max_reported_tokens
                or any(r.get('usage_state') == 'unknown' for r in ledger)):
            raise RuntimeError('Campaign budget reached; no automatic retry')
        call_number += 1
        number = call_number
        schema = kwargs.get('tool_schema') or {}
        phase = ('review' if schema.get('name', '').startswith('acceptance_review') else
                 'worker' if schema.get('name') == 'project_maintenance_step' else 'planning')
        row = {'number': number, 'phase': phase, 'scope': current_conversation.get(), 'state': 'pending'}
        ledger.append(row)
        (scratch / 'calls.json').write_text(json.dumps(ledger, indent=2))
        tracker = get_tracker()
        before_count, started_call = len(tracker._records), time.monotonic()
        (replies / f'{number:03}-request.json').write_text(json.dumps({
            'messages': messages, 'tool_schema': kwargs.get('tool_schema'),
            'response_format': kwargs.get('response_format')}, ensure_ascii=False))
        try:
            response = await original_chat(messages=messages, **kwargs)
            row['state'] = 'completed'
        except BaseException as exc:
            row.update(state='failed', error_class=type(exc).__name__)
            # Protocol exceptions contain runtime-authored diagnostics only;
            # keep them private to distinguish malformed output from API errors.
            (replies / f'{number:03}-error.json').write_text(json.dumps({
                'type': type(exc).__name__,
                'reason': str(exc)[:2000] if isinstance(exc, (ValueError, RuntimeError)) else 'Provider/transport call failed'}))
            raise
        finally:
            row['seconds'] = round(time.monotonic() - started_call, 3)
            row['usage_records'] = [asdict(record) for record in tracker._records[before_count:]]
            row['usage_state'] = 'reported' if row['usage_records'] else 'unknown'
            sessions = getattr(provider, '_conversations', None)
            if sessions is not None:
                row['bindings'] = [{key: value.get(key) for key in ('thread_id', 'last_request',
                    'compactions', 'usage_incomplete', 'compaction_usage_unknown')} for value in sessions.loaded.values()]
            (scratch / 'calls.json').write_text(json.dumps(ledger, indent=2))
            print(json.dumps({'call': number, 'phase': phase, 'state': row['state'],
                'seconds': row['seconds'], 'reported_tokens': recorded_tokens(ledger),
                'usage_state': row['usage_state']}), flush=True)
        # Private local experiment evidence, not provider headers or secrets.
        (replies / f'{number:03}.json').write_text(json.dumps({'messages': messages,
            'response_format': kwargs.get('response_format'), 'tool_schema': kwargs.get('tool_schema'),
            'response': response}, ensure_ascii=False))
        return response
    provider.chat_complete = recorded_chat
    cases = ['local', 'cross-module', 'contradiction', 'missing-environment', 'large'] if args.case == 'all' else [args.case]
    campaign = {'status': 'running', 'results': [], 'limits': {'calls': args.max_calls,
        'reported_tokens': args.max_reported_tokens, 'seconds': args.timeout,
        'token_limit_kind': 'soft; checked before next call, unknown usage is not zero'}}
    started = time.monotonic()
    provider.review_budget_status = lambda: {
        'calls': args.max_calls - call_number,
        'tokens': args.max_reported_tokens - recorded_tokens(ledger),
        'seconds': args.timeout - (time.monotonic() - started)}
    try:
        async def execute():
            for case in cases:
                for workflow in (['legacy', 'maintenance'] if args.compare else ['maintenance']):
                    campaign['results'].append(await run_case(case, workflow, provider, scratch,
                        approve_gcode_conflicts=args.approve_gcode_conflicts, frozen_contracts=frozen_contracts))
        await asyncio.wait_for(execute(), timeout=args.timeout)
        campaign['status'] = 'completed'
        campaign['all_delivered'] = bool(campaign['results']) and all(r.get('success') for r in campaign['results'])
    except Exception as exc:
        campaign.update(status='interrupted', error_class=type(exc).__name__)
    finally:
        try:
            if hasattr(provider, 'aclose'):
                await asyncio.wait_for(provider.aclose(), timeout=10)
            if getattr(provider, '_client', None):
                await asyncio.wait_for(provider._client.aclose(), timeout=10)
        except Exception as exc:
            campaign.update(status='shutdown_failed', shutdown_error_class=type(exc).__name__)
        finally:
            campaign.update(seconds=round(time.monotonic() - started, 3), reported_tokens=recorded_tokens(ledger),
                unknown_usage_calls=[r['number'] for r in ledger if r.get('usage_state') == 'unknown'],
                calls_by_phase={phase: sum(r['phase'] == phase for r in ledger) for phase in ('planning', 'worker', 'review')})
            (scratch / 'campaign-result.json').write_text(json.dumps(campaign, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--case', choices=['all', 'local', 'cross-module', 'contradiction', 'missing-environment', 'large', 'gcode'], default='cross-module')
    parser.add_argument('--compare', action='store_true')
    parser.add_argument('--approve-gcode-conflicts', action='store_true',
                        help='Requires explicit user approval for the documented test semantics on the copy')
    parser.add_argument('--model')
    parser.add_argument('--native-model', default='gpt-6.1-sol')
    parser.add_argument('--reasoning', choices=['low', 'medium', 'high'], default='low')
    parser.add_argument('--max-calls', type=int, default=24)
    parser.add_argument('--max-reported-tokens', type=int, default=300000)
    parser.add_argument('--timeout', type=int, default=620)
    parser.add_argument('--contract-file', type=Path, help='Frozen criteria JSON; skips model contract drafting for one maintenance fixture')
    args = parser.parse_args()
    if not args.live:
        parser.error('--live is required: this campaign makes paid model calls')
    if min(args.max_calls, args.max_reported_tokens, args.timeout) <= 0:
        parser.error('Campaign budgets must be positive')
    asyncio.run(main(args))
