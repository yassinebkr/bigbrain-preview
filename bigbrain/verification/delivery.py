"""Runtime delivery receipts bind approval, executed checks and source bytes."""
import json
import hashlib

from ..project_inspection import digest
from .evidence import default_repository


def file_snapshot(target, paths):
    """Include declared data/assets as well as text sources in the delivery."""
    result, size = {}, 0
    for path in sorted(set(paths)):
        file = target.file(path)
        if not file.is_file():
            result[path] = None
            continue
        size += file.stat().st_size
        if size > 20_000_000 or len(result) >= 10000:
            raise ValueError('Delivery artifact snapshot budget exceeded')
        result[path] = hashlib.sha256(file.read_bytes()).hexdigest()
    return result


def _check_manifest(ref, run_id, kind, executable, stack):
    repo = default_repository()
    spec = repo.load_spec(ref['design_id'], ref['revision'])
    run = repo.load_manifest(run_id)
    if (not spec or spec.metadata.get('approval', {}).get('decision') != 'approved'
            or not run or run.status != 'completed' or run.verdict != 'passed'
            or (run.design_id, run.design_revision, run.spec_sha256) !=
               (spec.design_id, spec.revision, spec.content_sha256())):
        raise ValueError('Delivery requires passing evidence for the approved contract revision')
    required = {'semantics'}
    if kind == 'python':
        required |= {'syntax', 'compile', 'contracts', 'tests', 'source_revision'}
    elif kind == 'web_app':
        required |= {'web_artifacts', 'browser'}
        if stack == 'react_vite':
            required |= {'dependencies', 'typecheck', 'build'}
    else:
        raise ValueError('Unsupported project delivery type')
    stages = {s.name: s for s in run.stages}
    if any(name not in stages or stages[name].status != 'passed' for name in required):
        raise ValueError('Delivery checks or approved-criteria review are missing')
    if kind == 'python':
        if not stages['tests'].details.get('passed_cases'):
            raise ValueError('Delivery needs executed passing tests')
        if 'run' not in stages or stages['run'].status != ('passed' if executable else 'not_applicable'):
            raise ValueError('Delivery needs verified entry-point execution or an explicit library contract')
    elif not any(case.get('status') == 'passed' for case in stages['browser'].details.get('cases', [])):
        raise ValueError('Delivery needs executed browser assertions')
    for artifact in run.artifacts:
        raw = repo.get_artifact(artifact.sha256)
        if raw is None or hashlib.sha256(raw).hexdigest() != artifact.sha256:
            raise ValueError('Delivery evidence artifact is unavailable or changed')
    return spec


def issue(target, payload, result, kind, hashes):
    """Called only after the shared repair engine's complete delivery gate."""
    ref = payload['contract_revision']
    executable = payload.get('executable', True) is not False
    stack = payload.get('web_stack', 'static')
    run_id = result.get('verification', {}).get('run_id')
    spec = _check_manifest(ref, run_id, kind, executable, stack)
    entry = result.get('entry_point') or payload.get('entry_point')
    if executable and (not entry or entry not in hashes or not target.file(entry).is_file()):
        raise ValueError('Delivery entry point is absent from verified sources')
    declaration = {'deliverable_type': kind, 'executable': executable,
                   'entry_point': entry if executable else None, 'web_stack': stack}
    if spec.metadata.get('delivery') and declaration != spec.metadata['delivery']:
        raise ValueError('Delivery differs from the approved architecture')
    receipt = {'protocol': 'project-delivery/1', 'target': target.to_payload(),
        'contract_revision': ref, 'run_id': run_id, **declaration,
        'file_hashes': file_snapshot(target, set(hashes) | {f['path'] for f in payload.get('all_files', [])}),
        'source_hashes': hashes, 'source_revision': digest(json.dumps(hashes, sort_keys=True))}
    artifact = default_repository().put_artifact(json.dumps(receipt, sort_keys=True).encode(),
        name='project-delivery.json', media_type='application/json')
    return {**result, 'delivery_receipt': artifact.sha256, 'delivery_status': 'ready', 'verified': True,
        'runnable': executable, 'project_path': target.path, 'project_name': target.directory.name,
        'deliverable_type': kind}


def validate(target, payload, result):
    """Orchestrator rechecks the receipt immediately before transaction commit."""
    from ..maintenance import ProjectTools
    sha = result.get('delivery_receipt', '')
    raw = default_repository().get_artifact(sha) if sha else None
    if raw is None or hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError('New project has no runtime delivery receipt')
    receipt = json.loads(raw)
    if (receipt.get('protocol') != 'project-delivery/1' or receipt.get('target') != target.to_payload()
            or receipt.get('contract_revision') != payload.get('contract_revision')
            or receipt.get('run_id') != result.get('verification', {}).get('run_id')):
        raise ValueError('Delivery receipt belongs to another target, contract or run')
    spec = _check_manifest(receipt['contract_revision'], receipt['run_id'], receipt['deliverable_type'],
                          receipt['executable'], receipt['web_stack'])
    declaration = {k: receipt[k] for k in ('deliverable_type', 'executable', 'entry_point', 'web_stack')}
    if spec.metadata.get('delivery') and declaration != spec.metadata['delivery']:
        raise ValueError('Delivery differs from the approved architecture')
    if spec.metadata.get('execution_target') not in (None, target.public()):
        raise ValueError('Delivery target differs from approved scope')
    current = ProjectTools(target).fingerprints()
    if (current != receipt['source_hashes']
            or digest(json.dumps(current, sort_keys=True)) != receipt['source_revision']):
        raise ValueError('Project sources changed after delivery verification')
    if file_snapshot(target, receipt['file_hashes']) != receipt['file_hashes']:
        raise ValueError('Project artifacts changed after delivery verification')
    entry = receipt['entry_point']
    if receipt['executable'] and (not entry or entry not in current or not target.file(entry).is_file()):
        raise ValueError('Verified entry point is missing')
    return {'delivery_status': 'ready', 'verified': True, 'runnable': receipt['executable'],
        'project_path': target.path, 'project_name': target.directory.name, 'entry_point': entry,
        'deliverable_type': receipt['deliverable_type'], 'delivery_receipt': sha,
        'verification_run_id': receipt['run_id']}
