"""Interrupted publication recovery preserves independent user edits."""

import hashlib
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
