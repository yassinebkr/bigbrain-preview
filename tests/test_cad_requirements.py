"""Requirement measurements use actual geometry and immutable drawing targets."""

import json

import pytest
from pydantic import ValidationError

from bigbrain.cad_contracts import GeometryObservation
from bigbrain.cad_drawings import DrawingSpecification
from bigbrain.cad_planning import CadPlan, draft_cad_plan, refine_cad_sampling
from bigbrain.cad_contracts import CriterionObservation
from bigbrain.brains.cad_brain import CadBrain
from bigbrain.bus.bus import MessageBus
from bigbrain.verification.evidence import default_repository
from tests.test_cad_clarification import fixture
from tests.test_cad_drawings import drawing
from tests.test_cad_integration import engine, prepared, task


def operand(source='section', reference='depth', quantity='end', axis=None):
    result = {'source': source, 'quantity': quantity}
    if reference is not None:
        result['reference'] = reference
    if axis is not None:
        result['axis'] = axis
    return result


def data():
    definition = drawing()
    definition['dimensions'][0].update(id='depth', kind='depth', value=5)
    return {'title': 'Recess', 'drawing': definition,
        'commands': [{'command': 'solid.box', 'params': {'length': 60, 'width': 40, 'height': 10}}],
        'criteria': [{'id': 'bounds', 'label': 'Envelope', 'metric': 'dimensions_mm', 'expected': [60, 40, 10]}],
        'sections': [{'id': 'depth', 'label': 'Recess floor', 'axis': 2, 'point_mm': [30, 20, 0],
                      'intervals_mm': [[0, 5]]}],
        'measurements': [{'id': 'recess-depth', 'dimension_id': 'depth', 'operation': 'difference',
            'first': operand('envelope', None, 'end', 2), 'second': operand()}]}


def geometry():
    return GeometryObservation(source_sha256='a'*64, evidence_ref='geometry.json',
        bounds_min_mm=(0, 0, 0), bounds_max_mm=(60, 40, 10), volume_mm3=1000,
        body_count=1, closed_solid=True)


def test_dependent_inconclusive_measurement_allows_reproduced_defect_repair():
    from bigbrain.cad_stages import reproduced_defect_is_repairable
    plan = CadPlan.model_validate(data())
    def check(identity, status):
        return CriterionObservation(criterion_id=identity, source_sha256='a'*64,
            evidence_ref='observations.json', status=status, diagnostic='Measured evidence')
    checks = [check('depth', 'failed'), check('recess-depth', 'inconclusive')]
    assert reproduced_defect_is_repairable(plan, checks)
    assert not reproduced_defect_is_repairable(plan, checks + [check('unrelated', 'inconclusive')])
    assert not reproduced_defect_is_repairable(plan, [check('recess-depth', 'inconclusive')])


@pytest.mark.asyncio
async def test_native_missing_hole_repairs_despite_dependent_inconclusive_measurement(tmp_path, engine):
    from tests.test_cad_integration import Provider
    _, sid, _, definition = fixture()
    definition['dimensions'][0].update(id='hole-diameter', kind='diameter', value=8)
    def commands(y):
        return [{'command': 'solid.box', 'params': {'length': 60, 'width': 40, 'height': 10,
                    'corner': [0, -40, -10], 'body_name': 'plate'}},
                {'command': 'solid.cylinder', 'params': {'radius': 4, 'height': 10,
                    'base': [30, y, -10], 'operation': 'cut', 'targets': ['plate']}}]
    plan_data = {'title': 'Plate', 'commands': commands(20), 'max_repairs': 1,
        'criteria': [{'id': 'bounds', 'label': 'Envelope', 'metric': 'dimensions_mm', 'expected': [60, 40, 10]}],
        'cylinders': [{'id': 'hole', 'label': 'Through hole', 'body': 'plate', 'axis': 2,
            'center_mm': [30, -20, 0], 'radius_mm': 4}],
        'measurements': [{'id': 'diameter', 'dimension_id': 'hole-diameter',
            'first': operand('cylinder', 'hole', 'diameter')}]}
    bus = MessageBus(tmp_path / 'logs', auth=None)
    provider = Provider({'commands': commands(-20)})
    try:
        plan, spec, _ = await prepared(bus, plan_data, drawing=definition, session_id=sid, precompiled=True)
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        result = await CadBrain('cad_brain', bus, llm_provider=provider).handle_task(task(plan, confirmed))
        assert result['success'], result
        assert len(provider.calls) == 1
        packet = json.loads(provider.calls[0]['messages'][1]['content'])
        statuses = {item['criterion_id']: item['status'] for item in packet['observations']}
        assert statuses['hole'] == 'failed' and statuses['diameter'] == 'inconclusive'
        assert packet['candidate_context']['geometry']['bounds_min_mm'] == pytest.approx([0, -40, -10])
        assert packet['candidate_context']['topology']['plate']
        assert all(check['status'] == 'passed' for check in result['cad']['checks'])
        assert next(c for c in result['cad']['checks'] if c['criterion_id'] == 'diameter')['expected'] == [8]
    finally:
        await bus.close()


def test_depth_reads_actual_values_and_rejects_wrong_candidate():
    plan = CadPlan.model_validate(data())
    method = plan.measurements[0]
    good = method.observe(plan, geometry(), {'depth': ((0, 5),)}, {}, evidence_ref='requirements.json')
    bad = method.observe(plan, geometry(), {'depth': ((0, 6),)}, {}, evidence_ref='requirements.json')
    assert good.status == 'passed' and good.observed == good.expected == (5,)
    assert bad.status == 'failed' and bad.expected == (5,) and bad.observed == (4,)
    missing = method.observe(plan, geometry(), {'depth': None}, {}, evidence_ref='requirements.json')
    assert missing.status == 'inconclusive'
    assert good.source_sha256 == geometry().source_sha256


def test_raw_probe_has_no_model_target_and_requires_a_consumer():
    from bigbrain.cad_sections import observe_section
    plan_data = data()
    plan_data['sections'][0].pop('intervals_mm')
    plan = CadPlan.model_validate(plan_data)
    observation, actual = observe_section(plan.sections[0], [], source_sha256='a'*64, evidence_ref='sections.json')
    assert observation.expected_intervals_mm is None and actual == ()
    assert plan.measurements[0].observe(plan, geometry(), {'depth': actual}, {},
        evidence_ref='requirements.json').status == 'inconclusive'
    plan_data['measurements'] = []
    with pytest.raises(ValidationError, match='must feed a requirement'):
        CadPlan.model_validate(plan_data)


def test_preflight_reports_multiple_errors_together():
    plan = data()
    plan['measurements'] += [
        {'id': 'self', 'dimension_id': 'depth', 'operation': 'difference', 'first': operand(), 'second': operand()},
        {'id': 'wrong-axis', 'dimension_id': 'depth', 'operation': 'difference',
            'first': operand('envelope', None, 'end', 0), 'second': operand()},
        {'id': 'absent', 'dimension_id': 'depth', 'first': operand(reference='missing')}]
    with pytest.raises(ValidationError) as error:
        CadPlan.model_validate(plan)
    message = str(error.value)
    assert 'distinct observations' in message and 'same world axis' in message and 'missing' in message


def test_angle_uses_perpendicular_measured_coordinate_differences():
    plan = data()
    plan['drawing']['dimensions'][0].update(id='angle', kind='angle', unit='degree', value=45)
    plan['sections'] += [{'id': 'slope-x', 'label': 'Slope run', 'axis': 0,
                         'point_mm': [0, 20, 8], 'intervals_mm': [[0, 55]]}]
    plan['measurements'] = [{'id': 'angle-check', 'dimension_id': 'angle', 'operation': 'angle',
        'first': operand('envelope', None, 'end', 2), 'rise_origin': operand(),
        'second': operand('envelope', None, 'end', 0),
        'run_origin': operand(reference='slope-x')}]
    plan = CadPlan.model_validate(plan)
    method = plan.measurements[0]
    assert method.observe(plan, geometry(), {'depth': ((0, 5),), 'slope-x': ((0, 55),)}, {},
                          evidence_ref='requirements.json').observed == (45,)
    assert method.observe(plan, geometry(), {'depth': ((0, 4),), 'slope-x': ((0, 55),)}, {},
                          evidence_ref='requirements.json').status == 'failed'


@pytest.mark.asyncio
async def test_planner_corrects_all_preflight_diagnostics_in_one_bounded_call():
    bad = data()
    bad.pop('drawing')
    bad['measurements'][0]['second'] = bad['measurements'][0]['first']
    good = data()
    definition = DrawingSpecification.model_validate(good.pop('drawing'))
    class Provider:
        def __init__(self):
            self.calls = []
        async def chat_complete(self, **kwargs):
            self.calls.append(kwargs)
            return json.dumps(bad if len(self.calls) == 1 else good)
    provider = Provider()
    plan = await draft_cad_plan(provider, 'Create recess', drawing=definition)
    assert plan.drawing == definition and len(provider.calls) == 2
    assert 'distinct observations' in provider.calls[1]['messages'][-1]['content']
    assert 'world-axis' not in ' '.join(plan.contracts())


def test_parameter_preflight_requires_existing_names_for_bulk_updates():
    from bigbrain.cad_planning import validate_cad_proposal
    raw = data()
    definition = DrawingSpecification.model_validate(raw.pop('drawing'))
    raw['commands'].insert(0, {'command': 'parameters.change', 'params': {'changes': {'L': '60 mm'}}})
    with pytest.raises(ValueError, match='requires existing names: L'):
        validate_cad_proposal(json.dumps(raw), drawing=definition)
    raw['commands'].insert(0, {'command': 'parameters.change', 'params': {'name': 'L', 'expression': '60 mm'}})
    assert validate_cad_proposal(json.dumps(raw), drawing=definition)


@pytest.mark.asyncio
@pytest.mark.parametrize('wrong', [False, True])
async def test_native_local_requirement_controls_delivery_with_same_envelope(tmp_path, engine, wrong):
    _, sid, _, definition = fixture()
    definition['dimensions'][0].update(id='hole-diameter', kind='diameter', value=8)
    plan_data = {'title': 'Plaque percée', 'commands': [
        {'command': 'solid.box', 'params': {'length': 60, 'width': 40, 'height': 10, 'body_name': 'plate'}},
        {'command': 'solid.cylinder', 'params': {'radius': 5 if wrong else 4, 'height': 10,
            'base': [30, 20, 0], 'operation': 'cut', 'targets': ['plate']}}],
        'criteria': [{'id': 'bounds', 'label': 'Envelope', 'metric': 'dimensions_mm', 'expected': [60, 40, 10]}],
        'cylinders': [{'id': 'hole', 'label': 'Hole surface', 'body': 'plate', 'axis': 2,
                       'center_mm': [30, 20, 0], 'radius_mm': 5 if wrong else 4}],
        'measurements': [{'id': 'diameter', 'dimension_id': 'hole-diameter',
                          'first': operand('cylinder', 'hole', 'diameter')}]}
    bus = MessageBus(tmp_path / 'logs', auth=None)
    try:
        plan, spec, _ = await prepared(bus, plan_data, drawing=definition, session_id=sid, precompiled=True)
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        result = await CadBrain('cad_brain', bus).handle_task(task(plan, confirmed))
        assert result['success'] is not wrong, result
        if wrong:
            assert result['delivery_status'] == 'incomplete' and 'observed 10; expected 8' in result['error']
        else:
            checks = result['cad']['checks']
            assert next(c for c in checks if c['criterion_id'] == 'diameter')['expected'] == [8]
    finally:
        await bus.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('response', [
    {'points': {'depth': [30.02, 20, 0]}},
    {'points': {'unknown': [30, 20, 0]}},
    {'points': {'depth': [30.0001, 20, 0]}, 'absolute_tolerance': 1},
])
async def test_sampling_refinement_rejects_scope_and_acceptance_changes(response):
    from unittest.mock import AsyncMock
    plan = CadPlan.model_validate(data())
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps(response)
    observation = CriterionObservation(criterion_id='depth', label='Floor', status='inconclusive',
        source_sha256='a'*64, evidence_ref='sections.json', diagnostic='Section lies on a surface boundary')
    with pytest.raises(ValueError):
        await refine_cad_sampling(provider, plan, [observation])


@pytest.mark.asyncio
async def test_native_boundary_refinement_remeasures_same_candidate(tmp_path, engine):
    from tests.test_cad_integration import Provider
    from bigbrain.cad_store import CadStore
    _, sid, _, definition = fixture()
    definition['dimensions'][0].update(id='depth', kind='depth', value=5)
    plan_data = data()
    plan_data.pop('drawing')
    plan_data['commands'] = [
        {'command': 'solid.box', 'params': {'length': 60, 'width': 40, 'height': 10, 'body_name': 'plate'}},
        {'command': 'solid.box', 'params': {'length': 20, 'width': 20, 'height': 5,
            'corner': [20, 10, 5], 'operation': 'cut', 'targets': ['plate']}}]
    plan_data['sections'][0]['point_mm'] = [20, 20, 0]
    plan_data['sections'][0].pop('intervals_mm')
    provider = Provider({'points': {'depth': [20.0001, 20, 0]}})
    bus = MessageBus(tmp_path / 'logs', auth=None)
    try:
        plan, spec, _ = await prepared(bus, plan_data, drawing=definition, session_id=sid, precompiled=True)
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        result = await CadBrain('cad_brain', bus, llm_provider=provider).handle_task(task(plan, confirmed))
        assert result['success'], result
        assert len(provider.calls) == 1
        document = result['cad']['document']
        assert document['revision'] == 1
        evidence = CadStore().directory(document['document_id']) / 'revision-1' / 'sampling-attempts.json'
        attempts = json.loads(evidence.read_text())
        assert len(attempts) == 2
        assert attempts[0]['observations'][0]['status'] == 'inconclusive'
        assert attempts[1]['observations'][0]['status'] == 'passed'
        assert attempts[0]['sections'][0]['surface_sha256'] == attempts[1]['sections'][0]['surface_sha256']
        assert attempts[0]['sections'][0]['criterion']['intervals_mm'] == attempts[1]['sections'][0]['criterion']['intervals_mm']
    finally:
        await bus.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('wrong', [False, True])
async def test_native_arc_endpoint_is_measured_without_boundary_sampling(tmp_path, engine, wrong):
    _, sid, _, definition = fixture()
    definition['dimensions'][0].update(id='endpoint-x', kind='position', value=20)
    plan_data = {'title': 'Arc endpoint', 'commands': [
        {'command': 'solid.cylinder', 'params': {'radius': 25, 'height': 10, 'body_name': 'probe'}},
        {'command': 'solid.box', 'params': {'length': 10, 'width': 30, 'height': 10,
            'corner': [20, -15, 0], 'operation': 'intersect', 'targets': ['probe']}}],
        'criteria': [{'id': 'bounds', 'label': 'Envelope', 'metric': 'dimensions_mm', 'expected': [5, 30, 10]}],
        'vertices': [{'id': 'endpoint', 'label': 'Arc endpoint', 'body': 'probe', 'point_mm': [21 if wrong else 20, -15, 0]}],
        'measurements': [{'id': 'endpoint-coordinate', 'dimension_id': 'endpoint-x',
                          'first': operand('vertex', 'endpoint', 'coordinate', 0)}]}
    bus = MessageBus(tmp_path / 'logs', auth=None)
    try:
        plan, spec, _ = await prepared(bus, plan_data, drawing=definition, session_id=sid, precompiled=True)
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        result = await CadBrain('cad_brain', bus).handle_task(task(plan, confirmed))
        assert result['success'] is not wrong, result
        if not wrong:
            observed = next(c for c in result['cad']['checks'] if c['criterion_id'] == 'endpoint-coordinate')
            assert observed['observed'] == pytest.approx([20])
    finally:
        await bus.close()
