"""Offline CAD identity, evidence and lifecycle acceptance cases."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from bigbrain.cad_contracts import CadArtifact, CadDelivery, CadPreview, CadRun


@pytest.fixture
def delivery():
    source = 'a' * 64
    return {
        'specification_id': 'spec-1', 'required_criteria': ['dimensions'],
        'required_exports': ['step'],
        'document': {
            'project_id': 'project-1', 'document_id': 'plate', 'revision': 1,
            'engine_version': '0.25.1',
            'native': {'path': 'plate.sc', 'format': 'solidcraft', 'sha256': source, 'size_bytes': 120},
            'exports': [{'path': 'plate.step', 'format': 'step', 'sha256': 'b' * 64,
                         'size_bytes': 200, 'source_sha256': source}],
        },
        'geometry': {
            'source_sha256': source, 'evidence_ref': 'measure-1', 'body_count': 1,
            'closed_solid': True, 'bounds_min_mm': [0, 0, 0],
            'bounds_max_mm': [60, 40, 6], 'volume_mm3': 14400,
        },
        'checks': [{'criterion_id': 'dimensions', 'source_sha256': source,
                    'status': 'passed', 'evidence_ref': 'measure-1',
                    'diagnostic': 'Measured bounds match the specified plate.'}],
    }


def run():
    return CadRun(run_id='run-1', project_id='project-1', document_id='plate',
                  specification_id='spec-1')


def test_delivery_serializes_and_remains_immutable(delivery):
    result = CadDelivery.model_validate(delivery)
    assert CadDelivery.model_validate_json(result.model_dump_json()) == result
    assert result.document.native.sha256 == 'a' * 64
    with pytest.raises(ValidationError):
        result.document.revision = 2


@pytest.mark.parametrize('path', [
    '../plate.sc', '/plate.sc', 'C:/plate.sc', 'C:plate.sc', 'plate.sc:stream',
    r'folder\plate.sc', './plate.sc', 'folder//plate.sc', 'folder/../plate.sc',
    '.secret/plate.sc', 'plate.sc/', '.', '\x00plate.sc',
])
def test_artifact_paths_are_portable_and_scoped(path):
    with pytest.raises(ValidationError):
        CadArtifact(path=path, format='solidcraft', sha256='a' * 64, size_bytes=1)


@pytest.mark.parametrize(('section', 'field', 'value'), [
    ('geometry', 'source_sha256', 'c' * 64),
    ('geometry', 'body_count', 0), ('geometry', 'closed_solid', False),
    ('geometry', 'volume_mm3', 0), ('geometry', 'volume_mm3', float('nan')),
    ('geometry', 'volume_mm3', float('inf')),
    ('geometry', 'bounds_max_mm', [60, 40, 0]),
    ('geometry', 'bounds_max_mm', [-1, 40, 6]),
    ('geometry', 'bounds_min_mm', [0, 0, float('nan')]),
    ('document', 'units', 'in'), ('document', 'revision', True),
])
def test_invalid_geometry_or_revision_blocks_delivery(delivery, section, field, value):
    delivery[section][field] = value
    with pytest.raises(ValidationError):
        CadDelivery.model_validate(delivery)


@pytest.mark.parametrize('defect', ['missing', 'duplicate', 'extra', 'failed', 'unresolved', 'old', 'required_duplicate'])
def test_criterion_gate(delivery, defect):
    if defect == 'missing':
        delivery['checks'] = []
    elif defect == 'duplicate':
        delivery['checks'] *= 2
    elif defect == 'extra':
        delivery['checks'].append({**delivery['checks'][0], 'criterion_id': 'unrequested'})
    elif defect == 'required_duplicate':
        delivery['required_criteria'] *= 2
    elif defect == 'old':
        delivery['checks'][0]['source_sha256'] = 'c' * 64
    else:
        delivery['checks'][0]['status'] = 'failed' if defect == 'failed' else 'inconclusive'
    with pytest.raises(ValidationError):
        CadDelivery.model_validate(delivery)


@pytest.mark.parametrize('defect', ['missing', 'old', 'path_collision', 'wrong_native'])
def test_export_gate(delivery, defect):
    if defect == 'missing':
        delivery['document']['exports'] = []
    elif defect == 'old':
        delivery['document']['exports'][0]['source_sha256'] = 'c' * 64
    elif defect == 'path_collision':
        delivery['document']['exports'][0]['path'] = 'plate.sc'
    else:
        delivery['document']['native']['format'] = 'stl'
    with pytest.raises(ValidationError):
        CadDelivery.model_validate(delivery)


@pytest.mark.parametrize('changed', [None, 'project_id', 'document_id', 'revision', 'hash'])
def test_preview_tracks_exact_piece_revision(delivery, changed):
    document = CadDelivery.model_validate(delivery).document
    data = {'project_id': 'project-1', 'document_id': 'plate', 'revision': 1,
            'image': {'path': 'preview.png', 'format': 'png', 'sha256': 'd' * 64,
                      'size_bytes': 100, 'source_sha256': 'a' * 64},
            'width': 960, 'height': 600}
    if changed == 'hash':
        data['image']['source_sha256'] = 'c' * 64
    elif changed is not None:
        data[changed] = 2 if changed == 'revision' else 'another'
    assert CadPreview.model_validate(data).is_current(document) == (changed is None)


def test_repair_and_terminal_lifecycle(delivery):
    queued = run()
    checking = queued.transition('modeling').transition('checking')
    repaired = checking.transition('modeling').transition('checking')
    ready = repaired.transition('ready', delivery=delivery)
    assert ready.delivery.geometry.volume_mm3 == 14400
    assert queued.state == 'queued'
    for state in ('modeling', 'checking', 'ready'):
        with pytest.raises(ValueError):
            ready.transition(state)
    with pytest.raises(ValueError):
        queued.transition('ready', delivery=delivery)
    with pytest.raises(ValidationError):
        checking.transition('ready')


@pytest.mark.parametrize('state', ['failed', 'cancelled', 'blocked'])
def test_stopped_work_has_visible_diagnostic(state):
    with pytest.raises(ValidationError):
        run().transition(state)
    stopped = run().transition(state, diagnostic='Operation stopped before publication.')
    with pytest.raises(ValueError):
        stopped.transition('modeling')


@pytest.mark.parametrize('field', ['project_id', 'document_id', 'specification_id'])
def test_delivery_cannot_cross_run_identity(delivery, field):
    changed = deepcopy(delivery)
    target = changed if field == 'specification_id' else changed['document']
    target[field] = 'another'
    checking = run().transition('modeling').transition('checking')
    with pytest.raises(ValidationError):
        checking.transition('ready', delivery=changed)
