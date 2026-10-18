"""The memory test root must isolate ALL persistent stores, not just Chroma."""

from pathlib import Path
import pytest

from bigbrain.memory.long_term_memory import LongTermMemory
from bigbrain.memory.project_memory import ProjectMemory


def test_environment_isolates_legacy_stores_and_leaves_cwd_memory_untouched(tmp_path, monkeypatch):
    runtime = tmp_path / 'runtime'
    existing = runtime / 'memory' / 'long_term' / 'preferences.json'
    existing.parent.mkdir(parents=True)
    existing.write_text('{"sentinel": "user data"}')
    monkeypatch.chdir(runtime)
    isolated = tmp_path / 'isolated'
    monkeypatch.setenv('BIGBRAIN_MEMORY_DIR', str(isolated))

    project = ProjectMemory('context', workspace='front')
    project.store('a test-only fact')
    long_term = LongTermMemory()
    long_term.store_user_preference('sentinel', 'test-only value')

    assert project.storage_file.is_relative_to(isolated)
    assert long_term.preferences_file.is_relative_to(isolated)
    assert existing.read_text() == '{"sentinel": "user data"}'
    assert not (runtime / 'memory' / 'projects').exists()


def test_explicit_paths_override_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('BIGBRAIN_MEMORY_DIR', str(tmp_path / 'env'))
    explicit = tmp_path / 'explicit'
    assert ProjectMemory('context', storage_dir=explicit).storage_dir == explicit
    assert LongTermMemory(storage_dir=explicit).storage_dir == explicit


def test_unset_environment_preserves_existing_runtime_paths(tmp_path, monkeypatch):
    monkeypatch.delenv('BIGBRAIN_MEMORY_DIR', raising=False)
    monkeypatch.chdir(tmp_path)
    assert ProjectMemory('context').storage_dir == Path('memory/projects')
    assert LongTermMemory().storage_dir == Path('memory/long_term')


@pytest.mark.asyncio
async def test_orchestrator_learnings_also_respect_the_isolated_root(tmp_path, monkeypatch):
    from bigbrain.bus.bus import MessageBus
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    monkeypatch.chdir(runtime)
    isolated = tmp_path / 'isolated'
    monkeypatch.setenv('BIGBRAIN_MEMORY_DIR', str(isolated))
    bus = MessageBus(tmp_path / 'logs', auth=None)
    orch = WorkspaceOrchestrator('test', bus)
    await orch._save_learnings([{'type': 'test', 'timestamp': 1}])
    assert orch.load_learnings() == [{'type': 'test', 'timestamp': 1}]
    assert (isolated / 'legacy/long_term/learnings.json').is_file()
    assert not (runtime / 'memory').exists()
    await bus.close()
