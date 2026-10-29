"""Persistent local project grants and descriptor-scoped file access."""

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import uuid


RIGHTS = frozenset({'read', 'write', 'execute', 'delete', 'install', 'network', 'transmit'})
EXCLUDED = frozenset({'node_modules', '__pycache__', 'venv', 'dist', 'build',
                      'credentials', 'credentials.json', 'id_rsa', 'id_ed25519'})


class ProjectAccessError(ValueError):
    """A project operation exceeded its current grant."""


class ProjectRegistry:
    """Serialize registry mutations across processes using a sidecar lock."""

    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(str(self.path) + '.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            records = json.loads(self.path.read_text()) if self.path.exists() else {}
            yield records
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
        info = root.stat()
        record = dict(id=str(uuid.uuid4()), root=str(root), name=root.name,
                      device=info.st_dev, inode=info.st_ino, revision=1,
                      rights=sorted(rights), state='attached')
        with self._locked() as records:
            records[record['id']] = record
        return record

    def get(self, project_id):
        with self._locked() as records:
            if project_id not in records:
                raise ProjectAccessError('Unknown project')
            return dict(records[project_id])

    def list(self):
        with self._locked() as records:
            return list(records.values())

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

    @contextmanager
    def access(self, project_id, revision, right):
        # Hold the registry lock through I/O so revocation has a definite boundary.
        with self._locked() as records:
            record = records.get(project_id)
            if (record is None or record['revision'] != revision
                    or record['state'] != 'attached' or right not in record['rights']):
                raise ProjectAccessError('Project grant unavailable or changed')
            try:
                fd = os.open(record['root'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            except OSError as exc:
                raise ProjectAccessError('Project directory unavailable') from exc
            try:
                info = os.fstat(fd)
                if (info.st_dev, info.st_ino) != (record['device'], record['inode']):
                    raise ProjectAccessError('Project directory identity changed')
                yield fd
            finally:
                os.close(fd)


def _parts(path):
    if not isinstance(path, str) or '\\' in path or '\x00' in path:
        raise ProjectAccessError('Invalid project path')
    parts = path.split('/')
    if PurePosixPath(path).is_absolute() or any(
            p in {'', '.', '..'} or p.startswith('.') or p in EXCLUDED
            or p.endswith(('.pem', '.key')) for p in parts):
        raise ProjectAccessError('Excluded project path')
    return parts


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
                    return data

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
