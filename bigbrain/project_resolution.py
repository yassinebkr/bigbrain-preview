"""Version-bound user choices over recoverable source publication conflicts."""

import base64
import hashlib
import json

from .execution_target import ExecutionTarget
from .project_file_io import read_source, publication_facts, publication_conflicts


def _version(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def resolution_snapshot(state):
    """Fingerprint the journal and the live objects covered by a user decision."""
    target = ExecutionTarget(**state['target'])
    target.validate()
    publication_conflicts(target, state.get('publications', []))
    paths = sorted(path for path, entry in state['files'].items() if entry['written'])
    current = {}
    for path in paths:
        raw, _, identity = read_source(target, path, identity=True)
        current[path] = {'version': _version(raw), 'identity': identity}
    retained = {operation['id']: publication_facts(target, operation)
                for operation in state.get('publications', [])}
    encoded = json.dumps({'journal': state, 'current': current, 'retained': retained},
                         sort_keys=True, separators=(',', ':')).encode()
    return {'token': hashlib.sha256(encoded).hexdigest(), 'current': current,
            'retained': retained, 'files': [{
                'path': path, 'sha256': current[path]['version'],
                'versions': [{'operationId': operation['id'],
                              'sha256': retained[operation['id']]['preserved']['version']}
                             for operation in state.get('publications', [])
                             if operation['path'] == path and operation.get('preserved')
                             and retained[operation['id']]['preserved']['version'] is not None],
            } for path in paths]}


def apply_resolution(transaction, token, choices):
    """Use the publication engine for an approved, complete set of source choices."""
    def apply(state):
        target = ExecutionTarget(**state['target'])
        conflicts = publication_conflicts(target, state.get('publications', []))
        if state['state'] not in {'conflict', 'committed', 'rolled_back'} or (
                state['state'] != 'conflict' and not conflicts):
            raise ValueError('Conflict resolution requires a stopped, conflicted transaction')
        if state.get('trees'):
            raise ValueError('Build-tree recovery requires separate inspection')
        snapshot = resolution_snapshot(state)
        if not isinstance(token, str) or token != snapshot['token']:
            raise ValueError('Recovery versions changed; inspect the conflict again')
        if not isinstance(choices, dict) or set(choices) != set(snapshot['current']):
            raise ValueError('Choose a version for every affected source path')
        selected, baselines = {}, {}
        for path, choice in choices.items():
            raw, mode, identity = read_source(target, path, identity=True)
            if {'version': _version(raw), 'identity': identity} != snapshot['current'][path]:
                raise ValueError('Recovery versions changed; inspect the conflict again')
            baselines[path] = {'before': base64.b64encode(raw).decode() if raw is not None else None,
                               'after': _version(raw), 'written': True, 'mode': mode}
            if choice == 'current':
                continue
            operation = next((item for item in state.get('publications', [])
                              if item['id'] == choice and item['path'] == path
                              and item.get('preserved')), None)
            if operation is None:
                raise ValueError('Selected retained version belongs to another path or operation')
            data, _, identity = read_source(target, operation['preserved'], identity=True)
            if data is None or {'version': _version(data), 'identity': identity} != (
                    snapshot['retained'][operation['id']]['preserved']):
                raise ValueError('Retained version changed; inspect the conflict again')
            selected[path] = data

        # Retain the prior baseline and the exact decision for subsequent audits.
        state.setdefault('resolutions', []).append({'token': token, 'choices': choices,
            'previous_state': state['state'], 'previous_files': state['files'],
            'observations': snapshot})
        for operation in state.get('publications', []):
            operation['status'] = 'acknowledged'
            operation['observed'] = snapshot['retained'][operation['id']]
        state['files'] = baselines
        state['state'] = 'open'
        transaction._save(state)
        for path, data in selected.items():
            entry = state['files'][path]
            expected = entry['after']
            entry['after'] = _version(data)
            transaction._save(state)
            transaction._publish(state, target, path, data, entry['mode'], expected)
    transaction._locked(apply)
    return transaction.finish(commit=True)
