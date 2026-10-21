"""Cross-layer regressions: real bus envelopes, successive revisions, diagnosis."""
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.bus.results import result_data
from bigbrain.brains.python_brain import PythonBrain
from bigbrain.execution_target import ExecutionTarget
from bigbrain.project_inspection import inspect_project, diagnose_project, digest
from bigbrain.orchestrator.architect import ArchitectPhase
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, TaskPlan, SubTask, TaskStatus


def project(tmp_path, files):
    root = tmp_path / 'workspace'
    directory = root / 'sandbox' / 'example'
    directory.mkdir(parents=True)
    for path, content in files.items():
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    (directory / '.project.json').write_text('{"entry_point":"main.py"}')
    return ExecutionTarget('existing', 'sandbox/example', str(root)).prepare()


def test_transport_failure_cannot_be_hidden_by_nested_success():
    assert result_data({'success': False, 'error': 'transport failed', 'data': {'success': True}})['success'] is False
    assert result_data({'success': True, 'data': {'success': False, 'error': 'tests failed'}})['error'] == 'tests failed'
    assert result_data({'stdout': 'legacy'}) == {'stdout': 'legacy'}


@pytest.mark.asyncio
async def test_real_result_handler_and_next_worker_receive_current_source(tmp_path):
    target = project(tmp_path, {'calc.py': 'VALUE = 1\n', 'main.py': 'from calc import VALUE\nprint(VALUE)\n'})
    baseline = inspect_project(target)
    bus = MessageBus(tmp_path / 'logs', auth=None)
    orch = WorkspaceOrchestrator('default', bus, llm_provider=AsyncMock())
    orch._execute_ready_subtasks = AsyncMock()
    orch._check_plan_completion = AsyncMock()
    first = SubTask('p_s0', 'Modify calc', 'python_brain', {}, status=TaskStatus.RUNNING)
    first._dispatch_msg_id = 'dispatch'
    second = SubTask('p_s1', 'Modify main', 'python_brain', {}, dependencies={'p_s0'})
    plan = TaskPlan('p', BusMessage(type=MessageType.TASK, source='front_brain', target=orch.name),
                    subtasks=[first, second], status=TaskStatus.RUNNING)
    orch.task_plans['p'] = plan
    orch.active_subtasks['dispatch'] = 'p'
    new_source = 'VALUE = 2\n'
    (target.directory / 'calc.py').write_text(new_source)
    # Exactly the envelope BaseBrain emits, handled through the real receiver.
    await orch._handle_task_result(BusMessage(type=MessageType.RESULT, source='python_brain', target=orch.name,
        reply_to='dispatch', payload={'success': True, 'data': {'success': True, 'file_path': 'calc.py',
        'file_content': new_source, 'source_sha256': digest(new_source)}}))
    payload = {'file_path': 'main.py', 'dependencies': ['calc.py'],
        '_existing_source': baseline['sources']['main.py'],
        '_existing_dependencies': {'calc.py': {'file_content': 'VALUE = 1\n'}},
        '_execution_target': target.to_payload()}
    resolved = await orch._resolve_payload_references(payload, plan)
    assert resolved['upstream_context']['calc.py']['file_content'] == new_source
    provider = AsyncMock()
    async def patch(**kwargs):
        data = json.loads(kwargs['messages'][-1]['content'].split('\n', 1)[1])
        assert data['dependencies']['calc.py'] == new_source
        return json.dumps({'edits': [{'old': 'print(VALUE)', 'new': 'print(VALUE + 1)'}]})
    provider.chat_complete.side_effect = patch
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    with brain.execution_scope(resolved):
        result = await brain._write_project_file(resolved)
    assert result['dependency_versions'] == {'calc.py': digest(new_source)}
    orch._compact_plan_context(plan)
    assert first.result['file_content'] == new_source
    await bus.close()


@pytest.mark.asyncio
async def test_dependency_changes_while_llm_works_fail_before_write(tmp_path):
    target = project(tmp_path, {'calc.py': 'VALUE = 1\n', 'main.py': 'print(1)\n'})
    sources = inspect_project(target)['sources']
    bus = MessageBus(tmp_path / 'logs', auth=None)
    provider = AsyncMock()
    async def patch(**kwargs):
        (target.directory / 'calc.py').write_text('VALUE = 3\n')
        return json.dumps({'edits': [{'old': 'print(1)', 'new': 'print(2)'}]})
    provider.chat_complete.side_effect = patch
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    payload = {'file_path': 'main.py', '_existing_source': sources['main.py'],
        'dependencies': ['calc.py'], '_existing_dependencies': {'calc.py': {'file_content': 'VALUE = 1\n'}},
        '_execution_target': target.to_payload()}
    with brain.execution_scope(payload), pytest.raises(ValueError, match='dependency changed'):
        await brain._write_project_file(payload)
    assert (target.directory / 'main.py').read_text() == 'print(1)\n'
    await bus.close()


@pytest.mark.asyncio
async def test_initial_diagnostic_reports_failures_and_preserves_source(tmp_path):
    import venv
    import sys
    import sysconfig
    target = project(tmp_path, {'main.py': 'VALUE = 1\n',
        'tests/test_value.py': 'from main import VALUE\ndef test_value():\n    assert VALUE == 2\n'})
    venv.EnvBuilder(with_pip=False, system_site_packages=True).create(target.directory / '.venv')
    packages = target.directory / '.venv' / 'lib' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages'
    (packages / 'test-tools.pth').write_text(sysconfig.get_path('purelib') + '\n')
    inspection = inspect_project(target)
    diagnosis = await diagnose_project(target, inspection)
    assert diagnosis['tests']['status'] == 'failed'
    assert any('test_value' in case for case in diagnosis['tests']['failed_cases'])
    assert 'assert 1 == 2' in diagnosis['tests']['diagnostic_output']
    assert inspect_project(target)['sources'] == inspection['sources']


@pytest.mark.asyncio
async def test_test_changes_require_explicit_decision_before_execution(tmp_path):
    target = project(tmp_path, {'main.py': 'print(1)\n', 'tests/test_value.py': 'assert True\n'})
    provider = AsyncMock()
    raw = {'project_name': 'example', 'acceptance_contracts': ['Print one'],
        'file_specs': [{'path': 'main.py', 'operation': 'keep'},
                       {'path': 'tests/test_value.py', 'operation': 'modify'}]}
    provider.chat_complete.return_value = json.dumps(raw)
    architect = ArchitectPhase(llm_provider=provider)
    with pytest.raises(ValueError, match='test_changes'):
        await architect.design('Repair existing project', existing_project=inspect_project(target))
    raw['test_changes'] = [{'path': 'tests/test_value.py', 'reason': 'Wrong expectation',
        'expected_behavior': 'Print one', 'authority': 'User requirement'}]
    provider.chat_complete.return_value = json.dumps(raw)
    spec = await architect.design('Repair existing project', existing_project=inspect_project(target))
    assert spec.test_changes == raw['test_changes']
    raw['unresolved_conflicts'] = ['Cannot establish intended behaviour']
    provider.chat_complete.return_value = json.dumps(raw)
    with pytest.raises(ValueError, match='clarification required'):
        await architect.design('Repair existing project', existing_project=inspect_project(target))
    # A semantic conflict must not be "fixed" by asking the model to erase it.
    assert provider.chat_complete.await_count == 4


@pytest.mark.asyncio
async def test_repair_receives_approved_contract_and_first_failure_not_only_tail(tmp_path):
    target = project(tmp_path, {'main.py': 'print(1)\n', 'tests/test_main.py': 'assert True\n'})
    bus = MessageBus(tmp_path / 'logs', auth=None)
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps({'edits': []})
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    brain.send_progress = AsyncMock()
    failure = [{'stage': 'tests', 'details': {'output_tail': 'last failure',
        'diagnostic_output': 'FIRST FAILURE\n' + 'x' * 3000 + '\nlast failure'}}]
    assert not await brain._repair_project_sources(target.directory,
        {'main.py': 'print(1)\n', 'tests/test_main.py': 'assert True\n'}, 'Repair', failure,
        acceptance_contracts=['Print one; do not change meaning'],
        baseline={'tests': {'status': 'failed', 'failed_cases': ['old failure']}})
    prompt = provider.chat_complete.call_args.kwargs['messages'][0]['content']
    assert 'FIRST FAILURE' in prompt
    assert 'Print one; do not change meaning' in prompt
    assert 'old failure' in prompt
    await bus.close()


@pytest.mark.asyncio
async def test_gate_uses_pinned_approved_revision_not_later_proposal(tmp_path):
    from bigbrain.verification.evidence import EvidenceRepository
    from bigbrain.verification.gate import RunGate
    repo = EvidenceRepository(tmp_path / 'evidence')
    gate = RunGate(repo)
    request = 'Print one'
    spec = gate.build_spec(request, ['main.py'])
    repo.save_spec(spec)
    approved = repo.approve_spec(spec.design_id, plan_id='p', decision='approved')
    newer = approved.model_copy(update={'revision': approved.revision + 1,
        'contracts': ['Different later contract'], 'metadata': {}})
    repo.save_spec(newer)
    (tmp_path / 'main.py').write_text('print(1)\n')
    manifest, verdict = await gate.evaluate_attempt(user_request=request, code='print(1)\n',
        execution={'exit_code': 0, 'stdout': '1\n'}, work_dir=tmp_path,
        requested_files=['main.py'], filename='main.py',
        contract_revision={'design_id': approved.design_id, 'revision': approved.revision})
    assert manifest.design_revision == approved.revision
    with pytest.raises(ValueError, match='unavailable'):
        await gate.evaluate_attempt(user_request=request, code='print(1)\n',
            execution={'exit_code': 0}, work_dir=tmp_path,
            contract_revision={'design_id': newer.design_id, 'revision': newer.revision})
