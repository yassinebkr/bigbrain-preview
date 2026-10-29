import json
from pathlib import Path
import sys
import sysconfig
from unittest.mock import AsyncMock
import venv

import pytest

from bigbrain.execution_target import ExecutionTarget
from bigbrain.project_transaction import ProjectTransaction, active_transaction, write_text, remove
from bigbrain.verification.executors import stage_tests
from bigbrain.verification.semantics import review_semantics


def project(tmp_path):
    root = tmp_path / 'workspace'
    folder = root / 'sandbox' / 'sample'
    folder.mkdir(parents=True)
    (folder / 'main.py').write_text('print(1)\n')
    (folder / 'helper.py').write_text('VALUE = 1\n')
    (folder / '.project.json').write_text('{"entry_point":"main.py","verified":true}')
    return ExecutionTarget('existing', 'sandbox/sample', str(root)).prepare()


def test_rollback_restores_multiple_files_manifest_and_removes_new_files(tmp_path):
    target = project(tmp_path)
    before = {p.name: p.read_bytes() for p in target.directory.iterdir()}
    transaction = ProjectTransaction.begin(target, ['main.py', 'helper.py', 'new/file.py'])
    token = active_transaction.set(str(transaction.journal))
    try:
        write_text(target, 'main.py', 'print(2)\n')
        write_text(target, 'helper.py', 'VALUE = 2\n')
        write_text(target, 'new/file.py', 'NEW = True\n')
        remove(target, '.project.json')
    finally:
        active_transaction.reset(token)
    # Re-open a persisted journal: recovery does not depend on process memory.
    outcome = ProjectTransaction(transaction.journal).finish()
    assert outcome['state'] == 'rolled_back'
    assert {p.name: p.read_bytes() for p in target.directory.iterdir()
            if p.name != '.bigbrain-recovery'} == before
    # Retained native objects remain available for explicit recovery resolution.
    recovery = target.directory / '.bigbrain-recovery'
    assert recovery.is_dir()
    assert b'print(2)\n' in [p.read_bytes() for p in recovery.rglob('*') if p.is_file()]
    with pytest.raises(ValueError, match='closed'):
        transaction.write(target, 'main.py', b'late worker')


def test_rollback_preserves_user_changes_and_restores_uncontested_files(tmp_path):
    target = project(tmp_path)
    transaction = ProjectTransaction.begin(target, ['main.py', 'helper.py'])
    transaction.write(target, 'main.py', b'print(2)\n')
    transaction.write(target, 'helper.py', b'VALUE = 2\n')
    (target.directory / 'main.py').write_text('# user concurrent edit\n')
    outcome = transaction.finish()
    assert outcome['state'] == 'conflict'
    assert outcome['conflicts'] == ['main.py']
    assert (target.directory / 'main.py').read_text() == '# user concurrent edit\n'
    assert (target.directory / 'helper.py').read_text() == 'VALUE = 1\n'
    with pytest.raises(ValueError, match='recovery required'):
        ProjectTransaction.begin(target, ['helper.py'])


def test_transaction_commit_and_unapproved_path_guard(tmp_path):
    target = project(tmp_path)
    transaction = ProjectTransaction.begin(target, ['main.py'])
    with pytest.raises(ValueError, match='write set'):
        transaction.write(target, 'helper.py', b'invalid')
    with pytest.raises(ValueError, match='recovery required'):
        ProjectTransaction.begin(target, ['main.py'])
    transaction.write(target, 'main.py', b'print(2)\n')
    assert transaction.finish(commit=True)['state'] == 'committed'
    assert (target.directory / 'main.py').read_text() == 'print(2)\n'
    ProjectTransaction.begin(target, ['helper.py']).finish()


@pytest.mark.asyncio
async def test_tests_use_real_project_environment_with_project_only_dependency(tmp_path):
    env = tmp_path / '.venv'
    venv.EnvBuilder(with_pip=False, system_site_packages=True).create(env)
    packages = env / 'lib' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages'
    # Provision pytest/dependencies without network in this isolated test venv.
    # Nested venv system_site_packages refers to base Python, not BigBrain's venv.
    (packages / 'test-tools.pth').write_text(sysconfig.get_path('purelib') + '\n')
    (packages / 'project_only_dependency.py').write_text('VALUE = 42\n')
    (tmp_path / 'test_project.py').write_text(
        'import project_only_dependency\nimport sys\n'
        f'def test_local():\n    assert project_only_dependency.VALUE == 42\n    assert sys.prefix == {str(env)!r}\n')
    result = await stage_tests(tmp_path, python=env / 'bin/python')
    assert result.status == 'passed', result.details
    assert result.details['environment']['prefix'] == str(env)
    assert result.details['passed_cases'] == ['test_project.py::test_local']


@pytest.mark.asyncio
async def test_no_fallback_when_project_has_no_pytest(tmp_path):
    env = tmp_path / '.venv'
    venv.EnvBuilder(with_pip=False).create(env)
    (tmp_path / 'test_project.py').write_text('def test_local():\n    assert True\n')
    result = await stage_tests(tmp_path, python=env / 'bin/python')
    assert result.status == 'inconclusive'
    assert result.details['environment']['prefix'] == str(env)
    assert result.details['environment']['pytest'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['valid', 'invented_test', 'missing_criterion', 'contradiction', 'uncertain', 'invalid_json'])
async def test_semantic_gate_requires_evidence_for_every_criterion(case):
    review = {'decision': 'pass', 'contradictions': [], 'coverage': [
        {'criterion_id': '0', 'tests': ['test_calc.py::test_mean'], 'reason': 'Checks actual input [1,3] yields 2, not a canned summary'}]}
    if case == 'invented_test': review['coverage'][0]['tests'] = ['imaginary_test']
    if case == 'missing_criterion': review['coverage'] = []
    if case == 'contradiction': review['contradictions'] = ['Test disagrees with approved definition']
    if case == 'uncertain': review['decision'] = 'needs_arbitration'
    provider = AsyncMock()
    provider.chat_complete.return_value = 'not json' if case == 'invalid_json' else json.dumps(review)
    result = await review_semantics(provider, request='Compute arithmetic mean',
        contracts=['Compute mean of provided values'], sources={'calc.py': 'def mean(values): return sum(values)/len(values)'},
        tests={'status': 'passed', 'passed_cases': ['test_calc.py::test_mean']})
    assert result.status == ('passed' if case == 'valid' else 'inconclusive')
    if case != 'valid': assert result.details['requires_arbitration'] is True


@pytest.mark.asyncio
async def test_semantic_gate_refuses_missing_actual_test_evidence():
    provider = AsyncMock()
    result = await review_semantics(provider, request='Compute mean', contracts=['Compute mean'],
        sources={'calc.py': 'pass'}, tests={'status': 'passed', 'passed_cases': []})
    assert result.status == 'inconclusive'
    provider.chat_complete.assert_not_called()


@pytest.mark.asyncio
async def test_real_worker_patch_is_rolled_back_when_later_plan_step_fails(tmp_path):
    from bigbrain.bus.bus import MessageBus
    from bigbrain.bus.message import BusMessage, MessageType
    from bigbrain.brains.python_brain import PythonBrain
    from bigbrain.project_inspection import inspect_project
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, TaskPlan, SubTask, TaskStatus
    target = project(tmp_path)
    snapshot = inspect_project(target)
    transaction = ProjectTransaction.begin(target, ['helper.py'])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps({'edits': [{'old': 'VALUE = 1', 'new': 'VALUE = 2'}]})
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    payload = {'file_path': 'helper.py', '_existing_source': snapshot['sources']['helper.py'],
        '_execution_target': target.to_payload(), '_transaction': str(transaction.journal)}
    with brain.execution_scope(payload):
        await brain._write_project_file(payload)
    assert (target.directory / 'helper.py').read_text() == 'VALUE = 2\n'
    orch = WorkspaceOrchestrator('default', bus, llm_provider=provider)
    orch._extract_learnings = AsyncMock()
    plan = TaskPlan('p', BusMessage(type=MessageType.TASK, source='front_brain', target=orch.name),
        subtasks=[SubTask('s1', 'Modify helper', 'python', {}, status=TaskStatus.COMPLETE),
                  SubTask('s2', 'Verify', 'python', {}, status=TaskStatus.FAILED, error='Tests failed')],
        status=TaskStatus.RUNNING, execution_target=target, transaction=str(transaction.journal))
    await orch._check_plan_completion(plan)
    assert plan.status == TaskStatus.FAILED
    assert plan.result['transaction']['state'] == 'rolled_back'
    assert (target.directory / 'helper.py').read_text() == 'VALUE = 1\n'
    await bus.close()


def test_crashed_owner_is_recovered_before_next_project_run(tmp_path, monkeypatch):
    target = project(tmp_path)
    previous = ProjectTransaction.begin(target, ['main.py'])
    previous.write(target, 'main.py', b'print(2)\n')
    def dead_owner(pid, signal):
        raise ProcessLookupError()
    monkeypatch.setattr('bigbrain.project_transaction.os.kill', dead_owner)
    next_transaction = ProjectTransaction.begin(target, ['helper.py'])
    assert (target.directory / 'main.py').read_text() == 'print(1)\n'
    assert json.loads(previous.journal.read_text())['state'] == 'rolled_back'
    next_transaction.finish()


@pytest.mark.asyncio
async def test_semantic_contradiction_blocks_delivery_and_is_immutable_evidence(tmp_path):
    from bigbrain.verification.evidence import EvidenceRepository
    from bigbrain.verification.gate import RunGate
    repo = EvidenceRepository(tmp_path / 'evidence')
    gate = RunGate(repo)
    spec = gate.build_spec('Compute mean', ['main.py'])
    spec.metadata['business_criteria'] = ['Compute actual arithmetic mean']
    repo.save_spec(spec)
    approved = repo.approve_spec(spec.design_id, plan_id='p')
    (tmp_path / 'main.py').write_text('print(2)\n')
    (tmp_path / 'test_mean.py').write_text('def test_mean():\n    assert 2 == 2\n')
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps({'decision': 'needs_arbitration',
        'contradictions': ['Test asserts a constant, not actual input processing'], 'coverage': []})
    manifest, verdict = await gate.evaluate_attempt(user_request='Compute mean', code='print(2)\n',
        execution={'exit_code': 0, 'stdout': '2\n'}, work_dir=tmp_path,
        contract_revision={'design_id': approved.design_id, 'revision': approved.revision},
        semantic_provider=provider, semantic_sources={'main.py': 'print(2)\n', 'test_mean.py': (tmp_path / 'test_mean.py').read_text()})
    assert next(stage for stage in manifest.stages if stage.name == 'tests').status == 'passed'
    assert verdict == 'inconclusive'
    provider.chat_complete.assert_awaited_once()
    assert manifest.stages[-1].details['requires_arbitration'] is True
    assert repo.load_manifest(manifest.run_id).stages[-1].details == manifest.stages[-1].details


@pytest.mark.asyncio
async def test_real_assembly_failure_rolls_back_sources_and_original_manifest(tmp_path, monkeypatch):
    from bigbrain.bus.bus import MessageBus
    from bigbrain.brains.python_brain import PythonBrain
    target = project(tmp_path)
    original_manifest = (target.directory / '.project.json').read_bytes()
    (target.directory / 'test_main.py').write_text('def test_failure():\n    assert False\n')
    transaction = ProjectTransaction.begin(target, ['main.py'])
    transaction.write(target, 'main.py', b'print(2)\n')
    bus = MessageBus(tmp_path / 'logs', auth=None)
    provider = AsyncMock()
    provider.chat_complete.return_value = '{"edits":[]}'
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    async def python(directory):
        return Path(sys.executable)
    monkeypatch.setattr(brain, '_setup_project_venv', python)
    payload = {'project_name': 'sample', 'entry_point': 'main.py', 'user_request': 'Repair program',
        'all_files': [{'path': 'main.py'}, {'path': 'test_main.py'}], '_editable_paths': ['main.py'],
        '_execution_target': target.to_payload(), '_transaction': str(transaction.journal)}
    with brain.execution_scope(payload):
        result = await brain._assemble_and_run(payload)
    assert result['success'] is False
    assert result['verification']['verdict'] == 'failed'
    assert not (target.directory / '.project.json').exists()
    assert transaction.finish()['state'] == 'rolled_back'
    assert (target.directory / '.project.json').read_bytes() == original_manifest
    assert (target.directory / 'main.py').read_text() == 'print(1)\n'
    await bus.close()


@pytest.mark.asyncio
async def test_failed_react_build_restores_previous_dist_and_kept_toolchain(tmp_path, monkeypatch):
    from bigbrain.brains.web_stack import REACT_FILES, build_react
    target = project(tmp_path)
    for path, content in REACT_FILES.items():
        (target.directory / path).write_text(content)
    (target.directory / 'dist').mkdir()
    (target.directory / 'dist/index.html').write_text('OLD VERIFIED BUILD')
    transaction = ProjectTransaction.begin(target, ['main.py'])
    async def command(project, argv):
        if argv[-1] == 'build':
            (project / 'dist').mkdir(exist_ok=True)
            (project / 'dist/index.html').write_text('FAILED PARTIAL BUILD')
            return {'status': 'failed', 'output': 'build failure'}
        return {'status': 'passed', 'output': ''}
    monkeypatch.setattr('bigbrain.brains.web_stack.command', command)
    token = active_transaction.set(str(transaction.journal))
    try:
        stages = await build_react(target.directory)
    finally:
        active_transaction.reset(token)
    assert stages[-1]['status'] == 'failed'
    assert transaction.finish()['state'] == 'rolled_back'
    assert (target.directory / 'dist/index.html').read_text() == 'OLD VERIFIED BUILD'
    assert all((target.directory / path).read_text() == text for path, text in REACT_FILES.items())
    retained = list(transaction.journal.parent.glob('*.dist-after-*'))
    assert len(retained) == 1
    assert (retained[0] / 'index.html').read_text() == 'FAILED PARTIAL BUILD'


@pytest.mark.asyncio
async def test_cancel_fences_writes_before_stopping_workers_then_restores(tmp_path):
    from bigbrain.bus.bus import MessageBus
    from bigbrain.bus.message import BusMessage, MessageType
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, TaskPlan, SubTask, TaskStatus
    target = project(tmp_path)
    transaction = ProjectTransaction.begin(target, ['main.py'])
    transaction.write(target, 'main.py', b'print(2)\n')
    bus = MessageBus(tmp_path / 'logs', auth=None)
    orch = WorkspaceOrchestrator('default', bus)
    worker = SubTask('s1', 'Modify', 'python_brain', {}, status=TaskStatus.RUNNING, assigned_brain='python_brain')
    worker._dispatch_msg_id = 'dispatch'
    plan = TaskPlan('p', BusMessage(type=MessageType.TASK, source='front_brain', target=orch.name),
        subtasks=[worker], status=TaskStatus.RUNNING, execution_target=target, transaction=str(transaction.journal))
    orch.task_plans['p'] = plan
    orch.active_subtasks['dispatch'] = 'p'
    async def cancel(message):
        if message.type != MessageType.CANCEL:
            return
        assert json.loads(transaction.journal.read_text())['state'] == 'cancelling'
        assert (target.directory / 'main.py').read_text() == 'print(2)\n'
        with pytest.raises(ValueError, match='closed'):
            transaction.write(target, 'main.py', b'late write')
    bus.send = AsyncMock(side_effect=cancel)
    await orch._cancel_task('p', 'soft')
    assert len([call for call in bus.send.call_args_list if call.args[0].type == MessageType.CANCEL]) == 1
    assert plan.rollback['state'] == 'rolled_back'
    assert (target.directory / 'main.py').read_text() == 'print(1)\n'
    await bus.close()


@pytest.mark.asyncio
async def test_approved_patch_execution_semantic_review_and_commit_end_to_end(tmp_path, monkeypatch):
    from bigbrain.bus.bus import MessageBus
    from bigbrain.brains.python_brain import PythonBrain
    from bigbrain.project_inspection import inspect_project
    from bigbrain.verification.evidence import default_repository
    from bigbrain.verification.gate import RunGate
    target = project(tmp_path)
    (target.directory / 'main.py').write_text('from helper import VALUE\nprint(VALUE)\n')
    (target.directory / 'test_helper.py').write_text('from helper import VALUE\ndef test_value():\n    assert VALUE == 2\n')
    snapshot = inspect_project(target)
    request = 'Print the actual helper value, which must be two'
    repo = default_repository()
    spec = RunGate(repo).build_spec(request, ['main.py', 'helper.py', 'test_helper.py'])
    spec.metadata['business_criteria'] = [request]
    repo.save_spec(spec)
    approved = repo.approve_spec(spec.design_id, plan_id='p')
    transaction = ProjectTransaction.begin(target, ['helper.py'])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    provider = AsyncMock()
    async def answer(**kwargs):
        if 'independent acceptance reviewer' in kwargs['messages'][0]['content']:
            data = json.loads(kwargs['messages'][1]['content'])
            assert data['sources']['helper.py'] == 'VALUE = 2\n'
            assert data['test_report']['status'] == 'passed'
            return json.dumps({'decision': 'pass', 'contradictions': [], 'coverage': [{
                'criterion_id': '0', 'tests': ['test_helper.py::test_value'],
                'reason': 'The test asserts imported VALUE == 2; entry point imports and prints that same value'}]})
        return '{"edits":[{"old":"VALUE = 1","new":"VALUE = 2"}]}'
    provider.chat_complete.side_effect = answer
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    async def python(directory):
        return Path(sys.executable)
    monkeypatch.setattr(brain, '_setup_project_venv', python)
    shared = {'_execution_target': target.to_payload(), '_transaction': str(transaction.journal),
        'user_request': request, 'contract_revision': {'design_id': approved.design_id, 'revision': approved.revision}}
    with brain.execution_scope({**shared, 'file_path': 'helper.py', '_existing_source': snapshot['sources']['helper.py']}):
        await brain._write_project_file({**shared, 'file_path': 'helper.py', '_existing_source': snapshot['sources']['helper.py']})
    payload = {**shared, 'project_name': 'sample', 'entry_point': 'main.py',
        'all_files': [{'path': p} for p in ('main.py', 'helper.py', 'test_helper.py')], '_editable_paths': ['helper.py']}
    with brain.execution_scope(payload):
        result = await brain._assemble_and_run(payload)
    assert result['success'] is True, result
    assert result['stdout'].strip() == '2'
    assert result['verification']['verdict'] == 'passed'
    assert result['verification']['stages'][-1] == {'name': 'semantics', 'status': 'passed'}
    assert transaction.finish(commit=True)['state'] == 'committed'
    assert (target.directory / 'helper.py').read_text() == 'VALUE = 2\n'
    await bus.close()


def test_modified_verified_build_conflicts_instead_of_overwriting_user_data(tmp_path):
    target = project(tmp_path)
    (target.directory / 'dist').mkdir()
    (target.directory / 'dist/index.html').write_text('OLD BUILD')
    transaction = ProjectTransaction.begin(target, ['main.py'])
    transaction.prepare_build_tree(target.directory)
    (target.directory / 'dist').mkdir()
    (target.directory / 'dist/index.html').write_text('NEW VERIFIED BUILD')
    transaction.seal_build_tree(target.directory)
    (target.directory / 'dist/index.html').write_text('USER EDIT AFTER VALIDATION')
    assert transaction.finish(commit=True)['state'] == 'conflict'
    assert transaction.finish()['state'] == 'conflict'
    assert (target.directory / 'dist/index.html').read_text() == 'USER EDIT AFTER VALIDATION'
    assert (transaction.journal.with_suffix('.dist-before') / 'index.html').read_text() == 'OLD BUILD'


def test_preview_refuses_open_or_conflicted_transactions(tmp_path):
    from bigbrain.project_transaction import assert_project_idle
    target = project(tmp_path)
    transaction = ProjectTransaction.begin(target, ['main.py'])
    with pytest.raises(ValueError, match='in progress'):
        assert_project_idle(Path(target.root), target.directory)
    transaction.finish()
    assert_project_idle(Path(target.root), target.directory)


@pytest.mark.asyncio
async def test_status_like_text_cannot_forge_executed_test_evidence(tmp_path):
    (tmp_path / 'test_real.py').write_text('def test_real():\n    assert True\n')
    (tmp_path / 'conftest.py').write_text(
        'def pytest_terminal_summary(terminalreporter):\n'
        '    terminalreporter.write_line("PASSED invented.py::test_fake")\n'
        '    terminalreporter.write_line("FAILED invented.py::test_other")\n')
    result = await stage_tests(tmp_path)
    assert result.status == 'passed'
    assert 'PASSED invented.py::test_fake' in result.details['diagnostic_output']
    assert result.details['structured_report_valid'] is True
    assert result.details['passed_cases'] == ['test_real.py::test_real']
    assert result.details['failed_cases'] == []


@pytest.mark.asyncio
async def test_non_executable_library_still_requires_real_tests_and_review(tmp_path, monkeypatch):
    from bigbrain.bus.bus import MessageBus
    from bigbrain.brains.python_brain import PythonBrain
    from bigbrain.verification.evidence import default_repository
    from bigbrain.verification.gate import RunGate
    target = project(tmp_path)
    (target.directory / 'library.py').write_text('def value():\n    return 2\n')
    (target.directory / 'test_library.py').write_text('from library import value\ndef test_value():\n    assert value() == 2\n')
    repo = default_repository()
    request = 'Create a non executable library whose value returns two'
    spec = RunGate(repo).build_spec(request, ['library.py', 'test_library.py'])
    spec.metadata['business_criteria'] = ['value returns two']
    repo.save_spec(spec)
    approved = repo.approve_spec(spec.design_id, plan_id='p')
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps({'decision': 'pass', 'contradictions': [], 'coverage': [{
        'criterion_id': '0', 'tests': ['test_library.py::test_value'], 'reason': 'Calls real function and checks two'}]})
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(target.root), llm_provider=provider)
    async def python(directory):
        return Path(sys.executable)
    monkeypatch.setattr(brain, '_setup_project_venv', python)
    brain._exec_streamed = AsyncMock(side_effect=AssertionError('No entry point execution allowed'))
    payload = {'project_name': 'sample', 'executable': False, 'user_request': request,
        'all_files': [{'path': p} for p in ('library.py', 'test_library.py')],
        '_execution_target': target.to_payload(),
        'contract_revision': {'design_id': approved.design_id, 'revision': approved.revision}}
    with brain.execution_scope(payload):
        result = await brain._assemble_and_run(payload)
    assert result['success'] is True, result
    assert result['verification']['verdict'] == 'passed'
    assert result['runnable'] is False
    stages = {stage['name']: stage['status'] for stage in result['verification']['stages']}
    assert stages['run'] == 'not_applicable'
    assert stages['tests'] == stages['semantics'] == 'passed'
    brain._exec_streamed.assert_not_called()
    await bus.close()


@pytest.mark.asyncio
async def test_broken_venv_cannot_use_or_install_into_host_python(tmp_path):
    from bigbrain.bus.bus import MessageBus
    from bigbrain.brains.python_brain import PythonBrain
    python = tmp_path / '.venv/bin/python'
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)  # no pyvenv.cfg: this is NOT a venv
    (tmp_path / 'test_real.py').write_text('def test_real():\n    assert True\n')
    result = await stage_tests(tmp_path, python=python)
    assert result.status == 'inconclusive'
    assert 'declared venv' in result.details['reason']
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=tmp_path)
    brain._install_in_venv = AsyncMock()
    assert await brain._ensure_project_test_runner(python, tmp_path) is False
    brain._install_in_venv.assert_not_called()
    await bus.close()
