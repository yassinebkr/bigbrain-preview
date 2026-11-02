"""Analytic measurements reject incorrect radius, axis and source geometry."""

import pytest
from pydantic import ValidationError

from bigbrain.cad_surfaces import CadCylinder
from bigbrain.cad_planning import CadPlan
from bigbrain.brains.cad_brain import CadBrain
from bigbrain.bus.bus import MessageBus
from bigbrain.verification.evidence import default_repository
from tests.test_cad_integration import engine, prepared, task
from tests.test_cad_drawings import drawing


def criterion(**changes):
    return CadCylinder(id='arc', label='Rayon et axe du fond arrondi', body='probe',
                       axis=2, center_mm=(0, 0, 0), radius_mm=25, **changes)


def topology(radius=25, origin=(0, 0, 8), axis=(0, 0, -1), exact=True):
    return {'body': 'probe', 'faces': [{'exact': exact, 'cylinder': {'radius': radius, 'origin': origin, 'axis': axis}}]}


@pytest.mark.parametrize('data,status', [
    (topology(), 'passed'), (topology(radius=24), 'failed'),
    (topology(origin=(1, 0, 0)), 'failed'), (topology(axis=(0, 1, 0)), 'failed'),
    (topology(exact=False), 'inconclusive'), (topology(radius=float('nan')), 'inconclusive'),
    ({'body': 'probe', 'faces': []}, 'failed'),
])
def test_analytic_face_observation(data, status):
    result = criterion().observe(data, source_sha256='a'*64, evidence_ref='topology.json')
    assert result.status == status
    assert result.source_sha256 == 'a'*64
    assert result.expected == (25, 0, 0)


def test_matching_approximate_face_is_inconclusive_among_exact_coaxial_faces():
    data = topology(radius=10)
    data['faces'] += topology(exact=False)['faces']
    result = criterion().observe(data, source_sha256='a'*64, evidence_ref='topology.json')
    assert result.status == 'inconclusive'
    assert 'independent measurement' in result.diagnostic
    data['faces'][-1]['cylinder']['radius'] = 24
    assert criterion().observe(data, source_sha256='a'*64, evidence_ref='topology.json').status == 'failed'
    data['faces'] += topology()['faces']
    assert criterion().observe(data, source_sha256='a'*64, evidence_ref='topology.json').status == 'passed'


def test_cylinder_center_binding_cannot_use_axis_coordinate():
    with pytest.raises(ValidationError, match='own axis'):
        criterion(center_bindings={'invalid': 2})


def test_drawing_radius_requires_faithful_analytic_binding():
    data = drawing()
    data['dimensions'].append({**data['dimensions'][0], 'id': 'radius', 'kind': 'radius', 'value': 25})
    plan = {'title': 'Probe', 'drawing': data,
        'commands': [{'command': 'solid.cylinder', 'params': {'radius': 25, 'height': 10}}],
        'criteria': [{'id': 'bounds', 'label': 'Envelope', 'metric': 'dimensions_mm',
            'expected': [60, 40, 6], 'dimension_bindings': {'width': 0}}],
        'cylinders': [{**criterion().model_dump(), 'radius_binding': 'radius'}]}
    assert CadPlan.model_validate(plan)
    plan['cylinders'][0]['radius_mm'] = 24
    with pytest.raises(ValidationError, match='target differs'):
        CadPlan.model_validate(plan)
    plan['cylinders'][0]['radius_mm'] = 12.5
    data['dimensions'][1]['kind'] = 'diameter'
    assert CadPlan.model_validate(plan)
    plan['cylinders'][0]['radius_mm'] = 25
    with pytest.raises(ValidationError, match='target differs'):
        CadPlan.model_validate(plan)


@pytest.mark.asyncio
@pytest.mark.parametrize('wrong', [None, 'radius', 'position'])
async def test_native_truncated_cylinder_check_controls_publication(tmp_path, engine, wrong):
    offset = 1 if wrong == 'position' else 0
    plan_data = {'title': 'Arc tronqué', 'commands': [
        {'command': 'solid.cylinder', 'params': {'radius': 25, 'height': 10, 'body_name': 'probe', 'base': [offset, 0, 0]}},
        {'command': 'solid.box', 'params': {'length': 10, 'width': 30, 'height': 10,
            'corner': [20 + offset, -15, 0], 'operation': 'intersect', 'targets': ['probe']}}],
        'criteria': [{'id': 'bounds', 'label': 'Envelope', 'metric': 'dimensions_mm', 'expected': [5, 30, 10]}],
        'cylinders': [{**criterion().model_dump(), 'radius_mm': 24 if wrong == 'radius' else 25}]}
    bus = MessageBus(tmp_path / 'logs', auth=None)
    try:
        plan, spec, _ = await prepared(bus, plan_data)
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        result = await CadBrain('cad_brain', bus).handle_task(task(plan, confirmed))
        assert result['success'] is (wrong is None), result
        if wrong:
            assert result['delivery_status'] == 'incomplete'
        else:
            check = next(item for item in result['cad']['checks'] if item['criterion_id'] == 'arc')
            assert check['status'] == 'passed'
            assert check['observed'] == pytest.approx([25, 0, 0])
            assert check['evidence_ref'].endswith('/topology.json')
    finally:
        await bus.close()
