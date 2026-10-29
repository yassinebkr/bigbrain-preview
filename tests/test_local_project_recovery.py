"""Interrupted publication recovery preserves independent user edits."""

import hashlib
import json
import os
import pytest

from bigbrain.local_projects import ProjectAccessError, ProjectFiles, ProjectRegistry
from bigbrain.local_project_patches import apply_patch_set
from bigbrain.local_project_recovery import project_transactions, recover_project


def pending(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'main.py').write_text('original\n')
    registry = ProjectRegistry(tmp_path / 'state' / 'registry.json')
    project = registry.attach(source, ('read', 'write', 'execute'))
    result = apply_patch_set(registry, project['id'], 1,
        [{'path': 'main.py', 'sha256': hashlib.sha256(b'original\n').hexdigest(),
          'content': 'candidate\n'}], commit=False)
    return source, registry, project, result['transactionId']


def test_pending_transaction_blocks_new_mutation_until_recovery(tmp_path):
    source, registry, project, transaction = pending(tmp_path)
    assert project_transactions(registry, project)[0]['id'] == transaction
    with pytest.raises(ProjectAccessError, match='recovery'):
        ProjectFiles(registry, project['id'], 1).write('extra.py', b'pass', None)
    result = recover_project(registry, project['id'], 1, transaction)
    assert result['state'] == 'rolled_back'
    assert (source / 'main.py').read_text() == 'original\n'
    assert project_transactions(registry, project) == []


def test_recovery_preserves_concurrent_edit_and_rejects_other_project(tmp_path):
    source, registry, project, transaction = pending(tmp_path)
    (source / 'main.py').write_text('user edit\n')
    result = recover_project(registry, project['id'], 1, transaction)
    assert result['state'] == 'conflict'
    assert (source / 'main.py').read_text() == 'user edit\n'
    other = tmp_path / 'other'
    other.mkdir()
    other_project = registry.attach(other, ('read', 'write'))
    with pytest.raises(ProjectAccessError, match='different project'):
        recover_project(registry, other_project['id'], 1, transaction)


def test_committed_editor_handle_change_blocks_further_execution(tmp_path):
    from bigbrain.project_transaction import ProjectTransaction
    source, registry, project, transaction = pending(tmp_path)
    journal = ProjectTransaction(registry.path.parent / 'transactions' / (transaction + '.json'))
    assert journal.finish(commit=True)['state'] == 'committed'
    record = json.loads(journal.journal.read_text())['publications'][0]
    retained = source / record['preserved']
    with retained.open('r+b', buffering=0) as editor:
        editor.write(b'late independent edit\n')
        editor.truncate()
        os.fsync(editor.fileno())
    pending_recovery = project_transactions(registry, project)
    assert pending_recovery[0]['conflicts'] == ['main.py']
    with pytest.raises(ProjectAccessError, match='recovery'):
        with registry.access(project['id'], project['revision'], 'execute'):
            pass
    assert retained.read_bytes() == b'late independent edit\n'


def test_retained_view_binds_operation_project_and_grant(tmp_path):
    from bigbrain.local_project_recovery import retained_version
    source, registry, project, transaction = pending(tmp_path)
    operation = project_transactions(registry, project)[0]['retainedVersions'][0]['operationId']
    viewed = retained_version(registry, project['id'], 1, transaction, operation)
    assert viewed['content'] == 'original\n'
    assert viewed['sha256'] == hashlib.sha256(b'original\n').hexdigest()
    assert (source / 'main.py').read_text() == 'candidate\n'
    with pytest.raises(ProjectAccessError, match='unavailable'):
        retained_version(registry, project['id'], 1, transaction, 'a' * 32)
    other = tmp_path / 'other'
    other.mkdir()
    other_project = registry.attach(other)
    with pytest.raises(ProjectAccessError, match='different project'):
        retained_version(registry, other_project['id'], 1, transaction, operation)
    registry.change(project['id'], 1, state='revoked')
    with pytest.raises(ProjectAccessError):
        retained_version(registry, project['id'], 1, transaction, operation)
