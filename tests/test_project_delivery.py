"""Delivery is a runtime decision, exercised with real files and Python tests."""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bigbrain.brains.python_brain import PythonBrain
from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.execution_target import ExecutionTarget
from bigbrain.front.front_brain import FrontBrain
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, SubTask, TaskPlan, TaskStatus
from bigbrain.project_inspection import digest
from bigbrain.project_transaction import ProjectTransaction
from bigbrain.verification.delivery import validate
from bigbrain.verification.evidence import default_repository
from bigbrain.verification.gate import RunGate


async def verified_project(tmp_path, monkeypatch, *, exhaust_budget=False, via_generation=False):
    root = tmp_path / 'workspace'
    root.mkdir()
    target = ExecutionTarget('new', 'calculator', str(root)).prepare()
    target.file('main.py').write_text(f'VALUE = {0 if exhaust_budget else 2}\nprint(VALUE)\n')
    target.file('test_main.py').write_text('from main import VALUE\ndef test_value():\n    assert VALUE == 2\n')
    target.file('example.csv').write_text('value\n2\n')
    repo = default_repository()
    spec = RunGate(repo).build_spec('Return and print two', ['main.py', 'test_main.py'])
    spec.metadata.update(business_criteria=['VALUE equals two'], execution_target=target.public(),
        delivery={'deliverable_type': 'python', 'executable': True, 'entry_point': 'main.py', 'web_stack': 'static'})
    repo.save_spec(spec)
    spec = repo.approve_spec(spec.design_id, plan_id='delivery')
    transaction = ProjectTransaction.begin(target, ['main.py'] if via_generation else [])
    payload = {'type': 'assemble_and_run', 'user_request': spec.user_request, 'project_name': 'calculator',
        'entry_point': 'main.py', 'deliverable_type': 'python',
        'all_files': [{'path': p} for p in ('main.py', 'test_main.py', 'example.csv')],
        'contract_revision': {'design_id': spec.design_id, 'revision': spec.revision},
        '_execution_target': target.to_payload(), '_transaction': str(transaction.journal)}
    actions = []
    for before, after in [(0, 1), (1, 3), (3, 4)]:
        actions.extend([{'type': 'read', 'path': 'main.py'}, {'type': 'patch', 'path': 'main.py',
            'sha256': digest(f'VALUE = {before}\nprint(VALUE)\n'),
            'edits': [{'old': f'VALUE = {before}', 'new': f'VALUE = {after}'}]}])
    async def review(**kwargs):
        if exhaust_budget:
            assert 'independent acceptance reviewer' not in kwargs['messages'][0]['content']
            return json.dumps({'action': actions.pop(0), 'notebook': 'Fix reproduced test failure'})
        from bigbrain.llm.usage import UsageRecord, get_tracker
        get_tracker().record(UsageRecord(model_id='offline', provider='test', input_tokens=20, output_tokens=20, total_tokens=40))
        assert 'independent acceptance reviewer' in kwargs['messages'][0]['content']
        context = json.loads(kwargs['messages'][1]['content'])
        return json.dumps({'decision': 'pass', 'contradictions': [], 'coverage': [{
            'criterion_id': '0', 'tests': context['passing_tests'], 'sources': ['main.py', 'test_main.py'],
            'reason': 'Executed test asserts VALUE equals two'}]})
    bus = MessageBus(tmp_path / 'logs', auth=None)
    provider = AsyncMock()
    provider.chat_complete.side_effect = review
    brain = PythonBrain('python', bus, work_dir=root, llm_provider=provider)
    monkeypatch.setattr(brain, '_setup_project_venv', AsyncMock(return_value=Path(sys.executable)))
    if via_generation:
        payload['type'] = 'generate_and_execute'
        monkeypatch.setattr(brain, '_generate_initial_code', AsyncMock(return_value=target.file('main.py').read_text()))
        monkeypatch.setattr(brain, '_execute_code', AsyncMock(side_effect=AssertionError('Legacy stdout path bypasses project checks')))
        monkeypatch.setattr(brain, '_fix_code', AsyncMock(side_effect=AssertionError('Use shared repair, not legacy replacement')))
    result = await brain.handle_task(BusMessage(type=MessageType.TASK, source='orchestrator', target=brain.name, payload=payload))
    assert result['success'] is not exhaust_budget, result
    if via_generation:
        brain._generate_initial_code.assert_awaited_once()
        brain._execute_code.assert_not_awaited()
        brain._fix_code.assert_not_awaited()
    return target, payload, result, transaction, bus


def completed_plan(target, payload, result, transaction, bus):
    original = BusMessage(type=MessageType.TASK, source='front_brain', target='orchestrator', payload={'session_id': 's'})
    plan = TaskPlan('delivery', original, subtasks=[SubTask('assembly', 'Assemble', 'python', payload,
        status=TaskStatus.COMPLETE, result=result)], status=TaskStatus.RUNNING,
        execution_target=target, transaction=str(transaction.journal))
    orch = WorkspaceOrchestrator('default', bus)
    orch._extract_learnings = AsyncMock()
    bus.send_result = AsyncMock()
    bus.broadcast_event = AsyncMock()
    return plan, orch


@pytest.mark.asyncio
async def test_verified_receipt_is_required_before_commit_and_terminal_success(tmp_path, monkeypatch):
    target, payload, result, transaction, bus = await verified_project(tmp_path, monkeypatch)
    plan, orch = completed_plan(target, payload, result, transaction, bus)
    try:
        await orch._check_plan_completion(plan)
        assert plan.status == TaskStatus.COMPLETE
        assert plan.result['delivery_status'] == 'ready' and plan.result['verified']
        assert plan.result['transaction']['state'] == 'committed'
        assert bus.broadcast_event.call_args.kwargs['event_type'] == 'task.complete'
        assert bus.broadcast_event.call_args.kwargs['payload']['runnable']
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('tamper', ['receipt', 'source', 'data', 'entry', 'contract', 'tests', 'criteria', 'interaction'])
async def test_unproved_or_stale_success_never_becomes_project_delivery(tmp_path, monkeypatch, tamper):
    target, payload, result, transaction, bus = await verified_project(tmp_path, monkeypatch)
    if tamper == 'receipt':
        result.pop('delivery_receipt')
    elif tamper in {'source', 'data', 'entry'}:
        path = 'example.csv' if tamper == 'data' else 'main.py'
        if tamper == 'entry':
            target.file(path).unlink()
        else:
            target.file(path).write_text('VALUE = 99\n')
    elif tamper == 'contract':
        payload['contract_revision'] = {**payload['contract_revision'], 'revision': 999}
    elif tamper == 'interaction':
        payload['interaction_mode'] = 'service'
    else:
        # A synthetic incomplete manifest tests the guard, not program validity.
        # Even a manifest whose remaining stages pass must contain all gates.
        repo = default_repository()
        run = repo.load_manifest(result['verification']['run_id'])
        omitted = 'tests' if tamper == 'tests' else 'semantics'
        copy = run.model_copy(deep=True, update={'run_id': 'run-incomplete',
            'stages': [s for s in run.stages if s.name != omitted]})
        repo.save_manifest(copy)
        receipt = json.loads(repo.get_artifact(result['delivery_receipt']))
        receipt['run_id'] = copy.run_id
        artifact = repo.put_artifact(json.dumps(receipt).encode(), name='synthetic-receipt.json', media_type='application/json')
        result['delivery_receipt'] = artifact.sha256
        result['verification']['run_id'] = copy.run_id
    plan, orch = completed_plan(target, payload, result, transaction, bus)
    try:
        await orch._check_plan_completion(plan)
        assert plan.status == TaskStatus.FAILED
        assert plan.result['delivery_status'] == 'incomplete'
        assert not plan.result['runnable'] and not plan.result['verified']
        assert plan.result['transaction']['state'] in {'rolled_back', 'conflict'}
        assert bus.broadcast_event.call_args.kwargs['event_type'] == 'task.failed'
        assert bus.broadcast_event.call_args.kwargs['payload']['delivery_status'] == 'incomplete'
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_file_generation_schedules_validation_instead_of_declaring_done(tmp_path, monkeypatch):
    target, payload, result, transaction, bus = await verified_project(tmp_path, monkeypatch)
    payload = {**payload, 'type': 'write_project_file', 'file_path': 'main.py'}
    plan, orch = completed_plan(target, payload, {'success': True, 'file_path': 'main.py'}, transaction, bus)
    orch._execute_ready_subtasks = AsyncMock()
    try:
        await orch._check_plan_completion(plan)
        assert plan.status == TaskStatus.RUNNING
        assert plan.subtasks[-1].payload['type'] == 'assemble_and_run'
        assert plan.subtasks[-1].dependencies == {'assembly'}
        bus.send_result.assert_not_awaited()
        assert json.loads(transaction.journal.read_text())['state'] == 'open'
        orch._execute_ready_subtasks.assert_awaited_once_with(plan)
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_front_brain_reports_incomplete_without_a_ready_summary(tmp_path):
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = FrontBrain(bus)
    brain._emit_chat_message = AsyncMock()
    brain._summarize_result = AsyncMock(return_value='ready')
    try:
        await brain._handle_task_result(BusMessage(type=MessageType.RESULT, source='orchestrator', target='front',
            payload={'success': False, 'delivery_status': 'incomplete', 'error': 'Repair budget exhausted', 'session_id': 's'}))
        text = brain._emit_chat_message.call_args.args[1]
        assert 'Projet incomplet' in text and 'non validé' in text
        assert 'Repair budget exhausted' in text
        brain._summarize_result.assert_not_awaited()
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_exhausted_real_repair_is_incomplete_with_tests_and_contract_intact(tmp_path, monkeypatch):
    target, payload, result, transaction, bus = await verified_project(tmp_path, monkeypatch, exhaust_budget=True)
    assert result['delivery_status'] == 'incomplete'
    assert result['maintenance_status'] == 'repair_budget_exhausted'
    assert result['maintenance']['repair_rounds'] == 2
    assert result['verification']['verdict'] == 'failed'
    assert 'assert VALUE == 2' in target.file('test_main.py').read_text()
    ref = payload['contract_revision']
    approved = default_repository().load_spec(ref['design_id'], ref['revision'])
    assert approved.metadata['business_criteria'] == ['VALUE equals two']
    plan, orch = completed_plan(target, payload, result, transaction, bus)
    plan.subtasks[0].status = TaskStatus.FAILED
    plan.subtasks[0].error = result['error']
    try:
        await orch._check_plan_completion(plan)
        assert plan.result['delivery_status'] == 'incomplete' and not plan.result['runnable']
        assert plan.result['transaction']['state'] == 'rolled_back'
        assert plan.result['failed_subtasks'][0]['verification']['run_id'] == result['verification']['run_id']
        assert bus.broadcast_event.call_args.kwargs['event_type'] == 'task.failed'
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('exhaust', [False, True])
async def test_bound_script_generation_also_requires_project_delivery(tmp_path, monkeypatch, exhaust):
    target, payload, result, transaction, bus = await verified_project(
        tmp_path, monkeypatch, exhaust_budget=exhaust, via_generation=True)
    plan, orch = completed_plan(target, payload, result, transaction, bus)
    if exhaust:
        plan.subtasks[0].status = TaskStatus.FAILED
        plan.subtasks[0].error = result['error']
    try:
        await orch._check_plan_completion(plan)
        assert plan.status == (TaskStatus.FAILED if exhaust else TaskStatus.COMPLETE)
        assert plan.result['delivery_status'] == ('incomplete' if exhaust else 'ready')
    finally:
        transaction.finish()
        await bus.close()
