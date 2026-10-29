"""Grant persistence and filesystem boundary regression cases."""

import hashlib
import pytest

from bigbrain.local_projects import ProjectAccessError, ProjectFiles, ProjectRegistry


def fixture(tmp_path, rights=('read', 'write')):
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'main.py').write_bytes(b'original')
    registry = ProjectRegistry(tmp_path / 'state' / 'projects.json')
    record = registry.attach(root, rights)
    return root, registry, record, ProjectFiles(registry, record['id'], 1)


def test_restart_and_hash_preservation(tmp_path):
    root, registry, record, files = fixture(tmp_path)
    reopened = ProjectRegistry(registry.path)
    assert reopened.get(record['id']) == record
    files.write('main.py', b'updated', hashlib.sha256(b'original').hexdigest())
    assert files.read('main.py') == b'updated'
    with pytest.raises(ProjectAccessError, match='concurrently'):
        files.write('main.py', b'lost', hashlib.sha256(b'original').hexdigest())
    assert (root / 'main.py').read_bytes() == b'updated'


@pytest.mark.parametrize('path', ['../secret', '/etc/passwd', '.env',
                                 'node_modules/pkg', 'a/../../secret', 'key.pem'])
def test_excluded_paths(tmp_path, path):
    _, _, _, files = fixture(tmp_path)
    with pytest.raises(ProjectAccessError):
        files.read(path)


def test_readonly_revocation_and_detach_preserve_sources(tmp_path):
    root, registry, record, files = fixture(tmp_path, ('read',))
    with pytest.raises(ProjectAccessError):
        files.write('new.py', b'content', None)
    registry.change(record['id'], 1, state='detached')
    with pytest.raises(ProjectAccessError):
        files.read('main.py')
    assert (root / 'main.py').read_bytes() == b'original'


def test_symlinks_hardlinks_and_replaced_root(tmp_path):
    root, _, _, files = fixture(tmp_path)
    outside = tmp_path / 'outside'
    outside.write_bytes(b'secret')
    (root / 'link').symlink_to(outside)
    with pytest.raises(OSError):
        files.read('link')
    (root / 'hard').hardlink_to(outside)
    with pytest.raises(ProjectAccessError):
        files.read('hard')
    root.rename(tmp_path / 'moved')
    root.mkdir()
    with pytest.raises(ProjectAccessError, match='identity'):
        files.read('main.py')
