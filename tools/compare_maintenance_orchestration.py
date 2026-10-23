"""Opt-in paired local fixture; same current subscription adapter on both sides.

Only frozen orchestration modules are substituted, never the working checkout.
No live call without --live. Evidence contains synthetic sources, not secrets.
"""
import argparse
import asyncio
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import time
import types
import venv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASELINE = '79d9cfe'
CONTRACTS = [
    'twice(n) returns n * 2 for numeric inputs, including zero and negative values.',
    'main.py preserves the existing CLI arguments and output format while reporting the corrected doubled value.',
    'Existing tests remain present and pass alongside regression tests for twice(n).',
]
MAX_CALLS, TOKEN_LIMIT = 24, 300000


class ComparisonBudget(RuntimeError):
    pass


def frozen_sources():
    return {name: subprocess.check_output(
        ['git', 'show', f'{BASELINE}:bigbrain/{name}.py'], cwd=ROOT, text=True)
        for name in ('maintenance', 'maintenance_state', 'verification/semantics')}


@contextmanager
def orchestration(variant, frozen):
    from bigbrain import maintenance
    from bigbrain.verification import semantics
    original = maintenance.maintain, semantics._progressive_review
    if variant == 'before':
        modules = {}
        for name, source in frozen.items():
            module = types.ModuleType('bigbrain.' + name.replace('/', '.'))
            module.__package__ = 'bigbrain.verification' if '/' in name else 'bigbrain'
            exec(compile(source, f'{BASELINE}/{name}.py', 'exec'), module.__dict__)
            modules[name] = module
        modules['maintenance'].MaintenanceState = modules['maintenance_state'].MaintenanceState
        maintenance.maintain = modules['maintenance'].maintain
        semantics._progressive_review = modules['verification/semantics']._progressive_review
    try:
        yield
    finally:
        maintenance.maintain, semantics._progressive_review = original


async def run_variant(variant, root, frozen):
    from tools.run_maintenance_campaign import fixture
    from bigbrain.brains.python_brain import PythonBrain
    from bigbrain.bus.bus import MessageBus
    from bigbrain.bus.message import BusMessage, MessageType
    from bigbrain.execution_target import ExecutionTarget
    from bigbrain.llm.codex_provider import CodexProvider
    from bigbrain.llm.usage import get_tracker
    from bigbrain.project_inspection import digest
    from bigbrain.project_transaction import ProjectTransaction
    from bigbrain.verification.contracts import build_proposal_spec
    from bigbrain.verification.evidence import default_repository

    folder = root / variant
    folder.mkdir()
    for key, directory in {'WORKSPACE_DIR': 'workspace', 'EVIDENCE_ROOT': 'evidence',
            'MEMORY_DIR': 'memory', 'SOUL_FILE': 'soul.json', 'SESSIONS_DIR': 'sessions',
            'ATTACHMENTS_DIR': 'attachments'}.items():
        os.environ['BIGBRAIN_' + key] = str(folder / directory)
    workspace = folder / 'workspace'
    project = workspace / 'sandbox/local'
    project.mkdir(parents=True)
    files, request = fixture('local')
    for path, source in files.items():
        (project / path).write_text(source)
    manifest = json.dumps({'entry_point': 'main.py', 'deliverable_type': 'python'})
    (project / '.project.json').write_text(manifest)
    # Deliberate offline harness dependency sharing, identical on both sides.
    # Tests run with the real project sys.prefix, never a runtime host fallback.
    venv.EnvBuilder(with_pip=False).create(project / '.venv')
    site = next((project / '.venv/lib').glob('python*/site-packages'))
    (site / 'comparison-dependencies.pth').write_text(sysconfig.get_path('purelib') + '\n')
    target = ExecutionTarget('existing', 'sandbox/local', str(workspace)).prepare()
    spec = build_proposal_spec(request, CONTRACTS)
    spec.metadata.update(business_criteria=CONTRACTS, maintenance={'test_changes': []}, execution_target=target.public())
    repo = default_repository()
    repo.save_spec(spec)
    approved = repo.approve_spec(spec.design_id, plan_id='paired-local', by='synthetic-fixture-harness')
    transaction = ProjectTransaction.begin(target, [])
    payload = {'type': 'maintain_project', 'project_name': 'local', 'user_request': request,
        'entry_point': 'main.py', 'deliverable_type': 'python', 'executable': True,
        'session_id': 'paired-local', '_execution_target': target.to_payload(),
        '_transaction': str(transaction.journal), '_maintenance_manifest_sha': digest(manifest),
        'contract_revision': {'design_id': approved.design_id, 'revision': approved.revision},
        'business_contracts': CONTRACTS, 'acceptance_contracts': CONTRACTS}
    tracker = get_tracker()
    tracker.reset()
    provider = CodexProvider()
    assert provider.reasoning_effort == 'low'
    assert provider.default_model == 'gpt-6.1-sol'
    call = provider.chat_complete
    ledger = []
    async def measured(*args, **kwargs):
        if len(ledger) >= MAX_CALLS or tracker.totals()['total_tokens'] >= TOKEN_LIMIT:
            raise ComparisonBudget('Shared comparison budget reached; no automatic retry')
        schema = kwargs.get('tool_schema') or {}
        row = {'number': len(ledger) + 1,
               'phase': 'review' if schema.get('name', '').startswith('acceptance_review') else 'worker'}
        ledger.append(row)
        before_count = len(tracker._records)
        started_call = time.monotonic()
        try:
            response = await call(*args, **kwargs)
            (folder / f'call-{row["number"]:02}.json').write_text(json.dumps({
                'messages': kwargs.get('messages', args[0] if args else None),
                'tool_schema': schema, 'response': response}, ensure_ascii=False))
            row['completed'] = True
            return response
        except BaseException as exc:
            row['error_type'] = type(exc).__name__
            raise
        finally:
            row['seconds'] = round(time.monotonic() - started_call, 3)
            row['usage_records'] = [asdict(r) for r in tracker._records[before_count:]]
            (folder / 'calls.json').write_text(json.dumps(ledger, indent=2))
            print(json.dumps({'variant': variant, **{k: row[k] for k in ('number', 'phase', 'seconds')},
                'completed': row.get('completed', False), 'reported_tokens': tracker.totals()['total_tokens']}), flush=True)
    provider.chat_complete = measured
    bus = MessageBus(folder / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=workspace, llm_provider=provider)
    started = time.monotonic()
    result, closed = {}, None
    try:
        with orchestration(variant, frozen):
            result = await asyncio.wait_for(brain.handle_task(BusMessage(type=MessageType.TASK,
                source='comparison', target='python', payload=payload)), timeout=620)
        closed = transaction.finish(commit=bool(result.get('success')))
    except BaseException as exc:
        result = {'success': False, 'error_type': type(exc).__name__}
        transaction.fence()
        closed = transaction.finish()
        if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)):
            raise
    finally:
        await provider.aclose()
        await bus.close()
        states = [json.loads(p.read_text()) for p in (folder / 'sessions/codex').rglob('*.json')]
        after = {p.relative_to(project).as_posix(): digest(p.read_text()) for p in project.rglob('*')
                 if p.is_file() and '.venv' not in p.parts and '__pycache__' not in p.parts}
        before = {**{p: digest(s) for p, s in files.items()}, '.project.json': digest(manifest)}
        summary = {'variant': variant, 'success': result.get('success', False), 'result': result,
            'seconds': round(time.monotonic() - started, 3), 'calls': len(ledger),
            'phase_calls': {phase: sum(r['phase'] == phase for r in ledger) for phase in ('worker', 'review')},
            'usage': tracker.totals(), 'transaction': closed,
            'initial_hashes': before, 'final_hashes': after,
            'changed_files': sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p)),
            'existing_tests_unchanged': before['test_main.py'] == after.get('test_main.py'),
            'bindings': states, 'usage_unknown': any(s.get('usage_incomplete') or s.get('compaction_usage_unknown') for s in states),
            'fixture_approval': 'synthetic; not UI user validation', 'interventions': 0}
        (folder / 'result.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k not in {'result', 'bindings', 'initial_hashes', 'final_hashes'}}), flush=True)
    return summary


async def main():
    os.environ['CODEX_CHATGPT_MODEL'] = 'gpt-6.1-sol'
    os.environ['BIGBRAIN_CODEX_EFFORT'] = 'low'
    root = Path(tempfile.mkdtemp(prefix='bigbrain-orchestration-pair-'))
    print('Evidence directory:', root, flush=True)
    frozen = frozen_sources()
    (root / 'protocol.json').write_text(json.dumps({'baseline': BASELINE, 'order': ['before', 'after'],
        'model': 'gpt-6.1-sol', 'effort': 'low', 'provider': 'codex-chatgpt',
        'contracts': CONTRACTS, 'call_limit': MAX_CALLS, 'reported_token_soft_limit': TOKEN_LIMIT,
        'token_limit_note': 'Checked before next call; last call can exceed limit; missing counters unknown',
        'session_policy': 'fresh sessions directory per variant; persistent worker; independent review scopes',
        'baseline_sha256': {k: hashlib.sha256(v.encode()).hexdigest() for k, v in frozen.items()},
        'working_sources': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / 'bigbrain').rglob('*.py'))},
        'limitations': 'One sequential pair; no statistical significance; cache/order and generation variability remain'}, indent=2))
    results = [await run_variant(v, root, frozen) for v in ('before', 'after')]
    (root / 'comparison.json').write_text(json.dumps(results, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    if not parser.parse_args().live:
        parser.error('--live required; consumes subscription usage')
    asyncio.run(main())
