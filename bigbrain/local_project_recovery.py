"""Project-scoped recovery views backed by the shared transaction journal."""

import json
from pathlib import Path
import re

from .local_projects import ProjectAccessError
from .project_transaction import active_transaction, ProjectTransaction


def project_transactions(registry, record):
    """Expose transaction identity and affected paths without source snapshots."""
    root = Path(record['root'])
    results = []
    for journal in (registry.path.parent / 'transactions').glob('*.json'):
        state = json.loads(journal.read_text())
        target = state.get('target', {})
        if Path(target.get('root', '')) / target.get('path', '') != root:
            continue
        if state.get('state') in {'open', 'cancelling', 'conflict'}:
            results.append({'id': journal.stem, 'state': state['state'],
                            'paths': sorted(path for path, entry in state.get('files', {}).items()
                                            if entry.get('written'))})
    return results


def recover_project(registry, project_id, revision, transaction_id):
    """Restore this transaction's changes while preserving concurrent user edits."""
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
    token = active_transaction.set(str(journal))
    try:
        with registry.access(project_id, revision, 'write'):
            result = ProjectTransaction(journal).finish()
        return {'state': result['state'], 'conflicts': result['conflicts'],
                'transactionId': transaction_id}
    finally:
        active_transaction.reset(token)
