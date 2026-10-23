"""Recoverable, scoped write journal. Not a filesystem/OS sandbox.

Rollback restores only our recorded writes and refuses concurrent user edits.
Journals survive crashes; unresolved journals block overlapping project runs.
"""
import base64
from contextvars import ContextVar
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from .execution_target import ExecutionTarget, relative_path

active_transaction = ContextVar('project_transaction', default=None)


def _hash(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _tree_hash(directory):
    if not directory.exists():
        return None
    result, size, count = hashlib.sha256(), 0, 0
    for base, dirs, files in os.walk(directory, followlinks=False):
        dirs.sort()
        for name in sorted(dirs + files):
            path = Path(base) / name
            if path.is_symlink():
                raise ValueError('Build tree contains a symlink')
            if not path.is_file():
                continue
            count += 1
            result.update(path.relative_to(directory).as_posix().encode() + b'\0')
            with open(path, 'rb') as stream:
                while chunk := stream.read(65536):
                    size += len(chunk)
                    if size > 128_000_000 or count > 10000:
                        raise ValueError('Build tree fingerprint budget exceeded')
                    result.update(chunk)
    return result.hexdigest()


def _read(path):
    if not path.exists() and not path.is_symlink():
        return None
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        import stat
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('Transaction requires regular files')
        if os.fstat(fd).st_size > 4_000_000:
            raise ValueError('Transaction file exceeds snapshot budget')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            return stream.read()
    finally:
        os.close(fd)


def _replace(path, data, mode=0o600):
    if data is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.bigbrain-write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class ProjectTransaction:
    def __init__(self, journal):
        self.journal = Path(journal)

    @classmethod
    def begin(cls, target, paths):
        target.validate()
        root = Path(target.root) / '.bigbrain-transactions'
        if root.is_symlink():
            raise ValueError('Transaction journal directory is a symlink')
        root.mkdir(exist_ok=True)
        # Serialize reservation across plans/processes, not just asyncio tasks.
        with open(root / 'registry.lock', 'a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            for previous in root.glob('*.json'):
                state = json.loads(previous.read_text())
                if state['target']['path'] == target.path and state['state'] in {'open', 'cancelling', 'conflict'}:
                    if state['state'] in {'open', 'cancelling'} and state.get('pid'):
                        try:
                            os.kill(state['pid'], 0)
                        except ProcessLookupError:
                            # A crashed build may have orphan child processes.
                            # Do not restore its output until explicitly recovered.
                            recovery = cls(previous).finish() if not state.get('trees') else {'state': 'recovery_required'}
                            if recovery['state'] == 'rolled_back':
                                continue
                        except PermissionError:
                            pass
                    raise ValueError(f'Unresolved project transaction: {previous.name}; recovery required')
            files = {}
            for path in sorted(set(paths) | {'.project.json'}):
                relative_path(path)
                file = target.file(path)
                raw = _read(file)
                files[path] = {'before': base64.b64encode(raw).decode() if raw is not None else None,
                    'after': _hash(raw), 'written': False,
                    'mode': file.stat().st_mode & 0o777 if raw is not None else 0o600}
            journal = root / (uuid.uuid4().hex + '.json')
            _replace(journal, json.dumps({'state': 'open', 'target': target.to_payload(),
                'files': files, 'created_dirs': [], 'pid': os.getpid()}).encode())
        return cls(journal)

    def _locked(self, operation):
        with open(str(self.journal) + '.lock', 'a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(self.journal.read_text())
            return operation(state)

    def _save(self, state):
        _replace(self.journal, json.dumps(state).encode())

    def fence(self):
        def fence(state):
            if state['state'] == 'open':
                state['state'] = 'cancelling'
                self._save(state)
        self._locked(fence)

    def reserve(self, target, path, expected):
        """Journal a discovered implementation path before its first write.

        Callers enforce the approved project-level maintenance policy. This does
        not grant arbitrary paths: target identity, revision and lifecycle still
        match, and the original bytes are durably recorded before any mutation.
        """
        def reserve(state):
            if state['state'] != 'open' or state['target'] != target.to_payload():
                raise ValueError('Transaction is closed or belongs to another target')
            relative_path(path)
            destination = target.file(path)
            raw = _read(destination)
            if _hash(raw) != expected:
                raise ValueError(f'{path}: concurrent source change before reservation')
            if path in state['files']:
                if state['files'][path]['after'] != expected:
                    raise ValueError(f'{path}: concurrent transaction change')
                return
            state['files'][path] = {'before': base64.b64encode(raw).decode() if raw is not None else None,
                'after': expected, 'written': False,
                'mode': destination.stat().st_mode & 0o777 if raw is not None else 0o600}
            self._save(state)
        self._locked(reserve)

    def prepare_build_tree(self, project, path='dist'):
        """Retain the old production build by rename; never recursively delete it."""
        def prepare(state):
            target = ExecutionTarget(**state['target'])
            if state['state'] != 'open' or Path(project) != target.directory or path != 'dist':
                raise ValueError('Unapproved build tree transaction')
            trees = state.setdefault('trees', {})
            if path in trees:
                return
            destination = target.file(path)
            if destination.exists() and not destination.is_dir():
                raise ValueError('Build tree must be a directory')
            backup = self.journal.with_suffix('.dist-before')
            if backup.exists():
                raise ValueError('Build backup already exists')
            trees[path] = {'backup': str(backup), 'existed': destination.exists(), 'before_version': _tree_hash(destination)}
            self._save(state)
            if destination.exists():
                os.replace(destination, backup)
        self._locked(prepare)

    def seal_build_tree(self, project):
        def seal(state):
            target = ExecutionTarget(**state['target'])
            if state['state'] != 'open' or Path(project) != target.directory:
                raise ValueError('Closed build transaction')
            for path, tree in state.get('trees', {}).items():
                tree['after_version'] = _tree_hash(target.file(path))
            self._save(state)
        self._locked(seal)

    def write(self, target, path, data):
        def apply(state):
            if state['state'] != 'open' or state['target'] != target.to_payload():
                raise ValueError('Transaction is closed or belongs to another target')
            if path not in state['files']:
                raise ValueError(f'{path}: outside approved transaction write set')
            destination = target.file(path)
            entry = state['files'][path]
            if _hash(_read(destination)) != entry['after']:
                raise ValueError(f'{path}: concurrent change; transaction write refused')
            parent = destination.parent
            while parent != target.directory and not parent.exists():
                relative = parent.relative_to(target.directory).as_posix()
                if relative not in state['created_dirs']:
                    state['created_dirs'].append(relative)
                parent = parent.parent
            entry.update(after=_hash(data), written=True)
            self._save(state)  # durable intent before the filesystem change
            _replace(destination, data, entry['mode'])
        return self._locked(apply)

    def finish(self, commit=False):
        def finish(state):
            if state['state'] in {'committed', 'rolled_back'}:
                return {'state': state['state'], 'conflicts': []}
            target = ExecutionTarget(**state['target'])
            try:
                target.validate()
            except (OSError, ValueError):
                state['state'] = 'conflict'
                self._save(state)
                return {'state': 'conflict', 'conflicts': ['project destination replaced'], 'journal': str(self.journal)}
            conflicts = []
            for path, entry in state['files'].items():
                if not entry['written']:
                    continue
                try:
                    destination = target.file(path)
                    actual = _hash(_read(destination))
                except (OSError, ValueError):
                    conflicts.append(path)
                    continue
                before = base64.b64decode(entry['before']) if entry['before'] is not None else None
                if actual != entry['after']:
                    if not commit and actual == _hash(before):
                        continue  # crash before write, or already restored
                    conflicts.append(path)
                    continue
                if not commit:
                    _replace(destination, before, entry['mode'])
            if commit:
                for path, tree in state.get('trees', {}).items():
                    if not tree.get('after_version') or _tree_hash(target.file(path)) != tree['after_version']:
                        conflicts.append(path)
            if not commit:
                for path, tree in state.get('trees', {}).items():
                    destination = target.file(path)
                    backup = Path(tree['backup'])
                    if backup != self.journal.with_suffix('.dist-before') or backup.is_symlink():
                        conflicts.append(path)
                        continue
                    if tree['existed'] and not backup.exists():
                        if _tree_hash(destination) != tree.get('before_version'):
                            conflicts.append(path)
                        continue  # crash before initial move, or already restored
                    if tree.get('after_version') and _tree_hash(destination) != tree['after_version']:
                        conflicts.append(path)  # user changed the verified build; preserve it
                        continue
                    # Keep failed build contents recoverable too; no broad deletion.
                    if destination.exists():
                        retained = self.journal.with_name(self.journal.stem + '.dist-after-' + uuid.uuid4().hex)
                        os.replace(destination, retained)
                    if tree['existed']:
                        os.replace(backup, destination)
                for relative in sorted(state['created_dirs'], key=len, reverse=True):
                    try:
                        target.file(relative).rmdir()  # only our empty directories
                    except OSError:
                        pass
            state['state'] = 'conflict' if conflicts else 'committed' if commit else 'rolled_back'
            self._save(state)
            return {'state': state['state'], 'conflicts': conflicts,
                    'journal': str(self.journal)}
        return self._locked(finish)


def write_text(target, path, text):
    transaction = active_transaction.get()
    if transaction:
        return ProjectTransaction(transaction).write(target, path, text.encode('utf-8'))
    destination = target.file(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding='utf-8')


def remove(target, path):
    transaction = active_transaction.get()
    if transaction:
        return ProjectTransaction(transaction).write(target, path, None)
    target.file(path).unlink(missing_ok=True)


def assert_project_idle(root, project):
    """Do not start a preview from uncommitted or conflicted runtime metadata."""
    relative = Path(project).relative_to(root).as_posix()
    for journal in (Path(root) / '.bigbrain-transactions').glob('*.json'):
        state = json.loads(journal.read_text())
        if state['target']['path'] == relative and state['state'] in {'open', 'cancelling', 'conflict'}:
            raise ValueError('Project transaction in progress or recovery required')
