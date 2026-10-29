"""Descriptor-relative transaction reads and atomic file replacement."""

from contextlib import contextmanager
import hashlib
import json
import os
import re
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


def read_at(parent, name, *, identity=False):
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    except FileNotFoundError:
        return (None, 0o600, None) if identity else (None, 0o600)
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
        result = (data, before.st_mode & 0o777)
        return (*result, [before.st_dev, before.st_ino]) if identity else result
    finally:
        os.close(descriptor)


def read_source(target, path, *, identity=False):
    try:
        with parent_directory(target, path) as (parent, name):
            return read_at(parent, name, identity=identity)
    except FileNotFoundError:
        return (None, 0o600, None) if identity else (None, 0o600)


RECOVERY_DIRECTORY = '.bigbrain-recovery'
MAX_RECOVERY_BYTES = 256 * 1024 * 1024
MAX_RECOVERY_FILES = 4096


def _private_directory(descriptor):
    info = os.fstat(descriptor)
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('Recovery storage requires a private directory owned by the current user')


def _recovery_usage(descriptor, depth=0):
    if depth > 3:
        raise ValueError('Unexpected recovery storage depth')
    size, count = 0, 0
    for name in os.listdir(descriptor):
        info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            try:
                extra_size, extra_count = _recovery_usage(child, depth + 1)
                size, count = size + extra_size, count + extra_count
            finally:
                os.close(child)
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            size, count = size + info.st_size, count + 1
        else:
            raise ValueError('Recovery storage contains an unsupported link or file type')
        if size > MAX_RECOVERY_BYTES or count > MAX_RECOVERY_FILES:
            raise ValueError('Recovery storage limit reached; resolve retained versions')
    return size, count


def prepare_publication(target, path, data, mode, expected, transaction_id):
    """Reserve owned recovery storage and return a serializable native intent."""
    from .native_publication import publication_backend
    if path.split('/')[0] == RECOVERY_DIRECTORY or not re.fullmatch('[a-f0-9]{32}', transaction_id):
        raise ValueError('Invalid publication scope')
    raw, _, before_identity = read_source(target, path, identity=True)
    if (hashlib.sha256(raw).hexdigest() if raw is not None else None) != expected:
        raise ValueError(f'{path}: source changed before atomic replacement')
    backend = publication_backend()
    with parent_directory(target, RECOVERY_DIRECTORY) as (root, name):
        created = False
        try:
            os.mkdir(name, 0o700, dir_fd=root)
            created = True
            os.fsync(root)
        except FileExistsError:
            pass
        store = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        try:
            _private_directory(store)
            owner = {'version': 1, 'device': target.device, 'inode': target.inode}
            if created:
                descriptor = os.open('.owner.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=store)
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(json.dumps(owner, sort_keys=True).encode())
                    stream.flush()
                    os.fsync(stream.fileno())
                os.fsync(store)
            marker, _ = read_at(store, '.owner.json')
            if marker is None or json.loads(marker) != owner:
                raise ValueError('Recovery directory ownership marker does not match the project')
            size, count = _recovery_usage(store)
            if size + len(data or b'') + len(raw or b'') > MAX_RECOVERY_BYTES or count + 2 > MAX_RECOVERY_FILES:
                raise ValueError('Recovery storage limit reached; resolve retained versions')
            try:
                os.mkdir(transaction_id, 0o700, dir_fd=store)
                os.fsync(store)
            except FileExistsError:
                pass
            group = os.open(transaction_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=store)
            try:
                _private_directory(group)
                operation = secrets.token_hex(16)
                os.mkdir(operation, 0o700, dir_fd=group)
                os.fsync(group)
            finally:
                os.close(group)
        finally:
            os.close(store)
    operation_root = f'{RECOVERY_DIRECTORY}/{transaction_id}/{operation}'
    candidate = operation_root + '/candidate'
    with parent_directory(target, path, create=data is not None) as (parent, _), parent_directory(
            target, candidate) as (recovery, name):
        if os.fstat(parent).st_dev != os.fstat(recovery).st_dev:
            raise ValueError('Recovery storage and source must reside on the same volume')
        if data is not None:
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 mode, dir_fd=recovery)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fchmod(stream.fileno(), mode)
                os.fsync(stream.fileno())
            os.fsync(recovery)
    candidate_path = target.directory / candidate
    preserved = (backend.preservation_path(candidate_path).relative_to(target.directory).as_posix()
                 if data is not None and expected is not None else
                 operation_root + '/displaced' if expected is not None else None)
    anchors = {str(directory): backend.directory_identity(directory) for directory in
               {target.directory, (target.directory / path).parent, candidate_path.parent}}
    return {'id': operation, 'path': path, 'status': 'prepared', 'platform': backend.platform,
        'kind': 'retire' if data is None else 'create' if expected is None else 'replace',
        'before': expected, 'after': hashlib.sha256(data).hexdigest() if data is not None else None,
        'before_identity': before_identity, 'candidate': candidate if data is not None else None,
        'candidate_identity': read_source(target, candidate, identity=True)[2] if data is not None else None,
        'preserved': preserved, 'anchors': anchors}


def publication_facts(target, operation):
    """Observe recorded versions through the existing scoped filesystem adapter."""
    facts = {}
    for role in ('path', 'candidate', 'preserved'):
        path = operation.get(role)
        if path is None:
            facts[role] = {'version': None, 'identity': None}
            continue
        raw, _, identity = read_source(target, path, identity=True)
        facts[role] = {'version': hashlib.sha256(raw).hexdigest() if raw is not None else None,
                       'identity': identity}
    return facts


def execute_publication(target, operation):
    """Apply durable intent and retain the actual displaced object on conflict."""
    from .native_publication import publication_backend
    backend = publication_backend()
    if backend.platform != operation['platform']:
        raise ValueError('Publication recovery requires its recorded platform adapter')
    facts = publication_facts(target, operation)
    if facts['path']['version'] != operation['before']:
        raise ValueError('Source changed before native publication')
    if operation['candidate'] and (facts['candidate']['version'] != operation['after'] or
            facts['candidate']['identity'] != operation['candidate_identity']):
        raise ValueError('Publication candidate changed')
    source = target.directory / operation['path']
    candidate = target.directory / operation['candidate'] if operation['candidate'] else None
    preserved = target.directory / operation['preserved'] if operation['preserved'] else None
    kwargs = {'anchors': operation['anchors']}
    if operation['kind'] == 'replace':
        backend.replace_preserving(source, candidate, preserved, **kwargs)
    elif operation['kind'] == 'create':
        backend.create(source, candidate, **kwargs)
    else:
        backend.retire(source, preserved, **kwargs)
    observed = publication_facts(target, operation)
    operation['observed'] = observed
    operation['status'] = 'applied'
    if (observed['path']['version'] != operation['after'] or
            (preserved is not None and observed['preserved']['version'] != operation['before'])):
        operation['status'] = 'conflict'
        raise ValueError('Concurrent publication conflict; displaced data retained')


def publication_conflicts(target, operations):
    """Reconcile durable intents and detect later writes to retained objects."""
    conflicts = []
    for operation in operations:
        try:
            facts = publication_facts(target, operation)
            if operation['status'] == 'conflict':
                conflicts.append(operation['path'])
                continue
            if operation['status'] == 'prepared':
                if operation['kind'] == 'retire':
                    applied = facts['path']['identity'] is None and facts['preserved']['identity'] is not None
                    untouched = facts['preserved']['identity'] is None
                else:
                    applied = facts['path']['identity'] == operation['candidate_identity']
                    untouched = facts['candidate']['identity'] == operation['candidate_identity']
                if applied:
                    operation['status'] = 'applied'
                    operation['observed'] = facts
                    if (facts['path']['version'] != operation['after'] or
                            (operation['preserved'] and facts['preserved']['version'] != operation['before'])):
                        operation['status'] = 'conflict'
                elif untouched:
                    operation['status'] = 'unapplied'
                else:
                    operation['status'] = 'conflict'
            if operation['status'] == 'conflict':
                conflicts.append(operation['path'])
            elif operation['status'] == 'applied' and operation['preserved']:
                previous = operation['observed']['preserved']
                if facts['preserved'] != previous:
                    operation['status'] = 'conflict'
                    conflicts.append(operation['path'])
        except (OSError, ValueError, KeyError, TypeError):
            conflicts.append(operation.get('path', 'unreadable retained publication'))
    return sorted(set(conflicts))
