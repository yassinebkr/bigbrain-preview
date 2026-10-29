"""Real retained objects survive publication races, interruption and late edits."""

import json
import os

import pytest

from bigbrain.execution_target import ExecutionTarget
from bigbrain.native_publication import LinuxPublication
from bigbrain.project_transaction import ProjectTransaction


def setup(tmp_path, paths=('main.py',)):
    root = tmp_path / 'project'
    root.mkdir()
    for path in paths:
        (root / path).write_bytes(b'before\n')
    info = root.stat()
    target = ExecutionTarget('existing', root.name, str(root.parent), info.st_dev, info.st_ino)
    return root, target, ProjectTransaction.begin(target, paths)


def operations(journal):
    return json.loads(journal.journal.read_text())['publications']


def test_edit_inside_final_native_window_is_retained(tmp_path, monkeypatch):
    root, target, journal = setup(tmp_path)
    original = LinuxPublication._rename
    def racing(self, source, destination, flags, anchors=None):
        if flags == 2 and destination == root / 'main.py':
            destination.write_bytes(b'external edit\n')
        return original(self, source, destination, flags, anchors)
    monkeypatch.setattr(LinuxPublication, '_rename', racing)
    with pytest.raises(ValueError, match='displaced data retained'):
        journal.write(target, 'main.py', b'candidate\n')
    record = operations(journal)[0]
    assert (root / record['preserved']).read_bytes() == b'external edit\n'
    assert (root / 'main.py').read_bytes() == b'candidate\n'
    assert journal.finish()['state'] == 'conflict'
    assert (root / record['preserved']).read_bytes() == b'external edit\n'


def test_late_editor_save_after_commit_is_reported(tmp_path):
    root, target, journal = setup(tmp_path)
    with (root / 'main.py').open('r+b', buffering=0) as editor:
        journal.write(target, 'main.py', b'candidate\n')
        assert journal.finish(commit=True)['state'] == 'committed'
        editor.write(b'late editor save\n')
        editor.truncate()
        os.fsync(editor.fileno())
    record = operations(journal)[0]
    assert (root / record['preserved']).read_bytes() == b'late editor save\n'
    assert (root / 'main.py').read_bytes() == b'candidate\n'
    assert journal.finish(commit=True)['state'] == 'conflict'


def test_crash_after_exchange_recovers_from_durable_intent(tmp_path, monkeypatch):
    root, target, journal = setup(tmp_path)
    original = journal._save
    class Interrupted(BaseException):
        pass
    def save(state):
        if (root / 'main.py').read_bytes() == b'candidate\n':
            raise Interrupted()
        original(state)
    monkeypatch.setattr(journal, '_save', save)
    with pytest.raises(Interrupted):
        journal.write(target, 'main.py', b'candidate\n')
    assert operations(journal)[0]['status'] == 'prepared'
    restored = ProjectTransaction(journal.journal).finish()
    assert restored['state'] == 'rolled_back', restored
    assert (root / 'main.py').read_bytes() == b'before\n'
    assert any((root / item['preserved']).read_bytes() == b'candidate\n'
               for item in operations(journal) if item['preserved'])


def test_second_file_failure_rolls_back_first_and_retains_versions(tmp_path, monkeypatch):
    root, target, journal = setup(tmp_path, ('first.py', 'second.py'))
    original = LinuxPublication._rename
    def fail_second(self, source, destination, flags, anchors=None):
        if destination == root / 'second.py':
            raise OSError('injected second-file failure')
        return original(self, source, destination, flags, anchors)
    monkeypatch.setattr(LinuxPublication, '_rename', fail_second)
    journal.write(target, 'first.py', b'first candidate\n')
    with pytest.raises(OSError, match='second-file'):
        journal.write(target, 'second.py', b'second candidate\n')
    assert journal.finish()['state'] == 'rolled_back'
    assert (root / 'first.py').read_bytes() == b'before\n'
    assert (root / 'second.py').read_bytes() == b'before\n'
    assert any((root / item['preserved']).read_bytes() == b'first candidate\n'
               for item in operations(journal) if item['preserved'])


def test_unowned_recovery_directory_is_preserved(tmp_path):
    root, target, journal = setup(tmp_path)
    recovery = root / '.bigbrain-recovery'
    recovery.mkdir(mode=0o700)
    (recovery / 'user.txt').write_bytes(b'keep\n')
    with pytest.raises(ValueError, match='ownership marker'):
        journal.write(target, 'main.py', b'candidate\n')
    assert (root / 'main.py').read_bytes() == b'before\n'
    assert (recovery / 'user.txt').read_bytes() == b'keep\n'


def test_retention_limit_stops_publication(tmp_path, monkeypatch):
    import bigbrain.project_file_io as io
    root, target, journal = setup(tmp_path)
    monkeypatch.setattr(io, 'MAX_RECOVERY_BYTES', 10)
    with pytest.raises(ValueError, match='storage limit'):
        journal.write(target, 'main.py', b'candidate\n')
    assert (root / 'main.py').read_bytes() == b'before\n'


def test_replaced_root_is_refused_by_native_anchors(tmp_path, monkeypatch):
    root, target, journal = setup(tmp_path)
    original = LinuxPublication._rename
    def swap(self, source, destination, flags, anchors=None):
        root.rename(tmp_path / 'moved-project')
        root.mkdir()
        (root / 'main.py').write_bytes(b'unrelated project\n')
        return original(self, source, destination, flags, anchors)
    monkeypatch.setattr(LinuxPublication, '_rename', swap)
    with pytest.raises((OSError, ValueError)):
        journal.write(target, 'main.py', b'candidate\n')
    assert (root / 'main.py').read_bytes() == b'unrelated project\n'
    assert (tmp_path / 'moved-project/main.py').read_bytes() == b'before\n'


def test_standalone_helpers_keep_displaced_versions(tmp_path):
    from bigbrain.project_transaction import write_text, remove
    root, target, journal = setup(tmp_path)
    assert journal.finish()['state'] == 'rolled_back'
    write_text(target, 'main.py', 'replacement\n')
    remove(target, 'main.py')
    assert not (root / 'main.py').exists()
    retained = [file.read_bytes() for file in (root / '.bigbrain-recovery').rglob('*')
                if file.is_file() and file.name != '.owner.json']
    assert b'before\n' in retained
    assert b'replacement\n' in retained


def test_project_files_retains_edit_in_native_window(tmp_path, monkeypatch):
    import hashlib
    from bigbrain.local_projects import ProjectRegistry, ProjectFiles, ProjectAccessError
    root = tmp_path / 'attached'
    root.mkdir()
    (root / 'main.py').write_bytes(b'before\n')
    registry = ProjectRegistry(tmp_path / 'registry' / 'projects.json')
    record = registry.attach(root, ['read', 'write'])
    original = LinuxPublication._rename
    def racing(self, source, destination, flags, anchors=None):
        if flags == 2 and destination == root / 'main.py':
            destination.write_bytes(b'editor save\n')
        return original(self, source, destination, flags, anchors)
    monkeypatch.setattr(LinuxPublication, '_rename', racing)
    with pytest.raises(ProjectAccessError, match='displaced data retained'):
        ProjectFiles(registry, record['id'], 1).write('main.py', b'candidate\n',
            hashlib.sha256(b'before\n').hexdigest())
    assert (root / 'main.py').read_bytes() == b'candidate\n'
    assert any(file.read_bytes() == b'editor save\n'
               for file in (root / '.bigbrain-recovery').rglob('*') if file.is_file())
