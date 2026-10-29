"""Persistent local project grants and descriptor-scoped file access."""

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import stat
import tempfile
import uuid


RIGHTS = frozenset({'read', 'write', 'execute', 'delete', 'install', 'network', 'transmit'})
EXCLUDED = frozenset({'node_modules', '__pycache__', 'venv', 'dist', 'build',
                      'credentials', 'credentials.json', 'id_rsa', 'id_ed25519'})
SENSITIVE_NAME = re.compile(
    r'(?:^|[._-])(?:secrets?|credentials?|passwords?|private.?key|tokens?)(?:[._-]|$)', re.I)


class ProjectAccessError(ValueError):
    """A project operation exceeded its current grant."""


def default_registry():
    """Use the configured per-user metadata store outside project sources."""
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local' / 'state'))
    root = Path(os.environ.get('BIGBRAIN_LOCAL_PROJECTS_DIR', state / 'bigbrain' / 'local-projects'))
    return ProjectRegistry(root / 'registry.json')


class ProjectRegistry:
    """Serialize registry mutations across processes using a sidecar lock."""

    def __init__(self, path):
        self.path = Path(path).absolute()

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(str(self.path) + '.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            records = json.loads(self.path.read_text()) if self.path.exists() else {}
            before = json.dumps(records, sort_keys=True)
            yield records
            if json.dumps(records, sort_keys=True) == before:
                return
            fd, name = tempfile.mkstemp(dir=self.path.parent)
            try:
                with os.fdopen(fd, 'w') as stream:
                    json.dump(records, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, self.path)
            finally:
                Path(name).unlink(missing_ok=True)

    def attach(self, selected_root, rights=('read',)):
        """Register a root supplied by the trusted chooser boundary."""
        rights = set(rights)
        if rights - RIGHTS or 'read' not in rights:
            raise ProjectAccessError('Invalid project rights')
        root = Path(selected_root).resolve(strict=True)
        if not root.is_dir() or root == Path(root.anchor):
            raise ProjectAccessError('Choose a project directory')
        storage = self.path.parent.resolve()
        if root == storage or root in storage.parents:
            raise ProjectAccessError('Project registry storage must be outside the attached source directory')
        info = root.stat()
        record = dict(id=str(uuid.uuid4()), root=str(root), name=root.name,
                      device=info.st_dev, inode=info.st_ino, revision=1,
                      rights=sorted(rights), state='attached')
        with self._locked() as records:
            for existing in records.values():
                other = Path(existing['root'])
                if existing['state'] == 'attached' and (
                        root == other or root in other.parents or other in root.parents):
                    raise ProjectAccessError('An overlapping project is already attached')
            records[record['id']] = record
        return record

    def get(self, project_id):
        with self._locked() as records:
            if project_id not in records:
                raise ProjectAccessError('Unknown project')
            return dict(records[project_id])

    def list(self):
        with self._locked() as records:
            return [record for record in records.values() if record.get('origin') != 'runtime_snapshot']

    def create_snapshot(self, project_id, revision, *, allowed_versions=None):
        """Create a runtime-owned copy with immutable source-grant provenance."""
        from .local_project_runner import copy_project
        source = self.get(project_id)
        if source.get('origin') == 'runtime_snapshot':
            raise ProjectAccessError('A runtime snapshot requires an attached source project')
        runs = self.path.parent / 'runs'
        runs.mkdir(parents=True, exist_ok=True, mode=0o700)
        root = Path(tempfile.mkdtemp(prefix='project-', dir=runs))
        try:
            observed, _, _ = copy_project(ProjectFiles(self, project_id, revision), root,
                                          allowed_versions=allowed_versions)
            info = root.stat()
            record = dict(id=str(uuid.uuid4()), root=str(root), name=source['name'],
                          device=info.st_dev, inode=info.st_ino, revision=1,
                          rights=list(source['rights']), state='attached', origin='runtime_snapshot',
                          source_project_id=project_id, source_revision=revision,
                          source_versions={path: hashlib.sha256(data).hexdigest()
                                           for path, data in observed.items()})
            with self._locked() as records:
                current = records.get(project_id)
                if current is None or current['revision'] != revision or current['state'] != 'attached':
                    raise ProjectAccessError('Source grant changed during snapshot creation')
                records[record['id']] = record
            return record
        except Exception:
            import shutil
            shutil.rmtree(root)
            raise

    def change(self, project_id, revision, *, rights=None, state=None):
        with self._locked() as records:
            record = records.get(project_id)
            if record is None or record['revision'] != revision:
                raise ProjectAccessError('Project grant changed')
            if rights is not None:
                if set(rights) - RIGHTS:
                    raise ProjectAccessError('Invalid project rights')
                record['rights'] = sorted(set(rights))
            if state is not None:
                if state not in {'attached', 'revoked', 'detached'}:
                    raise ProjectAccessError('Invalid project state')
                record['state'] = state
            record['revision'] += 1
            return dict(record)

    def restore(self, project_id, revision, *, selected_root=None):
        """Renew access to the same directory identity after revocation or relocation."""
        with self._locked() as records:
            record = records.get(project_id)
            if record is None or record['revision'] != revision or record.get('origin') == 'runtime_snapshot':
                raise ProjectAccessError('Project grant changed')
            root = Path(selected_root).resolve(strict=True) if selected_root is not None else Path(record['root'])
            fd = _open_root(root)
            try:
                info = os.fstat(fd)
                if (info.st_dev, info.st_ino) != (record['device'], record['inode']):
                    raise ProjectAccessError('Selected folder has a different project identity')
            finally:
                os.close(fd)
            for other in records.values():
                if other['id'] == project_id or other['state'] != 'attached':
                    continue
                other_root = Path(other['root'])
                if root == other_root or root in other_root.parents or other_root in root.parents:
                    raise ProjectAccessError('An overlapping project is already attached')
            storage = self.path.parent.resolve()
            if root == storage or root in storage.parents:
                raise ProjectAccessError('Project registry storage must be outside the attached source directory')
            record.update(root=str(root), state='attached', revision=record['revision'] + 1)
            return dict(record)

    def selection(self, session_id, *, project_id=None, update=False):
        """Persist conversation selection independently of project grants."""
        if not isinstance(session_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', session_id):
            raise ProjectAccessError('Invalid conversation identity')
        if update and project_id is not None:
            project = self.get(project_id)
            if project['state'] != 'attached':
                raise ProjectAccessError('Project is detached or revoked')
        selections = ProjectRegistry(self.path.with_name('selections.json'))
        with selections._locked() as records:
            if update:
                if project_id is None:
                    records.pop(session_id, None)
                else:
                    records[session_id] = project_id
            return records.get(session_id)

    @contextmanager
    def access(self, project_id, revision, right, *, environment=False):
        # Hold the registry lock through I/O so revocation has a definite boundary.
        with self._locked() as records:
            record = records.get(project_id)
            if (record is None or record['revision'] != revision
                    or record['state'] != 'attached' or right not in record['rights']):
                raise ProjectAccessError('Project grant unavailable or changed')
            if right in {'write', 'execute', 'transmit'}:
                from .local_project_recovery import project_transactions
                from .project_transaction import active_transaction
                own = active_transaction.get()
                own_id = Path(own).stem if own else None
                if any(transaction['id'] != own_id for transaction in project_transactions(self, record)):
                    raise ProjectAccessError('Project transaction recovery is required')
            source = None
            if record.get('origin') == 'runtime_snapshot':
                source = records.get(record.get('source_project_id'))
                if (source is None or source['revision'] != record.get('source_revision')
                        or source['state'] != 'attached' or right not in source['rights']
                        or source.get('origin') == 'runtime_snapshot'):
                    raise ProjectAccessError('Snapshot source grant unavailable or changed')
                try:
                    source_fd = _open_root(source['root'])
                except OSError as exc:
                    raise ProjectAccessError('Snapshot source directory unavailable') from exc
                try:
                    identity = os.fstat(source_fd)
                    if (identity.st_dev, identity.st_ino) != (source['device'], source['inode']):
                        raise ProjectAccessError('Snapshot source directory identity changed')
                finally:
                    os.close(source_fd)
            effective = source if environment and source is not None else record
            try:
                fd = _open_root(effective['root'])
            except OSError as exc:
                raise ProjectAccessError('Project directory unavailable') from exc
            try:
                info = os.fstat(fd)
                if (info.st_dev, info.st_ino) != (effective['device'], effective['inode']):
                    raise ProjectAccessError('Project directory identity changed')
                yield fd
            finally:
                os.close(fd)


def _parts(path):
    if not isinstance(path, str) or '\\' in path or '\x00' in path:
        raise ProjectAccessError('Invalid project path')
    parts = path.split('/')
    if PurePosixPath(path).is_absolute() or any(
            p in {'', '.', '..'} or p.startswith('.') or p in EXCLUDED or SENSITIVE_NAME.search(p)
            or p.endswith(('.pem', '.key')) for p in parts):
        raise ProjectAccessError('Excluded project path')
    return parts


def _open_root(path):
    """Pin every root component to reject ancestor symlink substitution."""
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in Path(path).parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        result, fd = fd, None
        return result
    finally:
        if fd is not None:
            os.close(fd)


@contextmanager
def _parent(root_fd, path):
    parts = _parts(path)
    fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd, parts[-1]
    finally:
        os.close(fd)


class ProjectFiles:
    """Read and replace regular files through an explicit project grant."""

    def __init__(self, registry, project_id, revision):
        self.registry, self.project_id, self.revision = registry, project_id, revision

    def read(self, path, limit=512_000):
        if type(limit) is not int or limit < 1:
            raise ProjectAccessError('Invalid project read limit')
        with self.registry.access(self.project_id, self.revision, 'read') as root:
            with _parent(root, path) as (parent, name):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                with os.fdopen(fd, 'rb') as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise ProjectAccessError('A single-link regular file is required')
                    data = stream.read(min(limit, 4_000_000) + 1)
                    if len(data) > min(limit, 4_000_000):
                        raise ProjectAccessError('Project read exceeds size limit')
                    after = os.fstat(stream.fileno())
                    if (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
                            after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise ProjectAccessError('Project source changed during read')
                    return data

    def list(self, path=''):
        """List bounded visible children using the read grant."""
        with self.registry.access(self.project_id, self.revision, 'read') as root:
            fd = os.dup(root)
            try:
                for component in _parts(path) if path else []:
                    child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=fd)
                    os.close(fd)
                    fd = child
                entries = []
                with os.scandir(fd) as children:
                    for scanned, child in enumerate(children):
                        if scanned >= 2000:
                            raise ProjectAccessError('Project directory exceeds listing limit')
                        try:
                            _parts(child.name)
                            info = child.stat(follow_symlinks=False)
                        except (ProjectAccessError, FileNotFoundError):
                            continue
                        directory = stat.S_ISDIR(info.st_mode)
                        if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                            continue
                        entries.append({'name': child.name,
                                        'path': '/'.join(filter(None, (path, child.name))),
                                        'type': 'folder' if directory else 'file',
                                        'size': info.st_size if not directory else None})
                return sorted(entries, key=lambda entry: (entry['type'] != 'folder', entry['name']))
            finally:
                os.close(fd)

    def write(self, path, data, expected_sha256):
        """Replace a versioned file; None expects an absent destination."""
        if not isinstance(data, bytes) or len(data) > 4_000_000:
            raise ProjectAccessError('Invalid project write')
        with self.registry.access(self.project_id, self.revision, 'write') as root:
            with _parent(root, path) as (parent, name):
                try:
                    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                except FileNotFoundError:
                    current = None
                    mode = 0o600
                else:
                    with os.fdopen(fd, 'rb') as stream:
                        info = os.fstat(stream.fileno())
                        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 4_000_000:
                            raise ProjectAccessError('Invalid project destination')
                        current = hashlib.sha256(stream.read()).hexdigest()
                        mode = stat.S_IMODE(info.st_mode)
                if current != expected_sha256:
                    raise ProjectAccessError('Project file changed concurrently')
                temporary = '.bigbrain-' + uuid.uuid4().hex
                try:
                    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                                 mode, dir_fd=parent)
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.rename(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
                    os.fsync(parent)
                finally:
                    try:
                        os.unlink(temporary, dir_fd=parent)
                    except FileNotFoundError:
                        pass
