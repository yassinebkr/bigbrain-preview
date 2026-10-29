"""Explicit conflict choices remain bound to observed file and journal versions."""

import hashlib
import json

import pytest

from bigbrain.local_projects import ProjectAccessError, ProjectRegistry
from bigbrain.local_project_patches import apply_patch_set
from bigbrain.local_project_recovery import inspect_resolution, resolve_project, project_transactions


def conflict(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'main.py').write_bytes(b'original\n')
    registry = ProjectRegistry(tmp_path / 'state' / 'registry.json')
    project = registry.attach(source, ('read', 'write', 'execute'))
    published = apply_patch_set(registry, project['id'], 1, [{
        'path': 'main.py', 'sha256': hashlib.sha256(b'original\n').hexdigest(),
        'content': 'candidate\n'}])
    journal = registry.path.parent / 'transactions' / (published['transactionId'] + '.json')
    operation = json.loads(journal.read_text())['publications'][0]
    retained = source / operation['preserved']
    retained.write_bytes(b'late editor save\n')
    return source, registry, project, published['transactionId'], operation['id'], retained


def test_keep_current_closes_conflict_and_detects_later_editor_write(tmp_path):
    source, registry, project, transaction, _, retained = conflict(tmp_path)
    decision = inspect_resolution(registry, project['id'], 1, transaction)
    result = resolve_project(registry, project['id'], 1, transaction,
                             decision['token'], {'main.py': 'current'})
    assert result['state'] == 'committed'
    assert (source / 'main.py').read_bytes() == b'candidate\n'
    assert retained.read_bytes() == b'late editor save\n'
    assert project_transactions(registry, project) == []
    with registry.access(project['id'], 1, 'execute'):
        pass
    retained.write_bytes(b'another editor save\n')
    assert project_transactions(registry, project)[0]['conflicts'] == ['main.py']
    with pytest.raises(ProjectAccessError, match='recovery'):
        with registry.access(project['id'], 1, 'execute'):
            pass


def test_restore_retained_uses_shared_publication_and_keeps_candidate(tmp_path):
    source, registry, project, transaction, operation, retained = conflict(tmp_path)
    decision = inspect_resolution(registry, project['id'], 1, transaction)
    result = resolve_project(registry, project['id'], 1, transaction,
                             decision['token'], {'main.py': operation})
    assert result['state'] == 'committed'
    assert (source / 'main.py').read_bytes() == b'late editor save\n'
    assert retained.read_bytes() == b'late editor save\n'
    assert any(path.read_bytes() == b'candidate\n'
               for path in (source / '.bigbrain-recovery').rglob('*') if path.is_file())
    assert project_transactions(registry, project) == []


@pytest.mark.parametrize('change', ['current', 'retained'])
def test_stale_decision_preserves_both_versions(tmp_path, change):
    source, registry, project, transaction, operation, retained = conflict(tmp_path)
    decision = inspect_resolution(registry, project['id'], 1, transaction)
    selected = source / 'main.py' if change == 'current' else retained
    selected.write_bytes(b'changed since inspection\n')
    with pytest.raises(ValueError, match='changed'):
        resolve_project(registry, project['id'], 1, transaction,
                        decision['token'], {'main.py': operation})
    assert selected.read_bytes() == b'changed since inspection\n'


def test_incomplete_choices_and_revocation_are_refused(tmp_path):
    source, registry, project, transaction, _, _ = conflict(tmp_path)
    decision = inspect_resolution(registry, project['id'], 1, transaction)
    with pytest.raises(ValueError, match='every affected'):
        resolve_project(registry, project['id'], 1, transaction, decision['token'], {})
    registry.change(project['id'], 1, state='revoked')
    with pytest.raises(ProjectAccessError):
        resolve_project(registry, project['id'], 1, transaction,
                        decision['token'], {'main.py': 'current'})
    assert (source / 'main.py').read_bytes() == b'candidate\n'


def test_edit_inside_resolution_publication_remains_recoverable(tmp_path, monkeypatch):
    from bigbrain.native_publication import LinuxPublication
    source, registry, project, transaction, operation, retained = conflict(tmp_path)
    decision = inspect_resolution(registry, project['id'], 1, transaction)
    original = LinuxPublication._rename
    def racing(self, candidate, destination, flags, anchors=None):
        if flags == 2 and destination == source / 'main.py':
            destination.write_bytes(b'new user edit during resolution\n')
        return original(self, candidate, destination, flags, anchors)
    monkeypatch.setattr(LinuxPublication, '_rename', racing)
    with pytest.raises(ValueError, match='displaced data retained'):
        resolve_project(registry, project['id'], 1, transaction,
                        decision['token'], {'main.py': operation})
    assert retained.read_bytes() == b'late editor save\n'
    assert any(path.read_bytes() == b'new user edit during resolution\n'
               for path in (source / '.bigbrain-recovery').rglob('*') if path.is_file())
    assert project_transactions(registry, project)[0]['state'] == 'conflict'


def test_interrupted_resolution_uses_existing_rollback(tmp_path, monkeypatch):
    from bigbrain.project_transaction import ProjectTransaction
    from bigbrain.local_project_recovery import recover_project
    source, registry, project, transaction, operation, retained = conflict(tmp_path)
    decision = inspect_resolution(registry, project['id'], 1, transaction)
    original = ProjectTransaction._save
    class Interrupted(BaseException):
        pass
    def crash_after_publication(self, state):
        if (source / 'main.py').read_bytes() == b'late editor save\n':
            raise Interrupted()
        return original(self, state)
    monkeypatch.setattr(ProjectTransaction, '_save', crash_after_publication)
    with pytest.raises(Interrupted):
        resolve_project(registry, project['id'], 1, transaction,
                        decision['token'], {'main.py': operation})
    monkeypatch.setattr(ProjectTransaction, '_save', original)
    result = recover_project(registry, project['id'], 1, transaction)
    assert result['state'] == 'rolled_back'
    assert (source / 'main.py').read_bytes() == b'candidate\n'
    assert retained.read_bytes() == b'late editor save\n'


def test_multi_file_choices_are_complete_and_path_bound(tmp_path):
    source = tmp_path / 'multi'
    source.mkdir()
    registry = ProjectRegistry(tmp_path / 'state' / 'registry.json')
    for name in ('main.py', 'helper.py'):
        (source / name).write_bytes(b'original\n')
    project = registry.attach(source, ('read', 'write'))
    result = apply_patch_set(registry, project['id'], 1, [{
        'path': name, 'sha256': hashlib.sha256(b'original\n').hexdigest(),
        'content': 'candidate\n'} for name in ('main.py', 'helper.py')])
    transaction = result['transactionId']
    journal = registry.path.parent / 'transactions' / (transaction + '.json')
    operations = {item['path']: item for item in json.loads(journal.read_text())['publications']}
    (source / operations['main.py']['preserved']).write_bytes(b'editor version\n')
    decision = inspect_resolution(registry, project['id'], 1, transaction)
    with pytest.raises(ValueError, match='another path'):
        resolve_project(registry, project['id'], 1, transaction, decision['token'], {
            'main.py': operations['helper.py']['id'], 'helper.py': 'current'})
    result = resolve_project(registry, project['id'], 1, transaction, decision['token'], {
        'main.py': operations['main.py']['id'], 'helper.py': 'current'})
    assert result['state'] == 'committed'
    assert (source / 'main.py').read_bytes() == b'editor version\n'
    assert (source / 'helper.py').read_bytes() == b'candidate\n'
