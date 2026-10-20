"""Real multi-file campaign for the architect/batch/assembly contract."""

from pathlib import Path

import pytest

from bigbrain.brains.python_brain import PythonBrain
from bigbrain.bus.bus import MessageBus
from bigbrain.verification.executors import stage_contracts, stage_tests
from bigbrain.verification.gate import RunGate


@pytest.mark.asyncio
async def test_assemble_fails_when_acceptance_tests_fail(tmp_path, monkeypatch):
    import sys

    monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", str(tmp_path / "evidence"))
    brain = PythonBrain("python_brain_test", MessageBus(auth=None), "default",
                        work_dir=tmp_path)
    project = tmp_path / "broken-project"
    (project / "tests").mkdir(parents=True)
    (project / "main.py").write_text("print('looks fine')\n")
    (project / "tests" / "test_acceptance.py").write_text(
        "def test_requested_behavior():\n    assert False, 'feature is unusable'\n")

    async def current_python(_project_dir):
        return Path(sys.executable)

    monkeypatch.setattr(brain, "_setup_project_venv", current_python)
    result = await brain._assemble_and_run({
        "project_name": "broken-project",
        "user_request": "build a usable feature",
        "all_files": [{"path": "main.py"}, {"path": "tests/test_acceptance.py"}],
        "entry_point": "main.py",
    })

    assert result["success"] is False
    assert result["verification"]["verdict"] == "failed"
    assert 'tests' in result['error']
    assert 'not runnable' not in result['error']
    assert result['exit_code'] == 0
    assert not (project / ".project.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('repair', ['valid', 'ineffective', 'tests', 'traversal'])
async def test_assembly_repairs_sources_with_frozen_tests_and_bounded_attempts(tmp_path, monkeypatch, repair):
    import json
    import sys
    from unittest.mock import AsyncMock

    monkeypatch.setenv('BIGBRAIN_WORKSPACE_DIR', str(tmp_path))
    monkeypatch.setenv('BIGBRAIN_EVIDENCE_ROOT', str(tmp_path / 'evidence'))
    brain = PythonBrain('python_repair', MessageBus(auth=None), 'default', work_dir=tmp_path)
    project = tmp_path / 'repair-demo'
    (project / 'tests').mkdir(parents=True)
    original_test = 'from main import value\n\ndef test_value():\n    assert value() == 2\n'
    (project / 'tests/test_value.py').write_text(original_test)
    (project / 'main.py').write_text('def value(): return 1\nprint(value())\n')
    async def current_python(_):
        return Path(sys.executable)
    monkeypatch.setattr(brain, '_setup_project_venv', current_python)
    calls = 0
    async def proposal(**kwargs):
        nonlocal calls
        calls += 1
        path = {'tests': 'tests/test_value.py', 'traversal': '../escape.py'}.get(repair, 'main.py')
        value = 2 if repair == 'valid' else 10 + calls
        current = (project / 'main.py').read_text()
        return json.dumps({'edits': [{'path': path, 'old': current, 'new': f'def value(): return {value}\nprint(value())\n'}]})
    provider = AsyncMock()
    provider.chat_complete.side_effect = proposal
    brain.llm_provider = provider
    result = await brain._assemble_and_run({
        'project_name': 'repair-demo', 'user_request': 'Return and print 2',
        'entry_point': 'main.py',
        'all_files': [{'path': 'main.py'}, {'path': 'tests/test_value.py'}],
    })
    assert result['success'] is (repair == 'valid'), result
    assert calls == (2 if repair == 'ineffective' else 1)
    assert (project / 'tests/test_value.py').read_text() == original_test
    assert not (tmp_path / 'escape.py').exists()
    if repair == 'valid':
        assert result['stdout'].strip() == '2'
        assert result['verification']['verdict'] == 'passed'
        assert len(result['repair_history']) == 1
    else:
        assert 'tests' in result['error']
        assert not (project / '.project.json').exists()


@pytest.mark.asyncio
async def test_assembly_gate_exception_is_not_a_success(tmp_path, monkeypatch):
    import sys
    monkeypatch.setenv('BIGBRAIN_WORKSPACE_DIR', str(tmp_path))
    brain = PythonBrain('python_gate_error', MessageBus(auth=None), 'default', work_dir=tmp_path)
    project = tmp_path / 'gate-error'
    project.mkdir()
    (project / 'main.py').write_text('print("works")\n')
    async def current_python(_):
        return Path(sys.executable)
    async def broken_gate(*args, **kwargs):
        raise RuntimeError('Evidence unavailable')
    monkeypatch.setattr(brain, '_setup_project_venv', current_python)
    monkeypatch.setattr(RunGate, 'evaluate_attempt', broken_gate)
    result = await brain._assemble_and_run({'project_name': 'gate-error', 'entry_point': 'main.py', 'all_files': [{'path': 'main.py'}]})
    assert result['success'] is False
    assert 'verification unavailable' in result['error']
    assert not (project / '.project.json').exists()


@pytest.mark.asyncio
async def test_assemble_validates_explicit_non_executable_project(tmp_path, monkeypatch):
    import json

    monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path))
    brain = PythonBrain("python_brain_test", MessageBus(auth=None), "default",
                        work_dir=tmp_path)
    project = tmp_path / "models-only"
    project.mkdir()
    (project / "models.py").write_text("VALUE = 1\n")

    result = await brain._assemble_and_run({
        "project_name": "models-only",
        "all_files": [{"path": "models.py"}],
        "executable": False,
        "entry_point": None,
    })

    assert result["success"] is True
    assert result["runnable"] is False
    assert result["entry_point"] is None
    manifest = json.loads((project / ".project.json").read_text())
    assert manifest["executable"] is False
    assert manifest["entry_point"] is None


@pytest.mark.asyncio
async def test_assemble_refuses_missing_declared_entry_point(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path))
    brain = PythonBrain("python_brain_test", MessageBus(auth=None), "default",
                        work_dir=tmp_path)
    project = tmp_path / "passive-project"
    project.mkdir()
    (project / "models.py").write_text("VALUE = 1\n")

    result = await brain._assemble_and_run({
        "project_name": "passive-project",
        "all_files": [{"path": "models.py"}],
        "entry_point": "main.py",
    })

    assert result["success"] is False
    assert result["exit_code"] == -5
    assert "Declared entry point is missing" in result["error"]


@pytest.mark.asyncio
async def test_assemble_rejects_silent_entry_point(tmp_path, monkeypatch):
    import sys

    monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("BIGBRAIN_EVIDENCE", "0")
    brain = PythonBrain("python_brain_test", MessageBus(auth=None), "default",
                        work_dir=tmp_path)
    project = tmp_path / "silent-project"
    project.mkdir()
    (project / "main.py").write_text("value = 1\n")

    async def current_python(_project_dir):
        return Path(sys.executable)

    monkeypatch.setattr(brain, "_setup_project_venv", current_python)
    result = await brain._assemble_and_run({
        "project_name": "silent-project",
        "all_files": [{"path": "main.py"}],
        "entry_point": "main.py",
    })

    assert result["success"] is False
    assert result["exit_code"] == -6
    assert "produced no output" in result["stderr"]
    assert not (project / ".project.json").exists()


TODO_FILES = {
    "todo/model.py": "from dataclasses import dataclass\n\n@dataclass\nclass Todo:\n    title: str\n    done: bool = False\n",
    "todo/store.py": "import json\nfrom pathlib import Path\nfrom .model import Todo\n\ndef save(path: Path, items: list[Todo]) -> None:\n    path.write_text(json.dumps([item.__dict__ for item in items]))\n\ndef load(path: Path) -> list[Todo]:\n    if not path.exists():\n        return []\n    return [Todo(**row) for row in json.loads(path.read_text())]\n",
    "main.py": "from pathlib import Path\nfrom todo.model import Todo\nfrom todo.store import load, save\n\npath = Path(\"todos.json\")\nitems = load(path)\nitems.append(Todo(\"ship item 9\"))\nsave(path, items)\nprint(items[-1].title)\n",
    "tests/test_store.py": "from pathlib import Path\nfrom todo.model import Todo\nfrom todo.store import load, save\n\ndef test_roundtrip(tmp_path: Path):\n    path = tmp_path / \"todos.json\"\n    save(path, [Todo(\"one\")])\n    assert load(path) == [Todo(\"one\")]\n",
}


@pytest.mark.asyncio
async def test_cli_todo_project_contract_tests_and_gate(tmp_path, monkeypatch):
    import sys

    monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path))
    brain = PythonBrain("python_brain_test", MessageBus(auth=None), "default", work_dir=tmp_path)
    batch = await brain._batch_write_files({
        "files": [{"path": "todo-cli/" + path, "content": content}
                  for path, content in TODO_FILES.items()]
    })
    assert batch["success"] is True

    async def current_python(_project_dir):
        return Path(sys.executable)

    monkeypatch.setattr(brain, "_setup_project_venv", current_python)
    execution = await brain._assemble_and_run({
        "project_name": "todo-cli",
        "user_request": "Build a multi-file todo CLI",
        "all_files": [{"path": path} for path in TODO_FILES],
        "entry_point": "main.py",
    })
    project_dir = tmp_path / "todo-cli"
    assert execution["exit_code"] == 0, execution
    assert execution["stdout"] == "ship item 9\n"
    assert execution["verification"]["verdict"] == "passed"
    assert stage_contracts(project_dir, list(TODO_FILES)).status == "passed"
    tests = await stage_tests(project_dir)
    assert tests.status == "passed"
    assert tests.details["tests"] == ["tests/test_store.py"]

    manifest, verdict = await RunGate().evaluate_attempt(
        user_request="Build a multi-file todo CLI",
        code=TODO_FILES["main.py"],
        execution=execution,
        work_dir=project_dir,
        requested_files=list(TODO_FILES),
        persisted_files=list(TODO_FILES),
        filename="main.py",
    )
    assert verdict == "passed"
    assert len(manifest.metadata["requested_files"]) == 4
    contracts = next(stage for stage in manifest.stages if stage.name == "contracts")
    assert {item["path"] for item in contracts.details["files"]} == set(TODO_FILES)


@pytest.mark.asyncio
async def test_batch_is_atomic_in_its_verdict_and_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path))
    brain = PythonBrain("python_brain_test", MessageBus(auth=None), "default", work_dir=tmp_path)
    result = await brain._batch_write_files({
        "files": [
            {"path": "project/good.py", "content": "ok = True\n"},
            {"path": "../escape.py", "content": "bad = True\n"},
        ]
    })
    assert result["success"] is False
    assert result["exit_code"] == 1
    assert result["summary"] == {
        "total_files": 2, "successful": 1, "failed": 1, "total_bytes": 10
    }
    assert (tmp_path / "project/good.py").is_file()
    assert not (tmp_path.parent / "escape.py").exists()


@pytest.mark.asyncio
async def test_assemble_cleans_stale_files_without_crashing(tmp_path, monkeypatch):
    """Regression (live): re-running a project whose dir already holds a
    file NOT in the new plan crashed with NameError — the stale-file
    cleanup called a logger that was never defined in python_brain."""
    import sys

    monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", str(tmp_path / "ev"))
    brain = PythonBrain("python_brain_test", MessageBus(auth=None), "default",
                        work_dir=tmp_path)

    project = tmp_path / "web-scraper"
    project.mkdir()
    (project / "main.py").write_text("print('new main')\n")
    (project / "old_module.py").write_text("# stale from a previous run\n")

    async def current_python(_project_dir):
        return Path(sys.executable)

    monkeypatch.setattr(brain, "_setup_project_venv", current_python)
    execution = await brain._assemble_and_run({
        "project_name": "web-scraper",
        "user_request": "update main.py",
        "all_files": [{"path": "main.py"}],
        "entry_point": "main.py",
    })

    assert execution["success"] is True, execution
    assert execution["stdout"].strip() == "new main"
    # The stale file was cleaned, the planned file kept
    assert (project / "main.py").is_file()
    assert not (project / "old_module.py").exists()
@pytest.mark.asyncio
@pytest.mark.parametrize('architect_spec', ['', 'A module exporting VALUE = 1'])
@pytest.mark.parametrize('extra', [{}, {'_user_interjection': 'keep it simple', '_task_state': 'one file left'}])
async def test_write_file_prompt_initializes_shared_sections(tmp_path, architect_spec, extra):
    from unittest.mock import AsyncMock

    provider = AsyncMock()
    provider.complete.return_value = 'VALUE = 1\n'
    brain = PythonBrain('python_prompt_test', MessageBus(auth=None), 'default',
                        work_dir=tmp_path, llm_provider=provider)
    result = await brain._write_project_file({
        'project_name': 'sample', 'file_path': 'main.py',
        'user_request': 'Create a module', 'architect_spec': architect_spec, **extra,
    })
    assert result['success'] is True
    assert (tmp_path / 'sample' / 'main.py').read_text().strip() == 'VALUE = 1'
    prompt = provider.complete.call_args.args[0]
    if extra:
        assert 'keep it simple' in prompt
        assert 'one file left' in prompt
