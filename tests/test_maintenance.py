"""Frozen projects, real files/interpreters/tests; scripted models test protocol only."""
import asyncio
import json
import sysconfig
import venv
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bigbrain.brains.python_brain import PythonBrain
from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.execution_target import ExecutionTarget
from bigbrain.maintenance import ProjectTools, maintain, protected_test
from bigbrain.project_inspection import digest
from bigbrain.project_transaction import ProjectTransaction, active_transaction
from bigbrain.verification.evidence import default_repository
from bigbrain.verification.gate import RunGate
from bigbrain.verification.semantics import review_semantics


def project(tmp_path, *, large=False):
    root = tmp_path / 'workspace'
    directory = root / 'sandbox' / 'calculator'
    directory.mkdir(parents=True)
    (directory / 'main.py').write_text('from arithmetic import add\nprint(add(2, 3))\n')
    (directory / 'arithmetic.py').write_text('def add(a, b):\n    return a - b\n')
    (directory / 'test_arithmetic.py').write_text('from arithmetic import add\ndef test_add():\n    assert add(2, 3) == 5\n')
    (directory / '.project.json').write_text(json.dumps({'entry_point': 'main.py', 'deliverable_type': 'python'}))
    if large:
        for number in range(10):
            (directory / f'unrelated{number}.py').write_text('# Preserve unrelated module\n' * 2000)
    return ExecutionTarget('existing', 'sandbox/calculator', str(root)).prepare()


def patch(path='arithmetic.py', source='def add(a, b):\n    return a - b\n'):
    return {'type': 'patch', 'path': path, 'sha256': digest(source),
            'edits': [{'old': 'return a - b', 'new': 'return a + b'}]}


def recorded_stub_usage():
    """Synthetic accounting for deterministic providers, never live evidence."""
    from bigbrain.llm.usage import UsageRecord, get_tracker
    get_tracker().record(UsageRecord(model_id='offline-stub', provider='test', input_tokens=100,
                                    output_tokens=10, total_tokens=110))


@pytest.mark.asyncio
@pytest.mark.parametrize('cause,expected', [
    ('uninspected_evidence', 'review_pending'), ('contradiction', 'requires_arbitration'),
    ('environment_blocked', 'requires_arbitration')])
async def test_verification_routing_stops_worker_before_any_blind_edit(tmp_path, cause, expected):
    target = project(tmp_path)
    payload, transaction = approved_payload(target)
    provider = ScriptedProvider([{'type': 'verify'}, patch()])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    before = target.file('arithmetic.py').read_text()
    try:
        with brain.execution_scope(payload):
            result = await maintain(brain, payload, diagnose=AsyncMock(return_value={'status': 'failed'}),
                verify=AsyncMock(return_value={'success': False, 'verification': {'verdict': 'inconclusive',
                    'failures': [{'stage': 'tests', 'status': 'failed'},
                                 {'stage': 'semantics', 'details': {'cause': cause}}]}}))
        assert result['maintenance_status'] == expected
        assert len(provider.calls) == 1
        assert target.file('arithmetic.py').read_text() == before
        assert result['maintenance']['changed_files'] == []
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_missing_test_does_not_authorize_production_patch(tmp_path):
    target = project(tmp_path)
    payload, transaction = approved_payload(target)
    provider = ScriptedProvider([{'type': 'read', 'path': 'arithmetic.py'}, {'type': 'verify'},
        patch(), {'type': 'arbitrate', 'reason': 'Need a regression test first'}])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    before = target.file('arithmetic.py').read_text()
    verify = AsyncMock(return_value={'success': False, 'verification': {'verdict': 'inconclusive',
        'failures': [{'stage': 'semantics', 'details': {'cause': 'missing_test'}}]}})
    try:
        with brain.execution_scope(payload):
            result = await maintain(brain, payload, diagnose=AsyncMock(return_value={'status': 'passed'}), verify=verify)
        assert result['maintenance_status'] == 'requires_arbitration'
        assert target.file('arithmetic.py').read_text() == before
        assert verify.await_count == 1
        assert any(a['status'] == 'tool_error' for a in result['maintenance']['actions'])
    finally:
        transaction.finish()
        await bus.close()


class ScriptedProvider:
    """Return frozen actions; reviewer separately inspects actual test/source pages."""
    def __init__(self, actions):
        self.actions = iter(actions)
        self.calls = []
        self.review_reads = set()

    async def chat_complete(self, **kwargs):
        recorded_stub_usage()
        messages = kwargs['messages']
        self.calls.append(messages)
        if 'drafting acceptance contracts' in messages[0]['content']:
            return json.dumps(['add(2,3) returns five'])
        if 'independent acceptance reviewer' in messages[0]['content']:
            context = json.loads(messages[1]['content'])
            self.review_reads.update(context.get('inspected_paths', []))
            for path in ('test_arithmetic.py', 'arithmetic.py'):
                if path not in self.review_reads:
                    self.review_reads.add(path)
                    return json.dumps({'action': {'type': 'read', 'path': path}})
            return json.dumps({'decision': 'pass', 'contradictions': [], 'coverage': [
                {'criterion_id': str(i), 'tests': context['passing_tests'][:1],
                 'sources': ['arithmetic.py', 'test_arithmetic.py'],
                 'reason': 'test_add asserts add(2,3)==5 using the real imported implementation'}
                for i in range(len(context['criteria']))]})
        action = next(self.actions, None)
        if action is None:
            raise AssertionError(messages[1]['content'])
        return json.dumps({'action': action, 'notebook': 'Reproduce subtraction bug, repair arithmetic only.'})


def approved_payload(target):
    request = 'Repair addition so add(2,3) is five; preserve the existing CLI and tests'
    repo = default_repository()
    spec = RunGate(repo).build_spec(request, ['main.py'])
    spec.metadata['business_criteria'] = ['add(2,3) returns five']
    repo.save_spec(spec)
    approved = repo.approve_spec(spec.design_id, plan_id='maintenance')
    transaction = ProjectTransaction.begin(target, [])
    return {'type': 'maintain_project', 'project_name': 'calculator', 'user_request': request,
            'entry_point': 'main.py', 'deliverable_type': 'python', 'executable': True,
            'business_contracts': spec.metadata['business_criteria'],
            '_execution_target': target.to_payload(), '_transaction': str(transaction.journal),
            '_maintenance_manifest_sha': digest(target.file('.project.json').read_text()),
            'contract_revision': {'design_id': approved.design_id, 'revision': approved.revision}}, transaction


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['failed', 'passed', 'inconclusive'])
async def test_preflight_runs_before_model_and_controls_writes(tmp_path, status):
    target = project(tmp_path)
    payload, transaction = approved_payload(target)
    provider = ScriptedProvider([{'type': 'read', 'path': 'arithmetic.py'}, patch(),
                                 {'type': 'arbitrate', 'reason': 'Environment unavailable'}])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    async def diagnose():
        assert not provider.calls
        return {'status': status, 'reason': 'Baseline'}
    verify = AsyncMock(return_value={'success': True, 'verification': {'verdict': 'passed'}})
    try:
        with brain.execution_scope(payload):
            result = await maintain(brain, payload, diagnose=diagnose, verify=verify)
        first = json.loads(provider.calls[0][1]['content'])['runtime_state']
        assert first['diagnostics'][0]['status'] == status
        assert first['phase'] == ('blocked' if status == 'inconclusive' else 'investigating')
        assert result['success'] is (status != 'inconclusive')
        assert verify.await_count == (0 if status == 'inconclusive' else 1)
        assert result['maintenance']['runtime_state']['phase'] == ('blocked' if status == 'inconclusive' else 'validated')
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_grouped_read_patch_and_automatic_verification(tmp_path):
    target = project(tmp_path)
    payload, transaction = approved_payload(target)
    provider = ScriptedProvider([
        {'type': 'read_many', 'reads': [{'path': 'arithmetic.py'}, {'path': 'main.py'}]},
        {'type': 'patch_set', 'patches': [patch(), {'path': 'main.py',
            'sha256': digest(target.file('main.py').read_text()),
            'edits': [{'old': 'print(add(2, 3))', 'new': 'print(add(3, 2))'}]}]}])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    verify = AsyncMock(return_value={'success': True, 'verification': {'verdict': 'passed'}})
    try:
        with brain.execution_scope(payload):
            result = await maintain(brain, payload, diagnose=AsyncMock(return_value={'status': 'failed'}), verify=verify)
        assert result['success']
        assert len(provider.calls) == 2  # no model-directed diagnostic or verify turn
        context = json.loads(provider.calls[1][1]['content'])
        pages = json.loads(context['observations'][-1]['result'])['pages']
        assert [p['path'] for p in pages] == ['arithmetic.py', 'main.py']
        assert all(r['complete'] for r in context['runtime_state']['reads']['items'])
        assert verify.await_count == 1
        assert result['maintenance']['changed_files'] == ['arithmetic.py', 'main.py']
        assert result['maintenance']['runtime_state']['source_epoch'] == 2
    finally:
        assert transaction.finish()['state'] == 'rolled_back'
        await bus.close()
    assert 'return a - b' in target.file('arithmetic.py').read_text()


@pytest.mark.asyncio
async def test_ready_environment_automatically_refreshes_diagnostic(tmp_path):
    target = project(tmp_path)
    payload, transaction = approved_payload(target)
    provider = ScriptedProvider([{'type': 'prepare_environment'},
        {'type': 'read', 'path': 'arithmetic.py'}, patch()])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    brain.maintenance_prepare = AsyncMock(return_value={'status': 'ready'})
    diagnose = AsyncMock(side_effect=[{'status': 'inconclusive', 'reason': 'Environment absent'}, {'status': 'failed'}])
    try:
        with brain.execution_scope(payload):
            result = await maintain(brain, payload, diagnose=diagnose,
                verify=AsyncMock(return_value={'success': True, 'verification': {'verdict': 'passed'}}))
        assert result['success']
        assert diagnose.await_count == 2
        state = json.loads(provider.calls[1][1]['content'])['runtime_state']
        assert state['environment']['status'] == 'ready'
        assert state['patching_allowed']
        assert state['diagnostic_count'] == 2
        assert result['maintenance']['runtime_state']['source_epoch'] == 1
        identifiers = [row['observation_id'] for row in result['maintenance']['actions']]
        assert len(identifiers) == len(set(identifiers))
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.parametrize('bad', ['stale', 'protected', 'syntax', 'duplicate', 'oversize'])
def test_patch_set_validates_every_file_before_writes(tmp_path, bad):
    target = project(tmp_path)
    tools = ProjectTools(target)
    tools.read('arithmetic.py')
    tools.read('main.py')
    second = {'path': 'main.py', 'sha256': digest(target.file('main.py').read_text()),
              'edits': [{'old': 'print(add(2, 3))', 'new': 'print(add(3, 2))'}]}
    if bad == 'stale':
        second['sha256'] = 'wrong'
    elif bad == 'protected':
        second['path'] = 'test_arithmetic.py'
    elif bad == 'syntax':
        second['edits'][0]['new'] = 'print('
    elif bad == 'duplicate':
        second = patch()
    elif bad == 'oversize':
        second['edits'][0]['new'] = 'x' * 128001
    transaction = ProjectTransaction.begin(target, [])
    token = active_transaction.set(str(transaction.journal))
    try:
        if bad == 'protected':
            assert tools.patch_set([patch(), second])['status'] == 'requires_arbitration'
        else:
            with pytest.raises((ValueError, SyntaxError)):
                tools.patch_set([patch(), second])
        assert not tools.changed
        assert 'return a - b' in target.file('arithmetic.py').read_text()
    finally:
        active_transaction.reset(token)
        transaction.finish()


def test_patch_set_apply_failure_aborts_and_owner_restores_previous_writes(tmp_path, monkeypatch):
    from bigbrain import maintenance
    target = project(tmp_path)
    tools = ProjectTools(target)
    tools.read('arithmetic.py')
    tools.read('main.py')
    original = maintenance.write_text
    def failing_write(target, path, content):
        if path == 'main.py':
            raise OSError('Synthetic second write failure')
        return original(target, path, content)
    monkeypatch.setattr(maintenance, 'write_text', failing_write)
    transaction = ProjectTransaction.begin(target, [])
    token = active_transaction.set(str(transaction.journal))
    try:
        with pytest.raises(maintenance.PatchSetFailure):
            tools.patch_set([patch(), {'path': 'main.py',
                'sha256': digest(target.file('main.py').read_text()),
                'edits': [{'old': 'print(add(2, 3))', 'new': 'print(add(3, 2))'}]}])
    finally:
        active_transaction.reset(token)
        assert transaction.finish()['state'] == 'rolled_back'
    assert 'return a - b' in target.file('arithmetic.py').read_text()


@pytest.mark.asyncio
async def test_grouped_read_over_budget_does_not_grant_read_versions(tmp_path):
    target = project(tmp_path)
    target.file('huge.py').write_text(('X = ' + repr('a' * 900) + '\n') * 100)
    payload, transaction = approved_payload(target)
    provider = ScriptedProvider([{'type': 'read_many', 'reads': [{'path': 'huge.py'}] * 8},
        {'type': 'arbitrate', 'reason': 'Inspect smaller pages'}])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    try:
        with brain.execution_scope(payload):
            result = await maintain(brain, payload, diagnose=AsyncMock(return_value={'status': 'failed'}), verify=AsyncMock())
        assert result['maintenance']['runtime_state']['reads']['total'] == 0
        context = json.loads(provider.calls[1][1]['content'])
        assert 'no pages supplied' in context['observations'][-1]['result']
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_unchanged_failed_verification_stops_without_budget_loop(tmp_path):
    target = project(tmp_path)
    payload, transaction = approved_payload(target)
    provider = ScriptedProvider([{'type': 'verify'}, {'type': 'verify'}])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    try:
        with brain.execution_scope(payload):
            result = await maintain(brain, payload, diagnose=AsyncMock(return_value={'status': 'failed'}),
                verify=AsyncMock(return_value={'success': False, 'verification': {'verdict': 'failed',
                    'failures': [{'stage': 'tests', 'status': 'failed', 'details': {}}]}}))
        assert result['maintenance_status'] == 'no_progress'
        assert len(provider.calls) == 2
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_small_review_assembles_pinned_sources_without_read_round_trips():
    calls = []
    class Reviewing:
        async def chat_complete(self, **kwargs):
            recorded_stub_usage()
            calls.append(kwargs)
            assert kwargs['tool_schema']['name'] == 'acceptance_review_decision'
            context = json.loads(kwargs['messages'][1]['content'])
            assert context['observations'][0]['assembled_sources']['main.py'] == 'print(6)'
            assert set(context['inspected_paths']) == {'main.py', 'test_main.py'}
            return json.dumps({'decision': 'needs_evidence', 'contradictions': [],
                'missing_evidence': [{'criterion_id': '0', 'kind': 'missing_test',
                    'path': None, 'source_revision': 'current', 'request': 'CLI assertion absent'}], 'coverage': []})
    result = await review_semantics(Reviewing(), request='Repair', contracts=['Print six'],
        sources={'main.py': 'print(6)', 'test_main.py': 'assert True'},
        tests={'status': 'passed', 'passed_cases': ['test_main.py::test_ok']}, progressive=True)
    assert len(calls) == 1
    assert result.status == 'inconclusive'
    assert result.details['repairable_evidence_gap'] is True


def test_progressive_reader_handles_large_projects_without_source_dump(tmp_path):
    target = project(tmp_path, large=True)
    tools = ProjectTools(target)
    assert len(tools.inventory()) == 13
    first = tools.read('unrelated0.py', count=100)
    assert first['next_line'] == 101
    assert first['total_lines'] == 2000
    assert len(first['content']) < 14000
    result = tools.search('return a - b')
    assert result['hits'][0]['path'] == 'arithmetic.py'


def test_dynamic_journal_rejects_stale_reads_and_rolls_back(tmp_path):
    target = project(tmp_path)
    transaction = ProjectTransaction.begin(target, [])
    tools = ProjectTools(target)
    tools.read('arithmetic.py')
    token = active_transaction.set(str(transaction.journal))
    try:
        assert tools.patch(patch())['status'] == 'patched'
        with pytest.raises(ValueError, match='Read the file|changed since'):
            tools.patch(patch())
    finally:
        active_transaction.reset(token)
    assert transaction.finish()['state'] == 'rolled_back'
    assert 'return a - b' in target.file('arithmetic.py').read_text()


@pytest.mark.parametrize('path', ['test_arithmetic.py', 'tests/acceptance.json', 'src/math.test.ts',
                                 'conftest.py', 'pyproject.toml', 'package.json'])
def test_validation_is_not_an_unapproved_repair_surface(path):
    assert protected_test(path)


def test_concurrent_user_change_and_fencing_are_not_overwritten(tmp_path):
    target = project(tmp_path)
    tools = ProjectTools(target)
    tools.read('arithmetic.py')
    transaction = ProjectTransaction.begin(target, [])
    token = active_transaction.set(str(transaction.journal))
    try:
        target.file('arithmetic.py').write_text('# user edit\n')
        with pytest.raises(ValueError, match='changed since'):
            tools.patch(patch())
        tools.read('main.py')
        transaction.fence()
        with pytest.raises(ValueError, match='closed'):
            tools.patch({'path': 'main.py', 'sha256': tools.read_versions['main.py'],
                         'edits': [{'old': 'print(add(2, 3))', 'new': 'print(add(3, 2))'}]})
    finally:
        active_transaction.reset(token)
    transaction.finish()
    assert target.file('arithmetic.py').read_text() == '# user edit\n'


def test_new_regression_tests_allowed_but_existing_tests_stay_frozen(tmp_path):
    target = project(tmp_path)
    transaction = ProjectTransaction.begin(target, [])
    tools = ProjectTools(target)
    token = active_transaction.set(str(transaction.journal))
    try:
        result = tools.patch({'path': 'tests/test_regression.py', 'sha256': digest(''),
            'edits': [{'old': '', 'new': 'from arithmetic import add\ndef test_negative():\n    assert add(-2,3) == 1\n'}]})
        assert result['status'] == 'patched'
        result = tools.patch({'path': 'test_arithmetic.py'})
        assert result['status'] == 'requires_arbitration'
        assert tools.patch({'path': 'pytest.ini'})['status'] == 'requires_arbitration'
    finally:
        active_transaction.reset(token)
        transaction.finish()
    assert not target.file('tests/test_regression.py').exists()


@pytest.mark.asyncio
async def test_excessive_test_output_is_inconclusive_and_terminated(tmp_path):
    from bigbrain.verification.executors import stage_tests
    import sys
    target = project(tmp_path)
    target.file('test_arithmetic.py').write_text('def test_flood():\n    print("x" * 3000000)\n    assert False\n')
    result = await stage_tests(target.directory, python=sys.executable, timeout=10)
    assert result.status == 'inconclusive'
    assert 'execution budget' in result.details['reason']
    assert len(result.details['diagnostic_output']) <= 64030


@pytest.mark.asyncio
async def test_real_cross_module_repair_project_python_review_and_commit(tmp_path):
    target = project(tmp_path, large=True)
    venv.EnvBuilder(system_site_packages=True, with_pip=False).create(target.directory / '.venv')
    # Offline fixture only: reuse test dependencies explicitly. The child still
    # runs with its own real project sys.prefix; production never falls back.
    site = next((target.directory / '.venv/lib').glob('python*/site-packages'))
    (site / 'fixture-dependencies.pth').write_text(sysconfig.get_path('purelib') + '\n')
    before_tests = target.file('test_arithmetic.py').read_bytes()
    payload, transaction = approved_payload(target)
    provider = ScriptedProvider([{'type': 'list'}, {'type': 'diagnose'},
        {'type': 'read', 'path': 'main.py'}, {'type': 'read', 'path': 'arithmetic.py'}, patch(),
        {'type': 'diagnose'}, {'type': 'verify'}])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    try:
        result = await brain.handle_task(BusMessage(type=MessageType.TASK, source='orchestrator', target='python', payload=payload))
        assert result['success'], result
        assert result['stdout'].strip() == '5'
        assert result['maintenance']['changed_files'] == ['arithmetic.py']
        assert result['verification']['verdict'] == 'passed'
        assert target.file('test_arithmetic.py').read_bytes() == before_tests
        assert transaction.finish(commit=True)['state'] == 'committed'
        assert max(len(json.dumps(call)) for call in provider.calls) < 100000
        assert all('Preserve unrelated module' not in json.dumps(call) for call in provider.calls)
    finally:
        if json.loads(transaction.journal.read_text())['state'] == 'open':
            transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_flattened_review_action_is_rejected_then_corrected_not_executed():
    calls = []
    class Reviewing:
        async def chat_complete(self, **kwargs):
            recorded_stub_usage()
            calls.append(kwargs)
            if len(calls) == 1:
                return json.dumps({'action': 'read', 'path': 'main.py'})
            if len(calls) <= 3:
                return json.dumps({'action': {'type': 'read', 'path': ['main.py', 'test_main.py'][len(calls) - 2]}})
            return json.dumps({'decision': 'pass', 'contradictions': [], 'coverage': [{
                'criterion_id': '0', 'tests': ['test_main.py::test_ok'], 'runtime': [],
                'sources': ['main.py', 'test_main.py'], 'reason': 'Observed executed assertion'}]})
    result = await review_semantics(Reviewing(), request='Repair', contracts=['Print six'],
        sources={'main.py': 'print(6)', 'test_main.py': 'assert True', 'large.py': '# padding\n' * 6000},
        tests={'status': 'passed', 'passed_cases': ['test_main.py::test_ok']}, progressive=True)
    assert result.status == 'passed'
    assert len(calls) == 4
    assert json.loads(calls[1]['messages'][1]['content'])['inspected_paths'] == []
    assert 'action must be an OBJECT' in calls[1]['messages'][1]['content']


@pytest.mark.asyncio
async def test_runtime_diagnostic_survives_last_four_observations_and_notebook(tmp_path):
    target = project(tmp_path)
    payload, transaction = approved_payload(target)
    provider = ScriptedProvider([{'type': 'read', 'path': 'arithmetic.py'} for _ in range(6)] +
        [{'type': 'state_read', 'section': 'diagnostics'},
         {'type': 'arbitrate', 'reason': 'Need project environment'}])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    try:
        with brain.execution_scope(payload):
            result = await maintain(brain, payload, diagnose=AsyncMock(return_value={
                'status': 'inconclusive', 'reason': 'Project interpreter absent'}), verify=AsyncMock())
        context = json.loads(provider.calls[-2][1]['content'])
        assert all(item.get('action') != 'diagnose' for item in context['observations'])
        assert context['runtime_state']['diagnostics'][0]['observation_id'] == 'observation-initial'
        assert context['runtime_state']['patching_allowed'] is False
        assert context['runtime_state']['blockers'][0]['reason'] == 'Project interpreter absent'
        assert context['runtime_state']['reads']['items'][0]['complete'] is True
        assert result['maintenance']['runtime_state']['diagnostic_count'] == 1
        assert all(len(step['state_artifact_sha256']) == 64 for step in result['maintenance']['actions'])
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_unsupported_pass_becomes_actionable_missing_evidence_never_success():
    count = 0
    class MissingCLI:
        async def chat_complete(self, **kwargs):
            nonlocal count
            count += 1
            if count <= 2:
                return json.dumps({'action': {'type': 'read', 'path': ['main.py', 'test_main.py'][count - 1]}})
            return json.dumps({'decision': 'pass', 'contradictions': [], 'coverage': [{
                'criterion_id': '0', 'tests': [], 'runtime': [],
                'sources': ['main.py'], 'reason': 'Looks correct but no CLI assertion'}]})
    result = await review_semantics(MissingCLI(), request='Repair', contracts=['CLI prints six'],
        sources={'main.py': 'print(6)', 'test_main.py': 'assert True'},
        tests={'status': 'passed', 'passed_cases': ['test_main.py::test_ok']}, progressive=True)
    assert result.status == 'inconclusive'
    assert result.details['repairable_evidence_gap'] is False
    assert result.details['next_action'] == 'inspect'
    assert result.details['requires_arbitration'] is False
    assert 'CLI prints six' in result.details['review']['missing_evidence'][0]['request']
    assert result.details['review']['rejected_review']['decision'] == 'pass'


@pytest.mark.asyncio
async def test_reviewer_decision_phase_keeps_executed_evidence_requirements():
    seen = []
    class Reviewing:
        async def chat_complete(self, **kwargs):
            seen.append(kwargs['tool_schema'])
            assert seen[-1]['name'] == 'acceptance_review_decision'
            assert 'action' not in seen[-1]['parameters']['properties']
            return json.dumps({'decision': 'pass', 'contradictions': [], 'coverage': [{
                'criterion_id': '0', 'tests': ['invented::test'],
                'sources': ['main.py', 'test_main.py'], 'reason': 'Unsupported claim'}]})
    result = await review_semantics(Reviewing(), request='Repair', contracts=['Works'],
        sources={'main.py': 'pass', 'test_main.py': 'assert True'},
        tests={'status': 'passed', 'passed_cases': ['test_main.py::test_ok']}, progressive=True)
    assert result.status == 'inconclusive'
    assert len(seen) == 3  # assembled sources, then three rejected fabricated verdicts
    assert 'invalid output' in result.details['reason']


@pytest.mark.asyncio
async def test_reviewer_stops_repeated_pages_instead_of_spending_whole_budget():
    calls = []
    class Repeating:
        async def chat_complete(self, **kwargs):
            recorded_stub_usage()
            calls.append(kwargs)
            return json.dumps({'action': {'type': 'read', 'path': 'main.py', 'start': 1, 'count': 120}})
    result = await review_semantics(Repeating(), request='Repair', contracts=['Works'],
        sources={'main.py': 'pass', 'test_main.py': 'assert True', 'large.py': '# padding\n' * 6000},
        tests={'status': 'passed', 'passed_cases': ['test_main.py::test_ok']}, progressive=True)
    assert result.status == 'inconclusive'
    assert len(calls) == 6  # one page + two repeats, then at most three final-verdict corrections
    assert all(call['tool_schema']['name'] == 'acceptance_review_decision' for call in calls[-3:])
    assert 'unread_test_paths' in calls[2]['messages'][1]['content']


@pytest.mark.asyncio
async def test_three_invalid_action_shapes_stop_without_writes(tmp_path):
    target = project(tmp_path)
    payload, transaction = approved_payload(target)
    provider = ScriptedProvider(['read', 'read', 'read'])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    try:
        with brain.execution_scope(payload):
            result = await maintain(brain, payload, diagnose=AsyncMock(return_value={'status': 'failed'}), verify=AsyncMock())
        assert result['maintenance_status'] == 'protocol_error'
        assert len(provider.calls) == 3
        assert result['maintenance']['changed_files'] == []
        assert 'action must be an OBJECT' in provider.calls[1][1]['content']
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_missing_environment_is_inconclusive_not_a_patch_license(tmp_path):
    target = project(tmp_path)
    payload, transaction = approved_payload(target)
    provider = ScriptedProvider([{'type': 'diagnose'}, {'type': 'read', 'path': 'arithmetic.py'}, patch(),
                               {'type': 'arbitrate', 'reason': 'Project interpreter missing'}])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    try:
        result = await brain.handle_task(BusMessage(type=MessageType.TASK, source='orchestrator', target='python', payload=payload))
        assert result['maintenance_status'] == 'requires_arbitration'
        assert result['maintenance']['changed_files'] == []
        assert 'return a - b' in target.file('arithmetic.py').read_text()
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_loop_cannot_claim_success_or_weaken_tests_and_failure_rolls_back(tmp_path):
    target = project(tmp_path)
    payload, transaction = approved_payload(target)
    provider = ScriptedProvider([{'type': 'diagnose'}, {'type': 'read', 'path': 'arithmetic.py'}, patch(),
        {'type': 'finish', 'success': True}, {'type': 'patch', 'path': 'test_arithmetic.py'}])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    with brain.execution_scope(payload):
        result = await maintain(brain, payload, diagnose=AsyncMock(return_value={'status': 'failed'}),
            verify=AsyncMock(return_value={'success': False, 'verification': {'verdict': 'failed'}}))
    assert result['success'] is False
    assert result['maintenance_status'] == 'requires_arbitration'
    assert transaction.finish()['state'] == 'rolled_back'
    assert 'return a - b' in target.file('arithmetic.py').read_text()
    await bus.close()


@pytest.mark.asyncio
async def test_cancellation_does_not_swallow_stop_or_commit(tmp_path):
    target = project(tmp_path)
    payload, transaction = approved_payload(target)
    bus = MessageBus(tmp_path / 'logs', auth=None)
    provider = AsyncMock()
    provider.chat_complete.side_effect = asyncio.CancelledError
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    with pytest.raises(asyncio.CancelledError):
        await brain.handle_task(BusMessage(type=MessageType.TASK, source='orchestrator', target='python', payload=payload))
    assert transaction.finish()['state'] == 'rolled_back'
    await bus.close()


@pytest.mark.asyncio
async def test_progressive_reviewer_cannot_cite_unread_sources():
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps({'decision': 'pass', 'contradictions': [],
        'coverage': [{'criterion_id': '0', 'tests': ['test_a.py::test_a'],
                      'sources': ['a.py'], 'reason': 'Trust me'}]})
    result = await review_semantics(provider, request='Correct arithmetic', contracts=['Correct arithmetic'],
        sources={'a.py': 'A=1', 'test_a.py': 'assert True', 'large.py': '# padding\n' * 6000},
        tests={'status': 'passed', 'passed_cases': ['test_a.py::test_a']}, progressive=True)
    assert result.status == 'inconclusive'


@pytest.mark.asyncio
async def test_existing_target_uses_maintenance_even_when_assessed_as_small_script(tmp_path):
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator
    target = project(tmp_path)
    provider = AsyncMock()
    provider.chat_complete.side_effect = [json.dumps({'mode': 'script', 'deliverable_type': 'python',
        'needs_research': False}), json.dumps(['Addition returns the sum without changing existing tests'])]
    bus = MessageBus(tmp_path / 'logs', auth=None)
    orchestrator = WorkspaceOrchestrator('default', bus, llm_provider=provider)
    try:
        plan = await orchestrator._create_task_plan(BusMessage(type=MessageType.TASK, source='morphable_ui',
            target=orchestrator.name, payload={'type': 'compound', 'user_request': 'Fix addition',
                                             'project_target': target.public()}))
        assert [step.payload['type'] for step in plan.subtasks] == ['maintain_project']
        assert plan.inspection is None
        assert plan.subtasks[0].brain_target == 'python_brain'
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_bus_approval_dispatch_live_progress_and_terminal_commit(tmp_path):
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator
    target = project(tmp_path)
    venv.EnvBuilder(with_pip=False).create(target.directory / '.venv')
    site = next((target.directory / '.venv/lib').glob('python*/site-packages'))
    (site / 'fixture-dependencies.pth').write_text(sysconfig.get_path('purelib') + '\n')
    provider = ScriptedProvider([{'type': 'diagnose'}, {'type': 'read', 'path': 'arithmetic.py'}, patch(), {'type': 'verify'}])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python_brain', bus, work_dir=Path(target.root), llm_provider=provider)
    orchestrator = WorkspaceOrchestrator('default', bus, llm_provider=provider)
    orchestrator._extract_learnings = AsyncMock()
    events, finished = [], asyncio.Event()
    async def observe(message):
        events.append(message)
        if message.payload.get('event') in {'task.complete', 'task.failed'}:
            finished.set()
    bus.subscribe('*', observe)
    await orchestrator.start()
    await brain.start()
    orchestrator.register_brain(brain.name, {'type': 'PythonBrain'})
    try:
        await bus.send(BusMessage(type=MessageType.TASK, source='morphable_ui', target=orchestrator.name,
            payload={'type': 'maintain_project', 'deliverable_type': 'python', 'user_request': 'Repair addition',
                     'project_target': target.public(), 'session_id': 'maintenance-session'}))
        proposal = next(m.payload for m in events if m.payload.get('event') == 'contracts.proposal')
        assert 'return a - b' in target.file('arithmetic.py').read_text()
        assert not list(Path(target.root).glob('.bigbrain-transactions/*.json'))
        await bus.send(BusMessage(type=MessageType.TASK, source='morphable_ui', target=orchestrator.name,
            payload={'type': 'contracts.approval', 'design_id': proposal['design_id'],
                     'plan_id': proposal['plan_id'], 'approve': True}))
        await asyncio.wait_for(finished.wait(), timeout=10)
        terminal = next(m.payload for m in events if m.payload.get('event') in {'task.complete', 'task.failed'})
        assert terminal['event'] == 'task.complete', terminal
        assert terminal['project_path'] == target.path
        assert any(m.payload.get('stage') == 'maintenance_patch' for m in events)
        journals = list(Path(target.root).glob('.bigbrain-transactions/*.json'))
        assert len(journals) == 1
        assert json.loads(journals[0].read_text())['state'] == 'committed'
    finally:
        await brain.stop()
        await orchestrator.stop()
        await bus.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['new', 'existing'])
async def test_web_specialist_repairs_actual_browser_behavior(tmp_path, mode):
    from bigbrain.brains.web_app_brain import WebAppBrain
    root = tmp_path / 'workspace'
    directory = root / 'sandbox/widget'
    (directory / 'tests').mkdir(parents=True)
    (directory / 'index.html').write_text('<main><button>Calculer</button><output>0</output></main><script src="app.js"></script>')
    (directory / 'styles.css').write_text('main { color: black; }\n')
    source = 'document.querySelector("button").onclick = () => { document.querySelector("output").textContent = "4"; };\n'
    (directory / 'app.js').write_text(source)
    acceptance = {'schema_version': 2, 'cases': [{'name': 'calculer',
        'steps': [{'op': 'click', 'selector': 'button'}],
        'assertions': [{'op': 'text', 'selector': 'output', 'value': '5'}]}]}
    (directory / 'tests/acceptance.json').write_text(json.dumps(acceptance))
    (directory / '.project.json').write_text('{"entry_point":"index.html","deliverable_type":"web_app"}')
    target = ExecutionTarget('existing', 'sandbox/widget', str(root)).prepare()
    if mode == 'new':
        from dataclasses import replace
        target = replace(target, mode='new')  # already reserved generated candidate
    repo = default_repository()
    spec = RunGate(repo).build_spec('Clicking Calculer must show five', ['index.html'])
    spec.metadata['business_criteria'] = ['Clicking Calculer shows five']
    repo.save_spec(spec)
    approved = repo.approve_spec(spec.design_id, plan_id='web-maintenance')
    transaction = ProjectTransaction.begin(target, [])
    class WebProvider(ScriptedProvider):
        async def chat_complete(self, **kwargs):
            recorded_stub_usage()
            if 'independent acceptance reviewer' not in kwargs['messages'][0]['content']:
                return await super().chat_complete(**kwargs)
            context = json.loads(kwargs['messages'][1]['content'])
            for path in ('tests/acceptance.json', 'app.js'):
                if path not in self.review_reads:
                    self.review_reads.add(path)
                    return json.dumps({'action': {'type': 'read', 'path': path}})
            return json.dumps({'decision': 'pass', 'contradictions': [], 'coverage': [{
                'criterion_id': '0', 'tests': context['passing_tests'], 'sources': ['tests/acceptance.json', 'app.js'],
                'reason': 'Real browser clicks the button and asserts output five'}]})
    provider = WebProvider(([{'type': 'diagnose'}] if mode == 'existing' else []) + [{'type': 'read', 'path': 'app.js'},
        {'type': 'patch', 'path': 'app.js', 'sha256': digest(source), 'edits': [{'old': '"4"', 'new': '"5"'}]},
        {'type': 'verify'}])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = WebAppBrain('web_app_brain', bus, work_dir=root, llm_provider=provider)
    payload = {'type': 'maintain_project', 'project_name': 'widget', 'user_request': spec.user_request,
        'deliverable_type': 'web_app', 'web_stack': 'static', 'entry_point': 'index.html',
        'business_contracts': spec.metadata['business_criteria'],
        '_execution_target': target.to_payload(), '_transaction': str(transaction.journal),
        '_maintenance_manifest_sha': digest(target.file('.project.json').read_text()),
        'contract_revision': {'design_id': approved.design_id, 'revision': approved.revision}}
    if mode == 'new':
        payload['type'] = 'assemble_and_preview'
    try:
        result = await brain.handle_task(BusMessage(type=MessageType.TASK, source='orchestrator', target=brain.name, payload=payload))
        assert result['success'], result
        assert result['verification']['browser_tests_executed'] is True
        assert result['maintenance']['changed_files'] == ['app.js']
        assert transaction.finish(commit=True)['state'] == 'committed'
        assert json.loads(target.file('tests/acceptance.json').read_text()) == acceptance
    finally:
        if json.loads(transaction.journal.read_text())['state'] == 'open':
            transaction.finish()
        await brain.cleanup()
        await bus.close()


@pytest.mark.asyncio
async def test_reviewer_provider_failure_keeps_status_without_request_secrets():
    import httpx
    from bigbrain.verification.semantics import review_semantics

    class Unavailable:
        async def chat_complete(self, **kwargs):
            request = httpx.Request('POST', 'https://provider.invalid', headers={'Authorization': 'secret'})
            response = httpx.Response(402, request=request, text='sensitive provider body')
            response.raise_for_status()

    result = await review_semantics(Unavailable(), request='Repair', contracts=['Works'],
        sources={'main.py': 'pass'}, tests={'status': 'passed', 'passed_cases': ['test_main.py::test_ok']})
    assert result.status == 'inconclusive'
    assert result.details['provider_http_status'] == 402
    assert 'secret' not in str(result.details)
    assert 'sensitive provider body' not in str(result.details)
