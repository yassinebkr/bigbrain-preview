"""Real files/patches/execution, deterministic provider contracts, no paid calls."""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.brains.python_brain import PythonBrain
from bigbrain.brains.web_app_brain import WebAppBrain
from bigbrain.execution_target import ExecutionTarget
from bigbrain.orchestrator.architect import ArchitectPhase
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator
from bigbrain.project_inspection import digest, inspect_project


def existing(tmp_path, files):
    root = tmp_path / 'workspace'
    directory = root / 'sandbox' / 'tool'
    directory.mkdir(parents=True)
    for path, source in files.items():
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding='utf-8')
    (directory / '.project.json').write_text('{"entry_point":"main.py"}')
    return ExecutionTarget('existing', 'sandbox/tool', str(root)).prepare()


def raw_spec():
    return {'project_name': 'do-not-create-a-parallel-project', 'deliverable_type': 'python',
        'entry_point': 'main.py', 'acceptance_contracts': ['Print 2 without arguments', 'Preserve the existing helper'],
        'file_specs': [{'path': 'main.py', 'operation': 'modify', 'implementation_notes': 'Change VALUE only'},
                       {'path': 'tests/test_main.py', 'operation': 'keep', 'dependencies': ['main.py']}]}


def test_inspection_is_bounded_read_only_and_excludes_secrets_links_and_binary(tmp_path, monkeypatch):
    binding = existing(tmp_path, {'main.py': 'VALUE = 1\n', '.env': 'PRIVATE=hidden',
        'secret.json': '{"private":"hidden"}', 'config.py': 'API_KEY = "abcdefghijklmnop"',
        'large.py': '# ' + 'x' * 200, 'binary.py': '\x00hidden'})
    outside = tmp_path / 'outside.py'
    outside.write_text('DO_NOT_READ')
    (binding.directory / 'link.py').symlink_to(outside)
    (binding.directory / 'linked').symlink_to(tmp_path, target_is_directory=True)
    import bigbrain.project_inspection as module
    monkeypatch.setattr(module, 'MAX_FILE_BYTES', 40)
    before = {p: p.read_bytes() for p in binding.directory.iterdir() if p.is_file()}
    snapshot = inspect_project(binding)
    assert snapshot['sources']['main.py']['sha256'] == digest('VALUE = 1\n')
    assert not snapshot['sources']['large.py']['complete']
    assert snapshot['limited']
    encoded = json.dumps(snapshot)
    assert 'DO_NOT_READ' not in encoded and 'abcdefghijklmnop' not in encoded and 'PRIVATE=hidden' not in encoded
    assert set(snapshot['sources']) == {'main.py', 'large.py'}
    assert all(p.read_bytes() == content for p, content in before.items())


@pytest.mark.asyncio
async def test_architect_preserves_omitted_files_and_requires_explicit_operations(tmp_path):
    binding = existing(tmp_path, {'main.py': 'VALUE = 1\n', 'helper.py': 'UNCHANGED = 3\n',
        'tests/test_main.py': 'def test_value():\n    assert True\n'})
    snapshot = inspect_project(binding)
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps(raw_spec())
    spec = await ArchitectPhase(provider).design('Fix VALUE', expected_deliverable='python', existing_project=snapshot)
    assert spec.project_name == 'tool'
    assert spec.get_file_spec('helper.py').operation == 'keep'
    assert spec.get_file_spec('main.py').operation == 'modify'
    messages = provider.chat_complete.call_args.kwargs['messages']
    assert 'UNCHANGED = 3' not in messages[0]['content']
    assert 'UNCHANGED = 3' in messages[1]['content']
    invalid = raw_spec()
    invalid['file_specs'][0]['operation'] = 'write'
    provider.chat_complete.return_value = json.dumps(invalid)
    with pytest.raises(ValueError, match='explicitly choose operation'):
        await ArchitectPhase(provider).design('Fix', expected_deliverable='python', existing_project=snapshot)
    snapshot['sources']['main.py']['complete'] = False
    provider.chat_complete.return_value = json.dumps(raw_spec())
    with pytest.raises(ValueError, match='not completely inspected'):
        await ArchitectPhase(provider).design('Fix', expected_deliverable='python', existing_project=snapshot)


@pytest.mark.asyncio
async def test_existing_project_plans_maintenance_without_guessing_files(tmp_path, monkeypatch):
    binding = existing(tmp_path, {'main.py': 'VALUE = 1\nprint(VALUE)\n', 'helper.py': '# keep\n',
        'tests/test_main.py': 'def test_value():\n    assert True\n'})
    monkeypatch.setenv('BIGBRAIN_WORKSPACE_DIR', binding.root)
    provider = AsyncMock()
    provider.chat_complete.side_effect = [json.dumps({'mode': 'project', 'deliverable_type': 'python', 'needs_research': False}), json.dumps(['Correct the value and preserve unrelated behavior'])]
    bus = MessageBus(tmp_path / 'logs', auth=None)
    orchestrator = WorkspaceOrchestrator('default', bus, llm_provider=provider)
    message = BusMessage(type=MessageType.TASK, source='front_brain', target='orchestrator_default',
        payload={'type': 'compound', 'user_request': 'Fix VALUE', 'session_id': 'sess-local',
                 'project_target': binding.public()})
    before = {p: p.read_bytes() for p in binding.directory.rglob('*') if p.is_file()}
    plan = await orchestrator._create_task_plan(message)
    assert [s.payload['type'] for s in plan.subtasks] == ['maintain_project']
    assert plan.subtasks[0].brain_target == 'python_brain'
    assert 'file_path' not in plan.subtasks[0].payload
    assert plan.execution_target.inode == binding.inode
    assert plan.inspection is None  # approved investigation owns diagnostics
    architecture_messages = provider.chat_complete.call_args.kwargs['messages']
    assert 'VALUE = 1' not in architecture_messages[1]['content']
    assert all(p.read_bytes() == source for p, source in before.items())  # diagnostic, no implementation edits
    await bus.close()


@pytest.mark.asyncio
async def test_direct_edit_keeps_native_route_but_requires_inspected_patch(tmp_path, monkeypatch):
    binding = existing(tmp_path, {'main.py': 'VALUE = 1\nprint(VALUE)\n'})
    monkeypatch.setenv('BIGBRAIN_WORKSPACE_DIR', binding.root)
    bus = MessageBus(tmp_path / 'logs', auth=None)
    orchestrator = WorkspaceOrchestrator('default', bus, llm_provider=AsyncMock())
    orchestrator.register_brain('python_brain')
    message = BusMessage(type=MessageType.TASK, source='front_brain', target='orchestrator_default',
        payload={'type': 'edit_file', 'brain': 'python_brain', 'file_path': 'main.py',
                 'instructions': 'Set VALUE to 2', 'project_target': binding.public()})
    plan = await orchestrator._create_task_plan(message)
    assert len(plan.subtasks) == 2
    assert plan.subtasks[0].payload['type'] == 'edit_file'
    assert plan.subtasks[1].payload['type'] == 'assemble_and_run'
    assert plan.subtasks[1].dependencies == {plan.subtasks[0].id}
    assert plan.subtasks[0].payload['_existing_source']['sha256'] == digest('VALUE = 1\nprint(VALUE)\n')
    orchestrator.llm_provider.chat_complete.assert_not_called()
    await bus.close()


@pytest.mark.asyncio
async def test_repair_documentation_does_not_exhaust_python_source_budget(tmp_path):
    files = {'main.py': 'VALUE = 1\nprint(VALUE)\n',
             'tests/test_main.py': 'assert True\n', 'README.md': 'x' * 120_000}
    binding = existing(tmp_path, files)
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps({'edits': [
        {'path': 'main.py', 'old': 'VALUE = 1', 'new': 'VALUE = 2'}]})
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(binding.root), llm_provider=provider)
    brain.send_progress = AsyncMock()
    assert await brain._repair_project_sources(binding.directory, files, 'Fix value', [], editable_paths=['main.py'])
    prompt = provider.chat_complete.call_args.kwargs['messages'][0]['content']
    assert 'README.md' not in prompt
    assert 'tests/test_main.py' in prompt
    assert (binding.directory / 'README.md').read_text() == files['README.md']
    assert (binding.directory / 'tests/test_main.py').read_text() == files['tests/test_main.py']
    assert (binding.directory / 'main.py').read_text() == 'VALUE = 2\nprint(VALUE)\n'
    await bus.close()


@pytest.mark.asyncio
async def test_automatic_repair_cannot_change_a_kept_file_and_reports_why(tmp_path):
    binding = existing(tmp_path, {'main.py': 'VALUE = 1\nprint(VALUE)\n', 'helper.py': 'KEEP = 1\n'})
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps({'edits': [{'path': 'helper.py', 'old': 'KEEP = 1', 'new': 'KEEP = 2'}]})
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(binding.root), llm_provider=provider)
    brain.send_progress = AsyncMock()
    files = {path: source['content'] for path, source in inspect_project(binding)['sources'].items()}
    assert not await brain._repair_project_sources(binding.directory, files, 'Fix main only', [], editable_paths=['main.py'])
    assert (binding.directory / 'helper.py').read_text() == 'KEEP = 1\n'
    brain.send_progress.assert_awaited_with({'stage': 'repair_declined', 'reason_code': 'unauthorized_or_invalid_edit'})
    web = WebAppBrain('web', bus, work_dir=Path(binding.root), llm_provider=provider)
    with pytest.raises(ValueError, match='targeted repair plan'):
        await web._repair_browser_failure(binding.directory, {}, {'_editable_paths': ['app.js']})
    await bus.close()


@pytest.mark.asyncio
async def test_creation_cannot_overwrite_a_file_added_during_generation(tmp_path):
    binding = existing(tmp_path, {'README.md': 'Keep\n'})
    provider = AsyncMock()
    async def response(*args, **kwargs):
        (binding.directory / 'main.py').write_text('# external file\n')
        return 'print("new")\n'
    provider.complete.side_effect = response
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(binding.root), llm_provider=provider)
    payload = {'file_path': 'main.py', 'project_name': 'tool', '_create_only': True, '_execution_target': binding.to_payload()}
    with brain.execution_scope(payload), pytest.raises(ValueError, match='cannot overwrite'):
        await brain._write_project_file(payload)
    assert (binding.directory / 'main.py').read_text() == '# external file\n'
    await bus.close()


def test_changed_preserved_dependency_stops_before_worker_execution(tmp_path):
    binding = existing(tmp_path, {'main.py': 'print(1)\n', 'helper.py': 'KEEP = 1\n'})
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(binding.root), llm_provider=AsyncMock())
    payload = {'_execution_target': binding.to_payload(), '_kept_hashes': {'helper.py': digest('KEEP = 1\n')}}
    (binding.directory / 'helper.py').write_text('KEEP = 2\n')
    with pytest.raises(ValueError, match='preserved source changed'):
        with brain.execution_scope(payload):
            pytest.fail('Worker must not execute with an obsolete preserved dependency')
    assert (binding.directory / 'main.py').read_text() == 'print(1)\n'
    brain.llm_provider.chat_complete.assert_not_called()


@pytest.mark.asyncio
async def test_changed_inspection_gets_a_new_immutable_contract_revision(tmp_path):
    from bigbrain.orchestrator.orchestrator import TaskPlan
    from bigbrain.orchestrator.architect import ProjectSpec, FileSpec
    binding = existing(tmp_path, {'main.py': 'print(1)\n'})
    bus = MessageBus(tmp_path / 'logs', auth=None)
    orchestrator = WorkspaceOrchestrator('default', bus, llm_provider=AsyncMock())
    message = BusMessage(type=MessageType.TASK, source='front_brain', target='orchestrator_default', payload={'session_id': 'sess-revision'})
    specs = []
    for fingerprint in ('before', 'after'):
        plan = TaskPlan(id=fingerprint, original_task=message, execution_target=binding,
            inspection={'inventory': [{'path': 'main.py', 'sha256': fingerprint}], 'limits': {}, 'limited': False},
            project_spec=ProjectSpec('tool', 'Fix tool', file_specs=[FileSpec('main.py', 'Fix value', operation='modify')],
                                     acceptance_contracts=['Print 2', 'Preserve helper']))
        specs.append(await orchestrator._propose_contracts(plan, 'Fix the same tool'))
    assert specs[0].design_id == specs[1].design_id
    assert specs[1].revision == specs[0].revision + 1
    assert specs[0].metadata['inspection']['inventory'][0]['sha256'] == 'before'
    assert specs[1].metadata['inspection']['inventory'][0]['sha256'] == 'after'
    await bus.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['todo', 'statistics', 'web-widget'])
async def test_targeted_patch_preserves_project_and_produces_executable_result(tmp_path, monkeypatch, case):
    sources = {
        'todo': ('main.py', 'def todo(items):\n    return items[-1:]\n\nif __name__ == "__main__":\n    print(todo(["a", "b"]))\n', 'return items[-1:]', 'return items', "['a', 'b']"),
        'statistics': ('main.py', 'def mean(values):\n    return sum(values)\n\nif __name__ == "__main__":\n    print(mean([2, 4]))\n', 'return sum(values)', 'return sum(values) / len(values)', '3.0'),
        'web-widget': ('app.js', 'function total(values) { return values.length; }\ndocument.querySelector("button").onclick = () => { document.querySelector("output").textContent = total([2, 4]); };\n', 'return values.length;', 'return values.reduce((a, b) => a + b, 0);', '6'),
    }
    path, source, old, new, expected = sources[case]
    binding = existing(tmp_path, {path: source, 'README.md': 'User documentation must stay byte-for-byte.\n'})
    baseline = inspect_project(binding)['sources'][path]
    if case == 'web-widget':
        (binding.directory / 'index.html').write_text('<button>Calculer</button><output></output><script src="app.js"></script>')
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps({'edits': [{'old': old, 'new': new}]})
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = (WebAppBrain('web', bus, work_dir=Path(binding.root), llm_provider=provider, model='web-test-model') if case == 'web-widget'
             else PythonBrain('python', bus, work_dir=Path(binding.root), llm_provider=provider))
    payload = {'file_path': path, 'project_name': 'tool', '_existing_source': baseline,
               '_execution_target': binding.to_payload(), 'user_request': 'Fix only the calculation'}
    with brain.execution_scope(payload):
        result = await (brain._write_web_file(payload) if case == 'web-widget' else brain._write_project_file(payload))
    assert result['method'] == 'patch'
    assert (binding.directory / path).read_text() == source.replace(old, new)
    assert (binding.directory / 'README.md').read_text() == 'User documentation must stay byte-for-byte.\n'
    import asyncio
    if case == 'web-widget':
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, args=['--no-sandbox'])
            try:
                page = await browser.new_page()
                await page.goto((binding.directory / 'index.html').as_uri())
                await page.get_by_role('button', name='Calculer').click()
                assert await page.locator('output').inner_text() == expected
            finally:
                await browser.close()
        assert provider.chat_complete.call_args.kwargs['model'] == 'web-test-model'
    else:
        process = await asyncio.create_subprocess_exec(sys.executable, str(binding.directory / path), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await process.communicate()
        assert process.returncode == 0, err
        assert out.decode().strip() == expected
    await bus.close()


@pytest.mark.asyncio
async def test_legacy_multifile_baseline_keeps_entry_and_tests_then_passes_real_gate(tmp_path, monkeypatch):
    files = {'main.py': 'from calc import value\nprint(value())\n',
             'calc.py': 'def value():\n    return 1\n\ndef unrelated():\n    return "keep me"\n',
             'tests/test_calc.py': 'from calc import value, unrelated\n\ndef test_value():\n    assert value() == 2\n\ndef test_preserved():\n    assert unrelated() == "keep me"\n',
             'README.md': 'python main.py\n'}
    binding = existing(tmp_path, files)
    monkeypatch.setenv('BIGBRAIN_WORKSPACE_DIR', binding.root)
    provider = AsyncMock()
    specification = raw_spec()
    specification['file_specs'] = [{'path': 'calc.py', 'operation': 'modify', 'implementation_notes': 'Change only value() to return 2'},
        {'path': 'tests/test_calc.py', 'operation': 'keep', 'dependencies': ['calc.py']}]
    provider.chat_complete.side_effect = [json.dumps(specification), json.dumps({'edits': [{'old': 'return 1', 'new': 'return 2'}]})]
    bus = MessageBus(tmp_path / 'logs', auth=None)
    orchestrator = WorkspaceOrchestrator('default', bus, llm_provider=provider)
    message = BusMessage(type=MessageType.TASK, source='front_brain', target='orchestrator_default',
        payload={'type': 'compound', 'user_request': 'Fix value to return 2, keep all other behaviour and tests',
                 'session_id': 'sess-multifile', 'project_target': binding.public()})
    from bigbrain.orchestrator.orchestrator import TaskPlan
    plan = TaskPlan('legacy-baseline', message)
    plan.subtasks = await orchestrator._plan_project(plan.id, message.payload['user_request'], False, [],
        deliverable_type='python', session_id='sess-multifile', plan=plan)
    assert [s.payload.get('file_path') for s in plan.subtasks[:-1]] == ['calc.py']
    brain = PythonBrain('python', bus, work_dir=Path(binding.root), llm_provider=provider)
    async def current_python(directory): return Path(sys.executable)
    monkeypatch.setattr(brain, '_setup_project_venv', current_python)
    for subtask in plan.subtasks:
        payload = {**subtask.payload, '_execution_target': plan.execution_target.to_payload()}
        with brain.execution_scope(payload):
            result = await (brain._assemble_and_run(payload) if payload['type'] == 'assemble_and_run' else brain._write_project_file(payload))
        assert result['success'], result
    assert result['verification']['verdict'] == 'passed'
    assert result['stdout'].strip() == '2'
    for path in ('main.py', 'tests/test_calc.py', 'README.md'):
        assert (binding.directory / path).read_text() == files[path]
    assert (binding.directory / 'calc.py').read_text() == files['calc.py'].replace('return 1', 'return 2')
    assert not (binding.directory / 'do-not-create-a-parallel-project').exists()
    await bus.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['ambiguous', 'syntax', 'whole-file', 'empty', 'concurrent', 'contract'])
async def test_invalid_patch_never_falls_back_to_rewrite_or_overwrites_changes(tmp_path, bad):
    source = 'VALUE = 1\nOTHER = 1\nprint(VALUE)\n'
    binding = existing(tmp_path, {'main.py': source})
    provider = AsyncMock()
    edits = {'edits': [{'old': 'VALUE = 1', 'new': 'VALUE = 2'}]}
    if bad == 'ambiguous': edits = {'edits': [{'old': '= 1', 'new': '= 2'}]}
    if bad == 'syntax': edits['edits'][0]['new'] = 'VALUE = ('
    if bad == 'whole-file': edits = {'edits': [{'old': source, 'new': 'print(2)\n'}]}
    if bad == 'empty': edits = {'edits': []}
    if bad == 'contract': edits = {'requires_contract_change': True, 'edits': []}
    baseline = inspect_project(binding)['sources']['main.py']
    async def answer(**kwargs):
        if bad == 'concurrent': (binding.directory / 'main.py').write_text('# external edit\n')
        return json.dumps(edits)
    provider.chat_complete.side_effect = answer
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=Path(binding.root), llm_provider=provider)
    payload = {'file_path': 'main.py', '_existing_source': baseline, '_execution_target': binding.to_payload()}
    with brain.execution_scope(payload), pytest.raises((ValueError, SyntaxError)):
        await brain._write_project_file(payload)
    assert (binding.directory / 'main.py').read_text() == ('# external edit\n' if bad == 'concurrent' else source)
    provider.complete.assert_not_called()
    await bus.close()
