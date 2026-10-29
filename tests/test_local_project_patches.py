"""Versioned batch publication with shared transaction recovery."""

import hashlib
import pytest

from bigbrain.local_projects import ProjectAccessError, ProjectRegistry
from bigbrain.local_project_patches import apply_patch_set, verify_and_apply
from bigbrain.project_transaction import ProjectTransaction


def setup(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'a.py').write_text('a = 1\n')
    (root / 'b.py').write_text('b = 1\n')
    registry = ProjectRegistry(tmp_path / 'state' / 'registry.json')
    project = registry.attach(root, ('read', 'write'))
    patches = [{'path': p, 'sha256': hashlib.sha256((root / p).read_bytes()).hexdigest(),
                'content': 'value = 2\n'} for p in ['a.py', 'b.py']]
    return root, registry, project, patches


def test_patch_batch_preserves_unrelated_files(tmp_path):
    root, registry, project, patches = setup(tmp_path)
    (root / 'user.txt').write_text('keep')
    result = apply_patch_set(registry, project['id'], 1, patches)
    assert result['state'] == 'committed'
    assert (root / 'a.py').read_text() == 'value = 2\n'
    assert (root / 'b.py').read_text() == 'value = 2\n'
    assert (root / 'user.txt').read_text() == 'keep'
    assert not (root / '.project.json').exists()
    assert not (root.parent / '.bigbrain-transactions').exists()


def test_failed_batch_restores_first_write(tmp_path, monkeypatch):
    root, registry, project, patches = setup(tmp_path)
    original = ProjectTransaction.write

    def fail_second(self, target, path, data):
        if path == 'b.py':
            raise OSError('injected publication failure')
        return original(self, target, path, data)

    monkeypatch.setattr(ProjectTransaction, 'write', fail_second)
    with pytest.raises(OSError, match='publication'):
        apply_patch_set(registry, project['id'], 1, patches)
    assert (root / 'a.py').read_text() == 'a = 1\n'
    assert (root / 'b.py').read_text() == 'b = 1\n'


def test_concurrent_edit_refuses_whole_batch(tmp_path):
    root, registry, project, patches = setup(tmp_path)
    (root / 'b.py').write_text('user edit\n')
    with pytest.raises(ProjectAccessError, match='concurrently'):
        apply_patch_set(registry, project['id'], 1, patches)
    assert (root / 'a.py').read_text() == 'a = 1\n'
    assert (root / 'b.py').read_text() == 'user edit\n'


@pytest.mark.asyncio
async def test_repair_checks_candidate_and_published_project(tmp_path):
    root, registry, project, _ = setup(tmp_path)
    (root / 'main.py').write_text('def double(n): return n\n')
    (root / 'test_main.py').write_text(
        'import unittest\nfrom main import double\n'
        'class Tests(unittest.TestCase):\n'
        '    def test_double(self): self.assertEqual(double(3), 6)\n')
    registry.change(project['id'], 1, rights=('read', 'write', 'execute'))
    patch = {'path': 'main.py', 'content': 'def double(n): return n * 2\n',
             'sha256': hashlib.sha256((root / 'main.py').read_bytes()).hexdigest()}
    result = await verify_and_apply(registry, project['id'], 2, [patch],
                                    [['python', '-m', 'unittest', 'discover']])
    assert result['state'] == 'committed'
    assert [check['phase'] for check in result['checks']] == ['candidate', 'published']
    assert all(check['exitCode'] == 0 for check in result['checks'])
    assert (root / 'main.py').read_text() == patch['content']


@pytest.mark.asyncio
async def test_failed_candidate_preserves_original_project(tmp_path):
    root, registry, project, patches = setup(tmp_path)
    registry.change(project['id'], 1, rights=('read', 'write', 'execute'))
    result = await verify_and_apply(registry, project['id'], 2, patches,
                                    [['python', '-c', 'raise SystemExit(1)']])
    assert result['state'] == 'incomplete'
    assert result['changedPaths'] == []
    assert (root / 'a.py').read_text() == 'a = 1\n'
    assert (root / 'b.py').read_text() == 'b = 1\n'


@pytest.mark.asyncio
async def test_repair_protects_validation_files(tmp_path):
    _, registry, project, _ = setup(tmp_path)
    with pytest.raises(ProjectAccessError, match='approved contract'):
        await verify_and_apply(registry, project['id'], 1,
                               [{'path': 'tests/test_main.py', 'content': 'pass', 'sha256': None}],
                               [['python', '-m', 'unittest']])
