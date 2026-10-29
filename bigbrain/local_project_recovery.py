"""Project-scoped recovery views backed by the shared transaction journal."""

import json
from pathlib import Path
import re

from .local_projects import ProjectAccessError
from .project_transaction import active_transaction, ProjectTransaction
from .execution_target import ExecutionTarget
from .project_file_io import publication_conflicts, read_source, RECOVERY_DIRECTORY


def project_transactions(registry, record):
    """Expose transaction identity and affected paths without source snapshots."""
    root = Path(record['root'])
    results = []
    for journal in (registry.path.parent / 'transactions').glob('*.json'):
        state = json.loads(journal.read_text())
        target = state.get('target', {})
        if Path(target.get('root', '')) / target.get('path', '') != root:
            continue
        conflicts = []
        retention_pending = state.get('retention', {}).get('status') == 'pending'
        if state.get('publications') and not retention_pending:
            conflicts = publication_conflicts(ExecutionTarget(**target), state['publications'])
        if state.get('state') in {'open', 'cancelling', 'conflict'} or conflicts or retention_pending:
            results.append({'id': journal.stem, 'state': 'retention_pending' if retention_pending else 'conflict' if conflicts else state['state'],
                            'conflicts': conflicts,
                            'retainedVersions': [{'operationId': operation['id'], 'path': operation['path'],
                                'state': operation['status'], 'preserved': operation['preserved']}
                                for operation in state.get('publications', []) if operation['preserved']],
                            'paths': sorted(path for path, entry in state.get('files', {}).items()
                                            if entry.get('written'))})
    return results


def _journal_for(registry, project_id, transaction_id):
    """Bind a recovery journal to its attached project's filesystem identity."""
    if not isinstance(transaction_id, str) or not re.fullmatch('[a-f0-9]{32}', transaction_id):
        raise ProjectAccessError('Invalid project transaction identity')
    record = registry.get(project_id)
    journal = registry.path.parent / 'transactions' / (transaction_id + '.json')
    if journal.is_symlink():
        raise ProjectAccessError('Invalid recovery journal')
    state = json.loads(journal.read_text())
    target = state.get('target', {})
    if (Path(target.get('root', '')) / target.get('path', '') != Path(record['root'])
            or (target.get('device'), target.get('inode')) != (record['device'], record['inode'])):
        raise ProjectAccessError('Recovery journal belongs to a different project')
    return journal, state


def retained_version(registry, project_id, revision, transaction_id, operation_id):
    """Read a bounded retained version using a journal-owned operation reference."""
    import hashlib
    from .local_projects import _parts
    journal, state = _journal_for(registry, project_id, transaction_id)
    if not isinstance(operation_id, str) or not re.fullmatch('[a-f0-9]{32}', operation_id):
        raise ProjectAccessError('Invalid publication operation identity')
    operation = next((item for item in state.get('publications', [])
                      if item['id'] == operation_id), None)
    if operation is None:
        raise ProjectAccessError('Retained publication is unavailable')
    _parts(operation['path'])
    preserved = operation.get('preserved')
    prefix = f'{RECOVERY_DIRECTORY}/{transaction_id}/{operation_id}/'
    if not preserved or not preserved.startswith(prefix) or preserved[len(prefix):] not in {
            'candidate', 'candidate.displaced', 'displaced'}:
        raise ProjectAccessError('Invalid retained publication scope')
    with registry.access(project_id, revision, 'read'):
        target = ExecutionTarget(**state['target'])
        raw, _ = read_source(target, preserved)
        if raw is None:
            raise ProjectAccessError('Retained version is unavailable')
        try:
            content = raw.decode('utf-8')
        except UnicodeDecodeError as error:
            raise ProjectAccessError('Retained version requires a binary viewer') from error
        return {'path': operation['path'], 'content': content,
                'sha256': hashlib.sha256(raw).hexdigest(), 'operationId': operation_id,
                'transactionId': transaction_id}


def recover_project(registry, project_id, revision, transaction_id):
    """Restore this transaction's changes while preserving concurrent user edits."""
    journal, state = _journal_for(registry, project_id, transaction_id)
    if state.get('retention', {}).get('status') == 'pending':
        raise ProjectAccessError('Complete the pending recovery release before source recovery')
    token = active_transaction.set(str(journal))
    try:
        with registry.access(project_id, revision, 'write'):
            result = ProjectTransaction(journal).finish()
        return {'state': result['state'], 'conflicts': result['conflicts'],
                'transactionId': transaction_id}
    finally:
        active_transaction.reset(token)


def inspect_resolution(registry, project_id, revision, transaction_id):
    """Return the versions that must be confirmed together for this conflict."""
    from .project_resolution import resolution_snapshot
    journal, _ = _journal_for(registry, project_id, transaction_id)
    with registry.access(project_id, revision, 'read'):
        snapshot = ProjectTransaction(journal)._locked(resolution_snapshot)
    return {'token': snapshot['token'], 'files': snapshot['files']}


def resolve_project(registry, project_id, revision, transaction_id, expected, choices):
    """Apply explicit source choices while retaining every displaced version."""
    from .project_resolution import apply_resolution
    journal, state = _journal_for(registry, project_id, transaction_id)
    if state.get('retention', {}).get('status') == 'pending':
        raise ProjectAccessError('Complete the pending recovery release before source resolution')
    context = active_transaction.set(str(journal))
    try:
        with registry.access(project_id, revision, 'write'):
            return apply_resolution(ProjectTransaction(journal), expected, choices)
    finally:
        active_transaction.reset(context)
