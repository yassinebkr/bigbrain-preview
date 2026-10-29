"""Apply approved local source patches through the shared recovery journal."""

import hashlib
import json
from pathlib import Path

from .execution_target import ExecutionTarget
from .local_projects import ProjectAccessError, ProjectFiles, _parts
from .project_transaction import ProjectTransaction


def apply_patch_set(registry, project_id, revision, patches, *, commit=True):
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
            if not commit:
                return {'state': 'pending_verification', 'changedPaths': list(prepared),
                        'transactionId': transaction.journal.stem}
            result = transaction.finish(commit=True)
            if result['state'] != 'committed':
                raise ProjectAccessError('Project patch requires conflict recovery')
            return {'state': 'committed', 'changedPaths': list(prepared),
                    'transactionId': transaction.journal.stem}
        except Exception:
            transaction.finish()
            raise


async def verify_and_apply(registry, project_id, revision, patches, checks):
    """Check the candidate, publish through the shared journal, then recheck."""
    from .local_project_runner import ProjectRunner
    from .maintenance import protected_test
    if (not isinstance(checks, list) or not 1 <= len(checks) <= 4
            or not isinstance(patches, list) or not patches):
        raise ProjectAccessError('A repair requires candidate patches and verification commands')
    for patch in patches:
        if not isinstance(patch, dict) or protected_test(patch.get('path', '')):
            raise ProjectAccessError('Validation changes require a separately approved contract')
    for right in ('read', 'write', 'execute'):
        with registry.access(project_id, revision, right):
            pass
    runner = ProjectRunner(registry)
    evidence = []
    baseline = None
    for command in checks:
        result = await runner.run(project_id, revision, command, patches=patches, include_versions=True)
        versions = result.pop('sourceVersions')
        if baseline is not None and versions != baseline:
            raise ProjectAccessError('Project dependencies changed between candidate checks')
        baseline = versions
        evidence.append({'phase': 'candidate', 'command': command, **result})
        if result['exitCode'] != 0:
            return {'state': 'incomplete', 'checks': evidence, 'changedPaths': []}
    published = apply_patch_set(registry, project_id, revision, patches, commit=False)
    transaction = ProjectTransaction(
        registry.path.parent / 'transactions' / (published['transactionId'] + '.json'))
    try:
        expected_versions = {**baseline, **{patch['path']: hashlib.sha256(
            patch['content'].encode('utf-8')).hexdigest() for patch in patches}}
        for command in checks:
            result = await runner.run(project_id, revision, command, include_versions=True)
            if result.pop('sourceVersions') != expected_versions:
                raise ProjectAccessError('Project dependencies changed before published verification')
            evidence.append({'phase': 'published', 'command': command, **result})
            if result['exitCode'] != 0:
                return {'state': 'incomplete', 'checks': evidence,
                        'recovery': transaction.finish(), 'changedPaths': []}
        with registry.access(project_id, revision, 'write'):
            outcome = transaction.finish(commit=True)
        if outcome['state'] != 'committed':
            raise ProjectAccessError('Concurrent project changes require recovery')
        return {'state': 'committed', 'verification': 'requested_checks_passed',
                'checks': evidence, 'changedPaths': published['changedPaths'],
                'transactionId': published['transactionId']}
    finally:
        # The shared journal preserves concurrent user edits during recovery.
        state = json.loads(transaction.journal.read_text())['state']
        if state in {'open', 'cancelling'}:
            transaction.finish()
