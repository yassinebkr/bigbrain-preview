"""Shared protocol gates on real disposable files; no paid inference."""
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bigbrain.brains.python_brain import PythonBrain
from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.execution_target import ExecutionTarget
from bigbrain.maintenance import repair_project
from bigbrain.project_inspection import digest
from bigbrain.project_transaction import ProjectTransaction
from bigbrain.verification.evidence import default_repository
from bigbrain.verification.gate import RunGate


class Actions:
    def __init__(self, actions):
        self.actions, self.calls = iter(actions), []

    async def chat_complete(self, **kwargs):
        self.calls.append(kwargs)
        return json.dumps({'action': next(self.actions), 'notebook': 'Recorded evidence only'})


def candidate(tmp_path, actions=()):
    root = tmp_path / 'workspace'
    root.mkdir()
    target = ExecutionTarget('new', 'example', str(root)).prepare()
    target.file('main.py').write_text('VALUE = 1\nprint(VALUE)\n')
    target.file('test_value.py').write_text('from main import VALUE\ndef test_value():\n    assert VALUE == 2\n')
    spec = RunGate(default_repository()).build_spec('Return and print two', ['main.py', 'test_value.py'])
    spec.metadata.update(business_criteria=['VALUE is two'], execution_target=target.public())
    default_repository().save_spec(spec)
    spec = default_repository().approve_spec(spec.design_id, plan_id='new-project')
    transaction = ProjectTransaction.begin(target, [])
    payload = {'type': 'assemble_and_run', 'user_request': spec.user_request,
        'deliverable_type': 'python', 'project_name': 'example', 'entry_point': 'main.py',
        'business_contracts': ['VALUE is two'], 'all_files': [{'path': 'main.py'}, {'path': 'test_value.py'}],
        'contract_revision': {'design_id': spec.design_id, 'revision': spec.revision},
        '_execution_target': target.to_payload(), '_transaction': str(transaction.journal)}
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=root, llm_provider=Actions(actions))
    return target, payload, transaction, bus, brain


def failure(cause='reproduced_defect'):
    return {'success': False, 'verification': {'verdict': 'failed',
        'failures': [{'stage': 'tests', 'status': 'failed', 'details': {'cause': cause}}]}}


def edit(value=2):
    return {'type': 'patch', 'path': 'main.py',
        'sha256': digest(f'VALUE = {value - 1}\nprint(VALUE)\n'),
        'edits': [{'old': f'VALUE = {value - 1}', 'new': f'VALUE = {value}'}]}


@pytest.mark.asyncio
@pytest.mark.parametrize('cause,expected', [('uninspected_evidence', 'review_pending'),
    ('contradiction', 'requires_arbitration'), ('environment_blocked', 'requires_arbitration')])
async def test_new_project_initial_gate_blocks_edits(tmp_path, cause, expected):
    target, payload, transaction, bus, brain = candidate(tmp_path)
    diagnose, verify = AsyncMock(), AsyncMock(return_value=failure(cause))
    try:
        with brain.execution_scope(payload):
            result = await repair_project(brain, payload, mode='new', diagnose=diagnose, verify=verify)
        assert result['maintenance_status'] == expected
        assert not result['success'] and not result['runnable']
        assert not brain.llm_provider.calls
        diagnose.assert_not_awaited()
        assert target.file('main.py').read_text().startswith('VALUE = 1')
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_new_project_passes_without_developer_turn(tmp_path):
    _, payload, transaction, bus, brain = candidate(tmp_path)
    diagnose = AsyncMock()
    try:
        with brain.execution_scope(payload):
            result = await repair_project(brain, payload, mode='new', diagnose=diagnose,
                verify=AsyncMock(return_value={'success': True, 'verification': {'verdict': 'passed'}}))
        assert result['success'] and result['repair']['mode'] == 'new'
        assert result['repair']['repair_rounds'] == 0
        assert not brain.llm_provider.calls
        diagnose.assert_not_awaited()
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_shared_engine_reverifies_each_patch_and_stops_at_two_rounds(tmp_path):
    actions = []
    for value in (2, 3, 4):
        actions += [{'type': 'read', 'path': 'main.py'}, edit(value)]
    target, payload, transaction, bus, brain = candidate(tmp_path, actions)
    verify = AsyncMock(return_value=failure())
    try:
        with brain.execution_scope(payload):
            result = await repair_project(brain, payload, mode='new', diagnose=AsyncMock(), verify=verify)
        assert result['maintenance_status'] == 'repair_budget_exhausted'
        assert result['maintenance']['repair_rounds'] == 2
        assert verify.await_count == 3  # initial gate + each applied patch
        assert target.file('main.py').read_text().startswith('VALUE = 3')
    finally:
        assert transaction.finish()['state'] == 'rolled_back'
        await bus.close()
    assert target.file('main.py').read_text().startswith('VALUE = 1')


@pytest.mark.asyncio
async def test_missing_validation_does_not_authorize_new_production_edits(tmp_path):
    target, payload, transaction, bus, brain = candidate(tmp_path,
        [{'type': 'read', 'path': 'main.py'}, edit(), {'type': 'arbitrate', 'reason': 'Need a regression test'}])
    try:
        with brain.execution_scope(payload):
            result = await repair_project(brain, payload, mode='new', diagnose=AsyncMock(),
                verify=AsyncMock(return_value=failure('missing_test')))
        assert result['maintenance_status'] == 'requires_arbitration'
        assert result['maintenance']['changed_files'] == []
        assert target.file('main.py').read_text().startswith('VALUE = 1')
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_new_validation_is_checked_before_production_repair(tmp_path):
    new_test = {'type': 'patch', 'path': 'test_regression.py', 'sha256': digest(''),
        'edits': [{'old': '', 'new': 'from main import VALUE\ndef test_regression():\n    assert VALUE == 2\n'}]}
    _, payload, transaction, bus, brain = candidate(tmp_path,
        [new_test, {'type': 'read', 'path': 'main.py'}, edit()])
    verify = AsyncMock(side_effect=[failure('missing_test'), failure(),
        {'success': True, 'verification': {'verdict': 'passed'}}])
    try:
        with brain.execution_scope(payload):
            result = await repair_project(brain, payload, mode='new', diagnose=AsyncMock(), verify=verify)
        assert result['success']
        assert verify.await_count == 3
        assert result['repair']['repair_rounds'] == 2
        assert result['repair']['changed_files'] == ['main.py', 'test_regression.py']
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_browser_validation_file_can_be_added_but_not_replaced(tmp_path):
    from bigbrain.maintenance import ProjectTools
    target, payload, transaction, bus, brain = candidate(tmp_path)
    action = {'path': 'tests/acceptance.json', 'sha256': digest(''),
        'edits': [{'old': '', 'new': '{"schema_version":2,"cases":[]}'}]}
    try:
        with brain.execution_scope(payload):
            tools = ProjectTools(target)
            assert tools.patch(action)['status'] == 'patched'
            tools.read('tests/acceptance.json')
            action['sha256'] = digest(target.file('tests/acceptance.json').read_text())
            action['edits'] = [{'old': '"cases":[]', 'new': '"cases":[{}]'}]
            assert tools.patch(action)['status'] == 'requires_arbitration'
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', ['contract', 'transaction', 'request', 'mode'])
async def test_new_repair_rejects_unapproved_or_mismatched_entry(tmp_path, invalid):
    _, payload, transaction, bus, brain = candidate(tmp_path)
    if invalid in {'contract', 'transaction'}:
        payload.pop('contract_revision' if invalid == 'contract' else '_transaction')
    elif invalid == 'request':
        payload['user_request'] = 'Another request'
    verify = AsyncMock()
    try:
        with brain.execution_scope(payload), pytest.raises(ValueError):
            await repair_project(brain, payload, mode='existing' if invalid == 'mode' else 'new',
                                 diagnose=AsyncMock(), verify=verify)
        verify.assert_not_awaited()
        assert not brain.llm_provider.calls
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('defect', ['value', 'syntax', 'missing_file'])
async def test_new_python_uses_real_execution_tests_and_linked_evidence(tmp_path, monkeypatch, defect):
    import sys
    target, payload, transaction, bus, brain = candidate(tmp_path,
        [{'type': 'read', 'path': 'main.py'}, edit()])
    action_provider = brain.llm_provider
    if defect == 'syntax':
        source = 'VALUE = (\nprint(VALUE)\n'
        target.file('main.py').write_text(source)
        action_provider.actions = iter([{'type': 'read', 'path': 'main.py'},
            {'type': 'patch', 'path': 'main.py', 'sha256': digest(source),
             'edits': [{'old': 'VALUE = (', 'new': 'VALUE = 2'}]}])
    elif defect == 'missing_file':
        payload['all_files'].append({'path': 'helper.py'})
        action_provider.actions = iter([{'type': 'patch', 'path': 'helper.py', 'sha256': digest(''),
            'edits': [{'old': '', 'new': 'UNUSED = 1\n'}]}, {'type': 'read', 'path': 'main.py'}, edit()])

    async def respond(**kwargs):
        if 'independent acceptance reviewer' in kwargs['messages'][0]['content']:
            from bigbrain.llm.usage import UsageRecord, get_tracker
            get_tracker().record(UsageRecord(model_id='offline', provider='test', input_tokens=20,
                                            output_tokens=20, total_tokens=40))
            context = json.loads(kwargs['messages'][1]['content'])
            assert not context.get('baseline_sources')
            return json.dumps({'decision': 'pass', 'contradictions': [], 'coverage': [{
                'criterion_id': '0', 'tests': context['passing_tests'],
                'sources': ['main.py', 'test_value.py'], 'reason': 'Real assertion checks VALUE equals two'}]})
        return await Actions.chat_complete(action_provider, **kwargs)

    action_provider.chat_complete = respond
    monkeypatch.setattr(brain, '_setup_project_venv', AsyncMock(return_value=Path(sys.executable)))
    brain.maintenance_diagnose = AsyncMock(side_effect=AssertionError('Creation must start with delivery gate'))
    original_tests = target.file('test_value.py').read_bytes()
    try:
        result = await brain.handle_task(BusMessage(type=MessageType.TASK, source='orchestrator', target=brain.name, payload=payload))
        assert result['success'], result
        assert result['stdout'].strip() == '2'
        assert result['repair']['repair_rounds'] == (2 if defect == 'missing_file' else 1)
        assert result['repair']['changed_files'] == (['helper.py', 'main.py'] if defect == 'missing_file' else ['main.py'])
        assert target.file('test_value.py').read_bytes() == original_tests
        rows = [row for row in result['repair']['actions'] if row['type'] == 'verify']
        assert len(rows) == (3 if defect == 'missing_file' else 2)
        repo = default_repository()
        initial = json.loads(repo.get_artifact(rows[0]['artifact_sha256']))
        previous = json.loads(repo.get_artifact(rows[-2]['artifact_sha256']))
        first_id = previous['verification']['run_id']
        final = repo.load_manifest(result['verification']['run_id'])
        assert final.parent_run_id == first_id
        assert final.metadata['attempt'] == len(rows)
        if defect in {'syntax', 'missing_file'}:
            assert initial['verification']['failures'][0]['stage'] == ('syntax' if defect == 'syntax' else 'contracts')
        brain.maintenance_diagnose.assert_not_awaited()
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_new_project_environment_failure_keeps_evidence_and_never_edits(tmp_path, monkeypatch):
    target, payload, transaction, bus, brain = candidate(tmp_path)
    monkeypatch.setattr(brain, '_setup_project_venv', AsyncMock(side_effect=OSError('Interpreter unavailable')))
    try:
        result = await brain.handle_task(BusMessage(type=MessageType.TASK, source='orchestrator', target=brain.name, payload=payload))
        assert result['maintenance_status'] == 'requires_arbitration'
        assert result['verification']['failures'][0]['details']['cause'] == 'environment_blocked'
        assert default_repository().load_manifest(result['verification']['run_id']) is not None
        assert not brain.llm_provider.calls
        assert target.file('main.py').read_text().startswith('VALUE = 1')
    finally:
        transaction.finish()
        await bus.close()
