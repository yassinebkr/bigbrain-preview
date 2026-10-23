"""Record failures discovered before a specialist can run its full gate."""
import json

from .evidence import RunManifest, StageResult, default_repository


def failure(payload, *, stage, cause, details):
    """Typed runtime observations enter the same immutable evidence chain."""
    status = 'failed' if cause == 'reproduced_defect' else 'inconclusive'
    result = {'verdict': status, 'failures': [
        {'stage': stage, 'status': status, 'details': {'cause': cause, **details}}]}
    ref = payload.get('contract_revision')
    if ref:
        repo = default_repository()
        spec = repo.load_spec(ref['design_id'], ref['revision'])
        if (not spec or spec.metadata.get('approval', {}).get('decision') != 'approved'
                or spec.user_request != payload.get('user_request')):
            raise ValueError('Preflight requires the approved request revision')
        artifact = repo.put_artifact(json.dumps(result, sort_keys=True).encode(),
            name='project-preflight.json', media_type='application/json')
        manifest = RunManifest(design_id=spec.design_id, design_revision=spec.revision,
            spec_sha256=spec.content_sha256(), status=status,
            parent_run_id=payload.get('_verification_parent_run_id'),
            stages=[StageResult(name=stage, status=status, tool='specialist_preflight',
                details=result['failures'][0]['details'], artifact_hashes=[artifact.sha256])],
            artifacts=[artifact], metadata={'attempt': payload.get('_verification_attempt', 1)})
        repo.save_manifest(manifest)
        result['run_id'] = manifest.run_id
    return result
