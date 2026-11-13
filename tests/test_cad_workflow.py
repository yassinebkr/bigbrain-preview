"""Design-intent gates and editable native document qualification."""

import copy
import json

import pytest
from pydantic import ValidationError

from bigbrain.cad_workflow import CadWorkflow
from bigbrain.solidcraft import CadError, SolidCraftSession, solidcraft_executable


def construction_commands():
    return [
        {'command': 'sketch.create', 'params': {'plane': 'XY', 'name': 'Base_profile'}},
        {'command': 'sketch.draw.dimensioned', 'params': {
            'command': 'sketch.rectangle.two_point', 'params': {'p0': [0, 0], 'p1': [60, 40]},
            'dimensions': {'width': 'length', 'height': 'width'}, 'locate': True}},
        {'command': 'sketch.finish', 'params': {}},
        {'command': 'solid.extrude', 'params': {'distance': 'thickness',
            'name': 'Base_extrusion', 'body_name': 'Mount_plate'}},
        {'command': 'sketch.create', 'params': {'plane': 'XY', 'offset': 'thickness', 'name': 'Hole_profile'}},
        {'command': 'sketch.draw.dimensioned', 'params': {
            'command': 'sketch.circle.center', 'params': {'center': ['length/2', 'width/2'], 'radius': 4},
            'dimensions': {'diameter': 'diameter'}, 'locate': True}},
        {'command': 'sketch.finish', 'params': {}},
        {'command': 'solid.extrude', 'params': {'distance': 'thickness', 'direction': 'negative',
            'operation': 'cut', 'targets': ['Mount_plate'], 'name': 'Through_hole'}}]


def construction_cut_intents(dimension='width'):
    return [{'id': 'through_hole', 'feature_id': 'body', 'dimension_ids': [dimension],
             'command_index': 7, 'kind': 'through', 'targets': ['Mount_plate'],
             'boundaries': [
                 {'label': 'top', 'origin_mm': ['length/2', 'width/2', 'thickness'],
                  'outward_normal': [0, 0, 1], 'role': 'opening'},
                 {'label': 'bottom', 'origin_mm': ['length/2', 'width/2', 0],
                  'outward_normal': [0, 0, -1], 'role': 'opening'}]}]


def workflow(length=60, diameter=8):
    parameters = [('length', f'{length} mm'), ('width', '40 mm'),
                  ('thickness', '6 mm'), ('diameter', f'{diameter} mm')]
    names = ['Base_profile', 'Base_extrusion', 'Hole_profile', 'Through_hole']
    return CadWorkflow.model_validate({
        'parameters': [{'name': name, 'expression': value, 'unit': 'mm',
                        'purpose': name + ' driving dimension'} for name, value in parameters],
        'sketches': [{'name': name, 'purpose': 'Constrained construction profile'}
                     for name in ('Base_profile', 'Hole_profile')],
        'features': [{'name': name, 'purpose': 'Editable construction feature'} for name in names],
        'bodies': ['Mount_plate'],
        'groups': [{'name': 'Plate_construction', 'features': names,
                    'sketches': ['Base_profile', 'Hole_profile'], 'bodies': ['Mount_plate']}]})


def test_workflow_requires_explained_freedom_and_complete_organization():
    data = workflow().model_dump(mode='json')
    data['sketches'][0]['expected_dof'] = 1
    with pytest.raises(ValidationError, match='explanation'):
        CadWorkflow.model_validate(data)
    data['sketches'][0]['freedom_reason'] = 'Deliberate sliding degree of freedom'
    CadWorkflow.model_validate(data)
    data['groups'][0]['features'].pop()
    with pytest.raises(ValidationError, match='exactly one group'):
        CadWorkflow.model_validate(data)


def test_declared_parameter_dependencies_are_known_and_acyclic():
    data = workflow().model_dump(mode='json')
    data['parameters'][0]['dependencies'] = ['unknown']
    with pytest.raises(ValidationError, match='Unknown parameter dependency'):
        CadWorkflow.model_validate(data)
    data['parameters'][0]['dependencies'] = ['width']
    data['parameters'][1]['dependencies'] = ['length']
    with pytest.raises(ValidationError, match='cycle'):
        CadWorkflow.model_validate(data)


def test_sketch_gate_requires_driving_dimensions_and_solver_evidence():
    profile = {'name': 'Base_profile', 'status': 'solved', 'dof': 0,
               'fully_constrained': True, 'curves': [], 'constraints': []}
    intent = workflow()
    assert any('driving dimension' in issue for issue in intent.sketch_diagnostics(profile))
    profile['constraints'] = [{'type': 'length', 'reference': True}]
    assert intent.sketch_diagnostics(profile)
    profile['constraints'] = [{'type': 'length', 'expression': 'length'}]
    assert intent.sketch_diagnostics(profile) == []
    profile['failing'] = ['k2']
    assert any('solver status' in issue for issue in intent.sketch_diagnostics(profile))


@pytest.mark.asyncio
async def test_invalid_sketch_stops_before_extrusion():
    from bigbrain.solidcraft import CadCommandError
    class Candidate:
        construct = SolidCraftSession.construct
        validate_commands = staticmethod(SolidCraftSession.validate_commands)
        def __init__(self):
            self.commands = []
        async def batch(self, commands):
            self.commands.extend(commands)
        async def tool(self, name):
            assert name == 'inspect_design'
            return {'sketches': [{'name': 'Base_profile', 'status': 'solved',
                'dof': 2, 'fully_constrained': False, 'constraints': [], 'curves': []}]}
    candidate = Candidate()
    with pytest.raises(CadCommandError) as failure:
        await candidate.construct(construction_commands(), workflow())
    assert failure.value.result['failed']['stage'] == 'sketch_quality'
    assert candidate.commands[-1]['command'] == 'sketch.finish'
    assert all(item['command'] != 'solid.extrude' for item in candidate.commands)
    candidate.commands.clear()
    invalid = construction_commands() + [{'command': 'document.delete', 'params': {}}]
    with pytest.raises(CadError, match='mutation contract'):
        await candidate.construct(invalid, workflow())
    assert candidate.commands == []


def test_fixed_projected_construction_axis_preserves_dimensional_intent():
    intent = workflow()
    profile = {'name':'Base_profile','status':'solved','dof':0,'fully_constrained':True,
        'failing':[], 'constraints':[{'type':'length'}],
        'curves':[{'fixed':False}, {'fixed':True,'construction':True,'link':'axis-ref'}],
        'links':[{'id':'axis-ref','kind':'project','source':{'type':'sketch_axis','name':'y'}}]}
    assert intent.sketch_diagnostics(profile) == []
    for change in ({'construction':False}, {'link':'missing'}, {'link':None}):
        rejected = copy.deepcopy(profile)
        rejected['curves'][1].update(change)
        assert any('fixation' in issue for issue in intent.sketch_diagnostics(rejected))
    rejected = copy.deepcopy(profile)
    rejected['links'][0]['kind'] = 'unknown'
    assert any('fixation' in issue for issue in intent.sketch_diagnostics(rejected))


@pytest.mark.asyncio
async def test_fresh_proposal_cannot_omit_professional_design_intent():
    from tests.test_cad_integration import Provider, recipe
    from bigbrain.cad_planning import draft_cad_plan
    provider = Provider(recipe())
    with pytest.raises(ValueError, match='require parametric workflow'):
        await draft_cad_plan(provider, 'Create an editable plate', require_workflow=True)
    assert len(provider.calls) == 2
    assert 'workflow' in provider.calls[1]['messages'][-1]['content']


@pytest.mark.asyncio
async def test_construction_preflight_corrects_once_with_definition_preserved():
    from tests.test_cad_drawings import drawing
    from bigbrain.cad_stages import CadDefinition, draft_construction
    definition = CadDefinition.model_validate({'title': 'Plate', 'objective': 'Build the confirmed plate', 'drawing': drawing()})
    good = {'title': 'Plate', 'workflow': workflow().model_dump(mode='json'), 'commands': construction_commands(),
            'cut_intents': construction_cut_intents()}
    bad = copy.deepcopy(good)
    bad['workflow']['features'] = [f for f in bad['workflow']['features'] if f['name'] != 'Base_profile']
    bad['workflow']['groups'][0]['features'].remove('Base_profile')
    class CorrectingProvider:
        def __init__(self):
            self.calls = []
        async def chat_complete(self, **kwargs):
            self.calls.append(kwargs)
            return json.dumps(bad if len(self.calls) == 1 else good)
    provider = CorrectingProvider()
    result = await draft_construction(provider, definition, [], [])
    assert len(provider.calls) == 2
    assert result.workflow == workflow()
    assert 'Every sketch must be a declared history feature' in provider.calls[1]['messages'][-1]['content']
    initial = provider.calls[0]['messages'][1]['content']
    assert provider.calls[1]['messages'][1]['content'] == initial
    assert json.loads(initial[0]['text'])['definition'] == definition.model_dump(mode='json')


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['commands', 'drawing', 'workflow', 'max_repairs'])
async def test_inspection_cannot_replace_construction_authority(field):
    from tests.test_cad_drawings import drawing
    from tests.test_cad_integration import Provider
    from bigbrain.cad_stages import CadDefinition, CadConstruction, inspect_candidate
    definition = CadDefinition.model_validate({'title': 'Plate', 'objective': 'Build the plate', 'drawing': drawing()})
    construction = CadConstruction.model_validate({'title': 'Plate', 'workflow': workflow().model_dump(mode='json'),
        'commands': construction_commands()})
    proposal = {'title': 'Plate', 'criteria': [{'id': 'bounds', 'label': 'Envelope',
        'metric': 'dimensions_mm', 'expected': [60, 40, 6], 'dimension_bindings': {'width': 0}}], field: None}
    provider = Provider(proposal)
    before = definition.model_dump_json(), construction.model_dump_json()
    with pytest.raises(ValueError, match='verification fields exclusively'):
        await inspect_candidate(provider, definition, construction, {})
    assert len(provider.calls) == 2
    assert before == (definition.model_dump_json(), construction.model_dump_json())


@pytest.mark.asyncio
async def test_native_coordinate_expressions_require_functional_dimensions(tmp_path):
    try:
        solidcraft_executable()
    except CadError:
        pytest.skip('SolidCraft 0.28.0 native installation is required')
    intent = CadWorkflow.model_validate({
        'parameters': [{'name': 'span', 'expression': '60 mm', 'unit': 'mm', 'purpose': 'Driving span'},
                       {'name': 'height', 'expression': '40 mm', 'unit': 'mm', 'purpose': 'Driving profile height'}],
        'sketches': [{'name': 'Outline', 'purpose': 'Expression-driven outline'}],
        'features': [{'name': 'Outline', 'purpose': 'Sketch profile'}, {'name': 'Base', 'purpose': 'Extruded base'}],
        'bodies': ['Plate'], 'groups': [{'name': 'Construction', 'features': ['Outline', 'Base'],
            'sketches': ['Outline'], 'bodies': ['Plate']}]})
    async with SolidCraftSession(tmp_path) as session:
        await session.batch([intent.parameter_command(),
            {'command': 'sketch.create', 'params': {'plane': 'XY', 'name': 'Outline'}},
            {'command': 'sketch.line', 'params': {'points': [[0, 0], ['span', 0], ['span', 'height'], [0, 'height']], 'closed': True, 'infer': False}},
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'solid.extrude', 'params': {'distance': 6, 'name': 'Base', 'body_name': 'Plate'}}])
        design = await session.tool('inspect_design')
        graph = await session.tool('execute', {'command': 'parameters.graph', 'params': {}})
        assert any('no driving dimension' in message for message in intent.diagnostics(design, graph))
        stripped = {**graph, 'edges': []}
        assert any('no driving dimension' in message for message in intent.diagnostics(design, stripped))
        await session.batch([{'command': 'parameters.change', 'params': {'name': 'span', 'expression': '80 mm'}}])
        changed = await session.tool('inspect_design')
        assert changed['sketches'][0]['dof'] == 0
        assert any(point['at'] == [80, 40] for point in changed['sketches'][0]['points'])


@pytest.mark.asyncio
async def test_native_angle_provenance_compares_radians_as_degrees(tmp_path):
    from tests.test_cad_drawings import drawing
    from bigbrain.cad_drawings import DrawingSpecification
    try:
        solidcraft_executable()
    except CadError:
        pytest.skip('SolidCraft 0.28.0 native installation is required')
    data = drawing()
    data['dimensions'][0].update(id='angle', kind='angle', value=45, unit='degree')
    spec = DrawingSpecification.model_validate(data)
    intent = CadWorkflow.model_validate({'parameters': [{'name': 'bevel_angle', 'expression': '45 deg',
        'unit': 'deg', 'purpose': 'Confirmed chamfer angle', 'source_dimension': 'angle'}],
        'features': [{'name': 'Blank', 'purpose': 'Native qualification blank'}], 'bodies': ['Plate'],
        'groups': [{'name': 'Construction', 'features': ['Blank'], 'bodies': ['Plate']}],
        'primitive_reason': 'Primitive blank isolates angular parameter provenance'})
    async with SolidCraftSession(tmp_path) as session:
        await session.batch([intent.parameter_command(), {'command': 'solid.box', 'params': {
            'length': 60, 'width': 40, 'height': 6, 'name': 'Blank', 'body_name': 'Plate'}}])
        observed = await session.tool('inspect_design')
        graph = await session.tool('execute', {'command': 'parameters.graph', 'params': {}})
        assert observed['params'][0]['value'] == pytest.approx(0.7853981633974483)
        assert intent.diagnostics(observed, graph, spec) == []
        wrong = spec.model_copy(update={'dimensions': (spec.dimensions[0].model_copy(update={'value': 40}),)})
        assert any('authoritative dimension' in error for error in intent.diagnostics(observed, graph, wrong))


@pytest.mark.asyncio
async def test_native_parametric_edit_preserves_constraints_history_and_saved_groups(tmp_path):
    try:
        solidcraft_executable()
    except CadError:
        pytest.skip('SolidCraft 0.28.0 native installation is required')
    first = workflow()
    async with SolidCraftSession(tmp_path) as session:
        await session.batch([first.parameter_command()])
        await session.batch([
            {'command': 'sketch.create', 'params': {'plane': 'XY', 'name': 'Base_profile'}},
            {'command': 'sketch.draw.dimensioned', 'params': {
                'command': 'sketch.rectangle.two_point', 'params': {'p0': [0, 0], 'p1': [60, 40]},
                'dimensions': {'width': 'length', 'height': 'width'}, 'locate': True}},
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'solid.extrude', 'params': {'distance': 'thickness',
                'name': 'Base_extrusion', 'body_name': 'Mount_plate'}},
            {'command': 'sketch.create', 'params': {'plane': 'XY', 'offset': 'thickness', 'name': 'Hole_profile'}},
            {'command': 'sketch.draw.dimensioned', 'params': {
                'command': 'sketch.circle.center', 'params': {'center': ['length/2', 'width/2'], 'radius': 4},
                'dimensions': {'diameter': 'diameter'}, 'locate': True}},
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'solid.extrude', 'params': {'distance': 'thickness', 'direction': 'negative',
                'operation': 'cut', 'targets': ['Mount_plate'], 'name': 'Through_hole'}}])
        before = await session.tool('inspect_design')
        graph = await session.tool('execute', {'command': 'parameters.graph', 'params': {}})
        assert first.diagnostics(before, graph) == []
        for rows in ([{'name': 'bad_length', 'expression': '90 deg', 'unit': 'mm'}],
                     [{'name': 'a', 'expression': 'b + 1 mm', 'unit': 'mm'},
                      {'name': 'b', 'expression': 'a + 1 mm', 'unit': 'mm'}]):
            with pytest.raises(CadError):
                await session.tool('execute', {'command': 'parameters.import', 'params': {'text': json.dumps(rows)}})
            assert await session.tool('execute', {'command': 'parameters.graph', 'params': {}}) == graph
        await first.arrange(session, before)
        capture = await session.capture('professional-plate', 'Professional plate', 1)
        before = await session.tool('inspect_design')
        native = tmp_path / capture.document.native.path
        assert first.saved_diagnostics(native, before) == []
        groups = first.read_native(native)

        # The second revision changes native expressions on the reopened model.
        await session.reopen(capture.document.native)
        edited = workflow(80, 10)
        await session.batch([edited.parameter_command()])
        after = await session.tool('inspect_design')
        graph = await session.tool('execute', {'command': 'parameters.graph', 'params': {}})
        assert edited.diagnostics(after, graph) == []
        await edited.arrange(session, after, existing_native=native)
        second = await session.capture('professional-plate', 'Professional plate', 2)
        after = await session.tool('inspect_design')
        second_native = tmp_path / second.document.native.path
        assert edited.saved_diagnostics(second_native, after) == []
        saved = edited.read_native(second_native)
        assert saved['timeline_groups'] == groups['timeline_groups']
        assert saved['browser_groups'] == groups['browser_groups']
        assert [(f['id'], f['name']) for f in after['timeline']] == [(f['id'], f['name']) for f in before['timeline']]
        assert second.geometry.bounds_max_mm == pytest.approx([80, 40, 6])
        assert second.document.native.sha256 != capture.document.native.sha256
        hole = next(s for s in after['sketches'] if s['name'] == 'Hole_profile')
        (tmp_path / 'edit-evidence.json').write_text(json.dumps({'before': before, 'after': after, 'graph': graph}))
        assert any(p.get('at') == [40, 20] for p in hole['points'])
        circle = next(c for c in hole['curves'] if c['type'] == 'circle')
        assert circle['radius'] == pytest.approx(5)
        assert circle['center_at'] == pytest.approx([40, 20])
        await session.reopen(second.document.native)
        reopened = await session.tool('inspect_design')
        assert edited.diagnostics(reopened, graph) == []
        assert edited.saved_diagnostics(second_native, reopened) == []

        fixed = copy.deepcopy(reopened)
        fixed['sketches'][0]['curves'][0]['fixed'] = True
        assert any('fixation' in issue for issue in edited.diagnostics(fixed, graph))
        broken = copy.deepcopy(reopened)
        broken['sketches'][0]['dof'] = 1
        assert any('degrees of freedom' in issue for issue in edited.diagnostics(broken, graph))


@pytest.mark.asyncio
async def test_worker_delivery_and_existing_edit_keep_quality_evidence(tmp_path):
    from tests.test_cad_integration import prepared, task
    from bigbrain.brains.cad_brain import CadBrain
    from bigbrain.bus.bus import MessageBus
    from bigbrain.cad_store import CadStore
    from bigbrain.verification.evidence import default_repository

    try:
        solidcraft_executable()
    except CadError:
        pytest.skip('SolidCraft 0.28.0 native installation is required')
    bus = MessageBus(tmp_path / 'bus', auth=None)
    worker = CadBrain('cad_brain', bus)
    def recipe(length, diameter, commands):
        return {'title': 'Editable plate', 'workflow': workflow(length, diameter).model_dump(mode='json'),
            'commands': commands, 'cut_intents': construction_cut_intents() if len(commands) > 1 else [], 'criteria': [
                {'id': 'envelope', 'label': 'Envelope', 'metric': 'dimensions_mm', 'expected': [length, 40, 6]},
                {'id': 'closed', 'label': 'Closed solid', 'metric': 'closed_solid', 'expected': [1]}]}
    try:
        plan, spec, _ = await prepared(bus, recipe(60, 8, construction_commands()))
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        first = await worker.handle_task(task(plan, confirmed))
        assert first['success'], first
        view = first['cad']
        document = view['document']['document_id']
        root = CadStore().directory(document)
        initial = CadWorkflow.read_native(root / view['document']['native']['path'])
        commands = [{'command': 'parameters.change', 'params': {'name': 'length', 'expression': '80 mm'}}]
        plan, spec, _ = await prepared(bus, recipe(80, 10, commands), document_id=document, revision=1)
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        result = await worker.handle_task(task(plan, confirmed))
        assert result['success'], result
        view = result['cad']
        assert view['geometry']['bounds_max_mm'] == pytest.approx([80, 40, 6])
        quality = next(c for c in view['checks'] if c['criterion_id'] == 'design-quality')
        assert quality['status'] == 'passed'
        safety_check = next(c for c in view['checks'] if c['criterion_id'] == 'cut-safety')
        safety_evidence = json.loads((root / safety_check['evidence_ref']).read_text())
        assert safety_evidence['source_sha256'] == view['document']['native']['sha256']
        assert safety_evidence['retained_validation']['previous_source_sha256'] == first['cad']['document']['native']['sha256']
        evidence = json.loads((root / quality['evidence_ref']).read_text())
        assert evidence['source_sha256'] == view['document']['native']['sha256']
        assert evidence['diagnostics'] == []
        saved = CadWorkflow.read_native(root / view['document']['native']['path'])
        assert saved['timeline_groups'] == initial['timeline_groups']
        assert saved['browser_groups'] == initial['browser_groups']
        hole = next(s for s in evidence['design']['sketches'] if s['name'] == 'Hole_profile')
        circle = next(c for c in hole['curves'] if c['type'] == 'circle')
        assert circle['radius'] == pytest.approx(5)
        assert circle['center_at'] == pytest.approx([40, 20])
        # A mismatched design intent must preserve the last delivered revision.
        invalid = recipe(80, 10, commands)
        invalid['workflow']['sketches'][0]['expected_dof'] = 1
        invalid['workflow']['sketches'][0]['freedom_reason'] = 'Expected sliding construction profile'
        plan, spec, _ = await prepared(bus, invalid, document_id=document, revision=view['document']['revision'])
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        failed = await worker.handle_task(task(plan, confirmed))
        assert failed['success'] is False and failed['delivery_status'] == 'incomplete'
        assert CadStore().view(document, 'session-cad')['document'] == view['document']
        failures = [json.loads(path.read_text()) for path in root.glob('command-failure-*.json')]
        assert any(item['engine_result']['failed'].get('stage') == 'design_quality' for item in failures)
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_confirmed_drawing_constructs_then_inspects_actual_candidate(tmp_path):
    from types import SimpleNamespace
    from tests.test_cad_clarification import fixture
    from tests.test_cad_integration import prepared, task
    from bigbrain.brains.cad_brain import CadBrain
    from bigbrain.bus.bus import MessageBus
    from bigbrain.cad_store import CadStore
    from bigbrain.verification.evidence import default_repository

    try:
        solidcraft_executable()
    except CadError:
        pytest.skip('SolidCraft 0.28.0 native installation is required')
    _, sid, _, drawing = fixture()
    drawing['dimensions'][0].update(id='length', kind='length', value=60, unit='mm')
    intent = workflow().model_dump(mode='json')
    intent['parameters'][0]['source_dimension'] = 'length'
    construction = {'title': 'Constrained plate', 'commands': construction_commands(), 'workflow': intent,
                    'cut_intents': construction_cut_intents('length')}
    inspection = {'title': 'Constrained plate', 'criteria': [
        {'id': 'bounds', 'label': 'Envelope', 'metric': 'dimensions_mm',
         'expected': [60, 40, 6], 'dimension_bindings': {'length': 0}}]}
    class StagedProvider:
        entry = SimpleNamespace(vision=True)
        def __init__(self):
            self.calls = []
        async def chat_complete(self, **kwargs):
            self.calls.append(kwargs)
            assert len(self.calls) <= 6
            if isinstance(kwargs['messages'][-1]['content'], list):
                from tests.test_cad_controller import fixture_decision
                return json.dumps(fixture_decision(kwargs, construction))
            return json.dumps(inspection)
    provider = StagedProvider()
    bus = MessageBus(tmp_path / 'bus', auth=None)
    try:
        plan, spec, planning_provider = await prepared(bus, inspection, drawing=drawing, session_id=sid)
        assert planning_provider.calls == []
        assert 'definition' in spec.metadata['cad'] and 'plan' not in spec.metadata['cad']
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        result = await CadBrain('cad_brain', bus, llm_provider=provider).handle_task(task(plan, confirmed))
        assert result['success'], result
        assert len(provider.calls) == 6
        for call in provider.calls[:5]:
            authority = json.loads(call['messages'][-1]['content'][0]['text'])['execution_authorization']
            assert authority['status'] == 'confirmed'
            assert authority['design_id'] == confirmed.design_id
            assert authority['revision'] == confirmed.revision
            assert authority['approval_plan_id'] == plan.id
            assert authority['document_id'] == result['cad']['document']['document_id']
        assert any(b.get('type') == 'image_url' for b in provider.calls[0]['messages'][-1]['content'])
        packet = json.loads(provider.calls[-1]['messages'][-1]['content'])
        view = result['cad']
        assert packet['candidate_observations']['source_sha256'] == view['document']['native']['sha256']
        assert packet['candidate_observations']['topology']['Mount_plate']
        assert packet['construction']['workflow']['parameters'][0]['source_dimension'] == 'length'
        assert all(c['status'] == 'passed' for c in view['checks'])
        root = CadStore().directory(view['document']['document_id'])
        assert (root / 'revision-1/inspection-input.json').is_file()
        assert (root / 'revision-1/inspection-plan.json').is_file()
        retained = json.loads((root / 'revision-1/inspection-plan.json').read_text())
        assert retained['max_repairs'] == 2
        assert retained['workflow'] == construction['workflow'] | {'schema_version': '1.0'}
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_interrupted_inspection_resumes_owned_recipe_without_front_or_construction(tmp_path):
    from types import SimpleNamespace
    from tests.test_cad_clarification import fixture
    from tests.test_cad_integration import prepared, task
    from bigbrain.brains.cad_brain import CadBrain
    from bigbrain.bus.bus import MessageBus
    from bigbrain.bus.message import BusMessage, MessageType
    from bigbrain.cad_runs import CadRunCheckpoint, confirmed_continuation
    from bigbrain.cad_store import CadStore
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator
    from bigbrain.verification.evidence import default_repository
    try:
        solidcraft_executable()
    except CadError:
        pytest.skip('SolidCraft 0.28.0 native installation is required')
    _, sid, _, drawing = fixture()
    drawing['dimensions'][0].update(id='length', value=60)
    construction = {'title': 'Plate', 'commands': construction_commands(), 'workflow': workflow().model_dump(mode='json'),
                    'cut_intents': construction_cut_intents('length')}
    inspection = {'title': 'Plate', 'criteria': [{'id': 'bounds', 'label': 'Envelope',
        'metric': 'dimensions_mm', 'expected': [60, 40, 6], 'dimension_bindings': {'length': 0}}]}
    class Provider:
        entry = SimpleNamespace(vision=True)
        def __init__(self, resumed=False):
            self.calls, self.resumed, self.scopes = [], resumed, []
        async def chat_complete(self, **kwargs):
            from bigbrain.llm.conversation import current_conversation
            self.scopes.append(current_conversation.get())
            self.calls.append(kwargs)
            if self.resumed:
                assert 'candidate_observations' in kwargs['messages'][-1]['content']
                return json.dumps(inspection)
            if isinstance(kwargs['messages'][-1]['content'], list):
                from tests.test_cad_controller import fixture_decision
                return json.dumps(fixture_decision(kwargs, construction))
            raise TimeoutError('Interrupted inspection')
    bus = MessageBus(tmp_path / 'bus', auth=None)
    try:
        plan, spec, planner = await prepared(bus, inspection, drawing=drawing, session_id=sid)
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        provider = Provider()
        failed = await CadBrain('cad_brain', bus, llm_provider=provider).handle_task(task(plan, confirmed))
        assert failed['success'] is False and len(provider.calls) == 6
        assert set(provider.scopes) == {(sid, 'worker:cad_brain')}
        checkpoint = CadRunCheckpoint(CadStore(), confirmed, sid)
        state = checkpoint.load()
        assert state['kind'] == 'construction'
        document = state['document_id']
        assert confirmed_continuation(document, sid)[0] == confirmed
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        from bigbrain.web.cad_api import setup_cad_routes
        class CaptureBus:
            def __init__(self):
                self.messages = []
            async def send(self, message):
                self.messages.append(message)
        transport = CaptureBus()
        app = web.Application()
        setup_cad_routes(app, bus=transport)
        async with TestClient(TestServer(app)) as client:
            headers = {'Origin': str(client.make_url('')).rstrip('/'), 'X-BigBrain-CAD': '1'}
            response = await client.post('/api/cad/resume', json={'documentId': document, 'sessionId': sid}, headers=headers)
            assert response.status == 200 and (await response.json())['queued']
            assert transport.messages[0].payload == {'type': 'cad.resume', 'document_id': document, 'session_id': sid}
            refused = await client.post('/api/cad/resume', json={'documentId': document, 'sessionId': 'unrelated'}, headers=headers)
            assert refused.status == 400 and len(transport.messages) == 1
        with pytest.raises(CadError, match='another conversation'):
            confirmed_continuation(document, 'unrelated')
        with pytest.raises(CadError, match='another conversation'):
            CadRunCheckpoint(CadStore(), confirmed, 'unrelated')
        resumed = Provider(resumed=True)
        orchestrator = WorkspaceOrchestrator('default', bus, llm_provider=resumed)
        orchestrator.register_brain('cad_brain', {'description': 'CAD'})
        await orchestrator._handle_task_request(BusMessage(type=MessageType.TASK, source='morphable_ui',
            target=orchestrator.name, payload={'type': 'cad.resume', 'document_id': document, 'session_id': sid}))
        resumed_plan = next(iter(orchestrator.task_plans.values()))
        message = task(resumed_plan, confirmed)
        result = await CadBrain('cad_brain', bus, llm_provider=resumed).handle_task(message)
        assert result['success'], result
        assert len(resumed.calls) == 1 and planner.calls == []
        assert result['cad']['document']['document_id'] == document
        assert all(item['status'] == 'passed' for item in result['cad']['checks'])
        with pytest.raises(CadError, match='already has a delivered revision'):
            confirmed_continuation(document, sid)
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_progressive_measurement_interruption_keeps_native_prefix(tmp_path, monkeypatch, cad_native_engine):
    from types import SimpleNamespace
    from tests.test_cad_clarification import fixture
    from tests.test_cad_controller import fixture_decision
    from tests.test_cad_integration import prepared, task
    from bigbrain.brains.cad_brain import CadBrain
    from bigbrain.bus.bus import MessageBus
    from bigbrain.cad_execution import CadExecutionStore
    from bigbrain.cad_planning import CadCriterion
    from bigbrain.cad_runs import CadRunCheckpoint
    from bigbrain.cad_store import CadStore
    from bigbrain.verification.evidence import default_repository

    _, sid, _, drawing = fixture()
    drawing['dimensions'][0].update(id='length', kind='length', value=60, unit='mm')
    construction = {'title': 'Plate', 'commands': construction_commands(),
        'workflow': workflow().model_dump(mode='json'), 'cut_intents': construction_cut_intents('length')}
    inspection = {'title': 'Plate', 'criteria': [{'id': 'bounds', 'label': 'Envelope',
        'metric': 'dimensions_mm', 'expected': [60, 40, 6], 'dimension_bindings': {'length': 0}}]}

    class Provider:
        entry = SimpleNamespace(vision=True)

        def __init__(self):
            self.calls = []

        async def chat_complete(self, **kwargs):
            self.calls.append(kwargs)
            if isinstance(kwargs['messages'][-1]['content'], list):
                return json.dumps(fixture_decision(kwargs, construction))
            return json.dumps(inspection)

    bus = MessageBus(tmp_path / 'bus', auth=None)
    try:
        plan, spec, _ = await prepared(bus, inspection, drawing=drawing, session_id=sid)
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        provider = Provider()
        original = CadCriterion.observe

        def interrupted(*args, **kwargs):
            raise RuntimeError('Synthetic measurement interruption')

        with monkeypatch.context() as patch:
            patch.setattr(CadCriterion, 'observe', interrupted)
            failed = await CadBrain('cad_brain', bus, llm_provider=provider).handle_task(task(plan, confirmed))
        assert not failed['success'] and failed['delivery_status'] == 'incomplete'
        checkpoint = CadRunCheckpoint(CadStore(), confirmed, sid)
        state = checkpoint.load()
        assert state['kind'] == 'inspection'
        root = CadStore().directory(state['document_id'])
        prefix = [c.id for c in CadExecutionStore(root, checkpoint.digest).active()]
        assert len(prefix) == 4 and len(provider.calls) == 6
        assert CadCriterion.observe is original
        calls_before_recovery = len(provider.calls)
        result = await CadBrain('cad_brain', bus, llm_provider=provider).handle_task(task(plan, confirmed))
        assert result['success'], result
        assert len(provider.calls) == calls_before_recovery
        assert [c.id for c in CadExecutionStore(root, checkpoint.digest).active()] == prefix
        assert result['cad']['document']['revision'] == 2
    finally:
        await bus.close()
