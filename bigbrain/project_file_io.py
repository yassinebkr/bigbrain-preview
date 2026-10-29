"""Descriptor-relative transaction reads and atomic file replacement."""

from contextlib import contextmanager
import hashlib
import os
import secrets
import stat

from .execution_target import relative_path


@contextmanager
def parent_directory(target, path, *, create=False):
    target.file(path)
    relative_path(path)
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in target.directory.parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        identity = os.fstat(descriptor)
        if (identity.st_dev, identity.st_ino) != (target.device, target.inode):
            raise ValueError('Project directory identity changed')
        for component in path.split('/')[:-1]:
            if create:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor, path.split('/')[-1]
    finally:
        os.close(descriptor)


def read_at(parent, name):
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    except FileNotFoundError:
        return None, 0o600
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 4_000_000:
            raise ValueError('Transaction requires a bounded regular single-link file')
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            data = stream.read(4_000_001)
        after = os.fstat(descriptor)
        if (len(data) > 4_000_000 or
                (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError('Transaction source changed during read')
        return data, before.st_mode & 0o777
    finally:
        os.close(descriptor)


def read_source(target, path):
    try:
        with parent_directory(target, path) as (parent, name):
            return read_at(parent, name)
    except FileNotFoundError:
        return None, 0o600


def replace_source(target, path, data, mode, expected):
    """Recheck the published version after durable journal intent is recorded."""
    with parent_directory(target, path, create=data is not None) as (parent, name):
        current, _ = read_at(parent, name)
        version = hashlib.sha256(current).hexdigest() if current is not None else None
        if version != expected:
            raise ValueError(f'{path}: source changed before atomic replacement')
        if data is None:
            if current is not None:
                os.unlink(name, dir_fd=parent)
            os.fsync(parent)
            return
        temporary = '.bigbrain-write-' + secrets.token_hex(16)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             mode, dir_fd=parent)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fchmod(stream.fileno(), mode)
                os.fsync(stream.fileno())
            # Resolve the parent again immediately before publication. A changed
            # ancestor prevents the replacement from using a stale directory.
            with parent_directory(target, path) as (fresh, _):
                a, b = os.fstat(parent), os.fstat(fresh)
                if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
                    raise ValueError('Publication directory changed')
            latest, _ = read_at(parent, name)
            if (hashlib.sha256(latest).hexdigest() if latest is not None else None) != expected:
                raise ValueError(f'{path}: source changed during publication')
            os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
