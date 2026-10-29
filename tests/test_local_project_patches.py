"""Versioned batch publication with shared transaction recovery."""

import hashlib
import pytest

from bigbrain.local_projects import ProjectAccessError, ProjectRegistry
from bigbrain.local_project_patches import apply_patch_set
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
