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


def test_project_origin_switch_preserves_choice_and_conversation_boundary(tmp_path):
    _, registry, project, _ = fixture(tmp_path)
    registry.selection('a', project_id=project['id'], update=True)
    assert registry.conversation_context('a')['project_id'] == project['id']
    registry.selection_origin('a', origin='workspace', update=True)
    assert registry.conversation_context('a') is None
    assert registry.selection('a') == project['id']
    reopened = ProjectRegistry(registry.path)
    assert reopened.selection_origin('a') == 'workspace'
    assert reopened.selection_origin('b') == 'workspace'
    reopened.selection_origin('a', origin='local', update=True)
    assert reopened.conversation_context('a')['project_id'] == project['id']
    reopened.selection('a', project_id=None, update=True)
    assert reopened.conversation_context('a')['state'] == 'unselected'


def test_legacy_selection_keeps_its_identity_during_origin_migration(tmp_path):
    _, registry, project, _ = fixture(tmp_path)
    selections = ProjectRegistry(registry.path.with_name('selections.json'))
    with selections._locked() as records:
        records['legacy'] = project['id']
    assert registry.selection_origin('legacy') == 'local'
    assert registry.conversation_context('legacy')['project_id'] == project['id']
    registry.selection_origin('legacy', origin='workspace', update=True)
    assert registry.selection('legacy') == project['id']
    assert registry.conversation_context('legacy') is None


def test_snapshot_inherits_source_revocation_and_keeps_separate_files(tmp_path):
    root, registry, project, _ = fixture(tmp_path)
    snapshot = registry.create_snapshot(project['id'], 1)
    assert snapshot['origin'] == 'runtime_snapshot'
    assert registry.list() == [project]
    stage = ProjectFiles(registry, snapshot['id'], 1)
    stage.write('main.py', b'candidate', hashlib.sha256(b'original').hexdigest())
    assert (root / 'main.py').read_bytes() == b'original'
    registry.change(project['id'], 1, state='revoked')
    with pytest.raises(ProjectAccessError, match='source grant'):
        stage.read('main.py')


def test_source_directory_cannot_contain_registry(tmp_path):
    registry = ProjectRegistry(tmp_path / 'state' / 'registry.json')
    with pytest.raises(ProjectAccessError, match='outside'):
        registry.attach(tmp_path)


def test_relocated_project_keeps_identity_and_conversation_selection(tmp_path):
    source, registry, project, old_files = fixture(tmp_path)
    registry.selection('conversation', project_id=project['id'], update=True)
    moved = tmp_path / 'renamed-project'
    source.rename(moved)
    restored = registry.restore(project['id'], 1, selected_root=moved)
    assert restored['id'] == project['id']
    assert restored['revision'] == 2
    assert registry.selection('conversation') == project['id']
    assert ProjectFiles(registry, project['id'], 2).read('main.py') == b'original'
    with pytest.raises(ProjectAccessError):
        old_files.read('main.py')


def test_restore_refuses_replaced_directory(tmp_path):
    source, registry, project, _ = fixture(tmp_path)
    revoked = registry.change(project['id'], 1, state='revoked')
    source.rename(tmp_path / 'original-directory')
    source.mkdir()
    with pytest.raises(ProjectAccessError, match='different project identity'):
        registry.restore(project['id'], revoked['revision'])
