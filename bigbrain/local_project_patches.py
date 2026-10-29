"""Apply approved local source patches through the shared recovery journal."""

import hashlib
import json
from pathlib import Path

from .execution_target import ExecutionTarget
from .local_projects import ProjectAccessError, ProjectFiles, _parts
from .project_transaction import ProjectTransaction


def apply_patch_set(registry, project_id, revision, patches):
    """Validate all input versions before recording and applying a bounded batch."""
    if not isinstance(patches, list) or not 1 <= len(patches) <= 32:
        raise ProjectAccessError('A patch set requires between 1 and 32 files')
    files = ProjectFiles(registry, project_id, revision)
    prepared = {}
    total = 0
    for patch in patches:
        if not isinstance(patch, dict):
            raise ProjectAccessError('Invalid patch entry')
        path = patch.get('path')
        _parts(path)
        content = patch.get('content')
        if not isinstance(content, str) or path in prepared:
            raise ProjectAccessError('Patch paths must be unique with text content')
        data = content.encode('utf-8')
        total += len(data)
        if len(data) > 4_000_000 or total > 16_000_000:
            raise ProjectAccessError('Patch set exceeds content limit')
        expected = patch.get('sha256')
        try:
            actual = hashlib.sha256(files.read(path, 4_000_000)).hexdigest()
        except FileNotFoundError:
            actual = None
        if actual != expected:
            raise ProjectAccessError(f'{path}: project file changed concurrently')
        prepared[path] = (data, expected)
    root = Path(registry.get(project_id)['root'])
    with registry.access(project_id, revision, 'write'):
        info = root.stat()
        target = ExecutionTarget('existing', root.name, str(root.parent), info.st_dev, info.st_ino)
        transaction = ProjectTransaction.begin(
            target, prepared, journal_root=registry.path.parent / 'transactions')
        try:
            state = json.loads(transaction.journal.read_text())
            for path, (_, expected) in prepared.items():
                if state['files'][path]['after'] != expected:
                    raise ProjectAccessError(f'{path}: project changed before publication')
            for path, (data, _) in prepared.items():
                transaction.write(target, path, data)
            result = transaction.finish(commit=True)
            if result['state'] != 'committed':
                raise ProjectAccessError('Project patch requires conflict recovery')
            return {'state': 'committed', 'changedPaths': list(prepared),
                    'transactionId': transaction.journal.stem}
        except Exception:
            transaction.finish()
            raise
