"""Project CAD outcomes into the shared immutable evidence repository."""

from datetime import datetime, timezone
import json

from .verification.evidence import RunManifest, StageResult, canonical_json, sha256_bytes


def begin_evidence(repository, specification, context, document_id):
    manifest = RunManifest(design_id=specification.design_id,
        design_revision=specification.revision,
        spec_sha256=sha256_bytes(canonical_json(specification).encode('utf-8')),
        status='running', toolchain={'brain': 'cad_brain'},
        metadata={**context, 'document_id': document_id},
        stages=[StageResult(name='cad_delivery', status='running')])
    repository.save_manifest(manifest)
    return manifest


def finish_evidence(repository, manifest, presentation):
    """Freeze the actual terminal presentation and its source-bound checks."""
    cad = presentation['cad']
    artifact = repository.put_artifact(
        json.dumps(presentation, ensure_ascii=False, allow_nan=False).encode('utf-8'),
        name='cad-presentation.json', media_type='application/json')
    snapshot = cad.get('snapshot')
    stages = [StageResult(name='cad_delivery',
        status='passed' if cad['status'] == 'ready' else 'inconclusive',
        artifact_hashes=[artifact.sha256], details={'diagnostic': cad.get('diagnostic'),
            'document_id': cad['document_id'], 'working': cad.get('working')})]
    for check in (snapshot or {}).get('checks', []):
        stages.append(StageResult(name=check['criterion_id'], status=check['status'],
            artifact_hashes=[artifact.sha256], details=check))
    completed = manifest.model_copy(update={
        'status': {'ready': 'completed', 'failed': 'failed', 'cancelled': 'cancelled'}[cad['status']],
        'completed_at': datetime.now(timezone.utc), 'stages': stages, 'artifacts': [artifact],
        'metadata': {**manifest.metadata,
            'revision': (snapshot or {}).get('document', {}).get('revision'),
            'native_sha256': (snapshot or {}).get('document', {}).get('native', {}).get('sha256')}})
    repository.save_manifest(completed)
    return completed
