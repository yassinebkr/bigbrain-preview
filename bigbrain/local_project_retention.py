"""Explicit, version-bound release of journal-owned recovery artifacts."""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time

from .execution_target import ExecutionTarget
from .local_projects import ProjectAccessError
from .native_publication import publication_backend
from .project_file_io import RECOVERY_DIRECTORY, read_source, parent_directory, publication_conflicts
from .project_transaction import ProjectTransaction


def retained_journals(registry, record):
    """List retained terminal journals separately from source conflicts."""
    result = []
    for journal in (registry.path.parent / 'transactions').glob('*.json'):
        state = json.loads(journal.read_text())
        target = state.get('target', {})
        if (Path(target.get('root', '')) / target.get('path', '') == Path(record['root'])
                and (target.get('device'), target.get('inode')) == (record['device'], record['inode'])
                and state['state'] in {'committed', 'rolled_back'}
                and state.get('publications') and state.get('retention', {}).get('status') != 'released'):
            result.append({'id': journal.stem, 'state': state.get('retention', {}).get('status', 'retained'),
                           'paths': sorted({item['path'] for item in state['publications']})})
    return result


def _artifact_paths(state, transaction_id):
    paths = {}
    for operation in state.get('publications', []):
        for role in ('candidate', 'preserved'):
            if operation.get(role):
                paths[operation[role]] = (operation['id'], operation['path'])
    for move in state.get('retention', {}).get('moves', []):
        for role in ('original', 'quarantine'):
            paths[move[role]] = (move['operationId'], move['sourcePath'])
    for path, (operation_id, _) in paths.items():
        if not re.fullmatch('[a-f0-9]{32}', operation_id):
            raise ProjectAccessError('Invalid retained operation identity')
        prefix = f'{RECOVERY_DIRECTORY}/{transaction_id}/{operation_id}/'
        if not path.startswith(prefix) or not re.fullmatch(
                r'(candidate(?:\.displaced)?|displaced|release-[a-f0-9]{32})', path[len(prefix):]):
            raise ProjectAccessError('Retained artifact escaped its journal-owned namespace')
    return paths


def retention_snapshot(state, transaction_id):
    target = ExecutionTarget(**state['target'])
    target.validate()
    pending = state.get('retention', {}).get('status') == 'pending'
    conflicts = [] if pending else publication_conflicts(target, state.get('publications', []))
    files = []
    for path, (operation_id, source_path) in sorted(_artifact_paths(state, transaction_id).items()):
        raw, _, identity = read_source(target, path, identity=True)
        if raw is not None:
            files.append({'artifact': path, 'path': source_path, 'operationId': operation_id,
                          'version': hashlib.sha256(raw).hexdigest(), 'identity': identity, 'bytes': len(raw)})
    sources = {}
    for path, entry in state['files'].items():
        if entry.get('written'):
            raw, _, identity = read_source(target, path, identity=True)
            sources[path] = {'version': hashlib.sha256(raw).hexdigest() if raw is not None else None,
                             'identity': identity}
    encoded = json.dumps({'journal': state, 'files': files, 'sources': sources}, sort_keys=True).encode()
    return {'token': hashlib.sha256(encoded).hexdigest(), 'files': files,
            'bytes': sum(item['bytes'] for item in files), 'conflicts': conflicts,
            'eligible': state['state'] in {'committed', 'rolled_back'} and not conflicts
                        and not state.get('trees') and state.get('retention', {}).get('status') != 'released'}


def inspect_retention(registry, project_id, revision, transaction_id):
    from .local_project_recovery import _journal_for
    journal, _ = _journal_for(registry, project_id, transaction_id)
    with registry.access(project_id, revision, 'read'):
        return ProjectTransaction(journal)._locked(lambda state: retention_snapshot(state, journal.stem))


def read_retention(registry, project_id, revision, transaction_id, artifact):
    """Read an inventory member, including a quarantined interrupted release."""
    from .local_project_recovery import _journal_for
    journal, state = _journal_for(registry, project_id, transaction_id)
    paths = _artifact_paths(state, journal.stem)
    if not isinstance(artifact, str) or artifact not in paths:
        raise ProjectAccessError('Artifact belongs to another recovery inventory')
    with registry.access(project_id, revision, 'read'):
        raw, _ = read_source(ExecutionTarget(**state['target']), artifact)
        if raw is None:
            raise ProjectAccessError('Retained artifact is unavailable')
        return {'path': paths[artifact][1], 'content': raw.decode('utf-8'),
                'sha256': hashlib.sha256(raw).hexdigest()}


def _forget_preimages(state):
    """Retain version evidence after explicit release of recovery byte snapshots."""
    groups = [state['files'], *(item['previous_files'] for item in state.get('resolutions', []))]
    for group in groups:
        for entry in group.values():
            if entry.get('before') is not None:
                entry['before_sha256'] = hashlib.sha256(base64.b64decode(entry['before'])).hexdigest()
                entry['before'] = None


def release_retention(registry, project_id, revision, transaction_id, expected, confirmed):
    """Release only the explicitly confirmed inventory; retain partial-work intent."""
    from .local_project_recovery import _journal_for, project_transactions
    if confirmed is not True:
        raise ProjectAccessError('Irreversible recovery release requires explicit confirmation')
    journal, _ = _journal_for(registry, project_id, transaction_id)
    record = registry.get(project_id)
    with registry.access(project_id, revision, 'delete'):
        if any(item['id'] != transaction_id for item in project_transactions(registry, record)):
            raise ProjectAccessError('Resolve other project transactions before recovery release')
        transaction = ProjectTransaction(journal)
        def release(state):
            snapshot = retention_snapshot(state, journal.stem)
            if not snapshot['eligible']:
                raise ProjectAccessError('Resolve source conflicts before recovery release')
            if not isinstance(expected, str) or expected != snapshot['token']:
                raise ProjectAccessError('Recovery inventory changed; inspect it again')
            target = ExecutionTarget(**state['target'])
            backend = publication_backend()
            retention = state.setdefault('retention', {'moves': [], 'releasedBytes': 0})
            retention.update(status='pending', token=expected)
            transaction._save(state)
            deadline = time.monotonic() + 15
            for item in snapshot['files']:
                if time.monotonic() >= deadline:
                    return {'state': 'pending', 'releasedBytes': retention['releasedBytes']}
                quarantine = str(Path(item['artifact']).with_name('release-' + secrets.token_hex(16)))
                move = {'original': item['artifact'], 'quarantine': quarantine,
                        'operationId': item['operationId'], 'sourcePath': item['path'], 'status': 'intent'}
                retention['moves'].append(move)
                transaction._save(state)  # both names remain discoverable after interruption
                parent = (target.directory / item['artifact']).parent
                anchors = {str(target.directory): [target.device, target.inode],
                           str(parent): backend.directory_identity(parent)}
                backend.retire(target.directory / item['artifact'], target.directory / quarantine, anchors=anchors)
                move['status'] = 'retired'
                transaction._save(state)
                backend.release_preserved(target.directory / quarantine,
                    {'version': item['version'], 'identity': item['identity']}, anchors=anchors)
                move['status'] = 'released'
                retention['releasedBytes'] += item['bytes']
                transaction._save(state)
            if retention_snapshot(state, journal.stem)['files']:
                raise ProjectAccessError('Additional retained versions appeared; inspect them again')
            for operation in state.get('publications', []):
                operation['status'] = 'released'
            _forget_preimages(state)
            retention['status'] = 'released'
            transaction._save(state)
            # Remove exclusively named, empty runtime directories; retain foreign entries.
            directories = {str(Path(path).parent) for path in _artifact_paths(state, journal.stem)}
            directories.add(f'{RECOVERY_DIRECTORY}/{journal.stem}')
            for directory in sorted(directories, key=len, reverse=True):
                try:
                    with parent_directory(target, directory) as (parent, name):
                        os.rmdir(name, dir_fd=parent)
                        os.fsync(parent)
                except OSError:
                    pass
            return {'state': 'released', 'releasedBytes': retention['releasedBytes']}
        return transaction._locked(release)
