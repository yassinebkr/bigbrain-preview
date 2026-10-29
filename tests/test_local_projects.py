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


def test_listing_filters_sensitive_and_indirect_files(tmp_path):
    root, _, _, files = fixture(tmp_path)
    (root / '.env').write_text('secret')
    (root / 'node_modules').mkdir()
    (root / 'sub').mkdir()
    (root / 'sub' / 'code.py').write_text('pass')
    (root / 'alias').symlink_to(root / 'main.py')
    assert [entry['name'] for entry in files.list()] == ['sub', 'main.py']
    assert files.list('sub')[0]['path'] == 'sub/code.py'


def test_overlap_and_stale_grant(tmp_path):
    root, registry, record, files = fixture(tmp_path)
    (root / 'sub').mkdir()
    with pytest.raises(ProjectAccessError, match='overlapping'):
        registry.attach(root / 'sub')
    registry.change(record['id'], 1, rights=('read',))
    with pytest.raises(ProjectAccessError):
        files.list()


def test_ancestor_symlink_substitution(tmp_path):
    container = tmp_path / 'container'
    container.mkdir()
    root = container / 'project'
    root.mkdir()
    registry = ProjectRegistry(tmp_path / 'state.json')
    record = registry.attach(root)
    container.rename(tmp_path / 'moved')
    container.symlink_to(tmp_path / 'moved', target_is_directory=True)
    with pytest.raises(ProjectAccessError, match='unavailable'):
        ProjectFiles(registry, record['id'], 1).list()


def test_conversation_selection_survives_restart(tmp_path):
    _, registry, project, _ = fixture(tmp_path)
    registry.selection('conversation-a', project_id=project['id'], update=True)
    reopened = ProjectRegistry(registry.path)
    assert reopened.selection('conversation-a') == project['id']
    assert reopened.selection('conversation-b') is None
    reopened.selection('conversation-a', update=True)
    assert registry.selection('conversation-a') is None
