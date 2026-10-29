"""Publication races preserve user edits and reject swapped directory paths."""

import pytest

from bigbrain.execution_target import ExecutionTarget
from bigbrain.project_transaction import ProjectTransaction


def transaction(tmp_path):
    root = tmp_path / 'project'
    (root / 'src').mkdir(parents=True)
    (root / 'src' / 'main.py').write_text('before\n')
    info = root.stat()
    target = ExecutionTarget('existing', root.name, str(root.parent), info.st_dev, info.st_ino)
    return root, target, ProjectTransaction.begin(target, ['src/main.py'])


def test_edit_after_durable_intent_is_preserved(tmp_path, monkeypatch):
    root, target, journal = transaction(tmp_path)
    original = journal._save
    def save(state):
        original(state)
        if state['files']['src/main.py']['written']:
            (root / 'src/main.py').write_text('concurrent user edit\n')
    monkeypatch.setattr(journal, '_save', save)
    with pytest.raises(ValueError, match='changed before atomic'):
        journal.write(target, 'src/main.py', b'candidate\n')
    assert (root / 'src/main.py').read_text() == 'concurrent user edit\n'
    result = journal.finish()
    assert result['state'] == 'conflict'


def test_parent_symlink_swap_after_intent_cannot_publish_outside(tmp_path, monkeypatch):
    root, target, journal = transaction(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'main.py').write_text('outside\n')
    original = journal._save
    swapped = False
    def save(state):
        nonlocal swapped
        original(state)
        if state['files']['src/main.py']['written'] and not swapped:
            swapped = True
            (root / 'src').rename(root / 'preserved-src')
            (root / 'src').symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(journal, '_save', save)
    with pytest.raises((OSError, ValueError)):
        journal.write(target, 'src/main.py', b'candidate\n')
    assert (outside / 'main.py').read_text() == 'outside\n'
    assert (root / 'preserved-src/main.py').read_text() == 'before\n'
    assert journal.finish()['state'] == 'conflict'


def test_nested_new_file_and_rollback_keep_parent_scope(tmp_path):
    root, target, journal = transaction(tmp_path)
    journal.reserve(target, 'new/sub/module.py', None)
    journal.write(target, 'new/sub/module.py', b'value = 1\n')
    assert (root / 'new/sub/module.py').read_text() == 'value = 1\n'
    assert journal.finish()['state'] == 'rolled_back'
    assert not (root / 'new').exists()
