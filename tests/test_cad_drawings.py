"""Drawing provenance and uncertainty gates before native geometry mutation."""

import pytest
from pydantic import ValidationError

from bigbrain.cad_drawings import DrawingSpecification


def drawing():
    source = {'attachment_id': 'att-012345abcdef', 'sha256': 'a' * 64}
    return {'title': 'Stepped support', 'sources': [source], 'views': ['front', 'top'],
            'dimensions': [{'id': 'width', 'feature_id': 'body', 'label': 'Width',
                'kind': 'length', 'value': 60, 'unit': 'mm', 'origin': 'explicit',
                'sources': [source], 'annotation': '60'}]}


def test_explicit_dimension_keeps_source_and_region():
    spec = DrawingSpecification.model_validate(drawing()).require_resolved()
    assert spec.dimensions[0].sources[0].sha256 == 'a' * 64
    assert spec.dimensions[0].sources[0].region == (0, 0, 1, 1)


def test_critical_unreadable_dimension_requires_clarification():
    data = drawing()
    data['dimensions'][0].update(value=None, origin='unresolved', annotation='6?')
    spec = DrawingSpecification.model_validate(data)
    assert len(spec.clarification_questions()) == 1
    with pytest.raises(ValueError, match='clarification'):
        spec.require_resolved()


@pytest.mark.parametrize('change', [
    {'sources': [{'attachment_id': 'att-012345abcdef', 'sha256': 'b' * 64}]},
    {'origin': 'derived', 'dependencies': ['width'], 'derivation': 'same dimension'},
    {'origin': 'derived', 'dependencies': ['missing'], 'derivation': 'unknown'},
    {'value': float('nan')}, {'unit': 'degree'}, {'value': -1},
    {'sources': [{'attachment_id': 'att-012345abcdef', 'sha256': 'a' * 64,
                  'region': [0, 0, 2, 1]}]},
])
def test_invalid_evidence_and_derivations_fail_closed(change):
    data = drawing()
    data['dimensions'][0].update(change)
    with pytest.raises(ValidationError):
        DrawingSpecification.model_validate(data)


def test_conflict_blocks_even_with_numeric_dimension():
    data = drawing()
    data['issues'] = [{'id': 'conflict', 'question': 'Which width is correct, 60 or 65 mm?',
                      'reason': 'conflicting', 'dimension_ids': ['width']}]
    with pytest.raises(ValueError, match='60 or 65'):
        DrawingSpecification.model_validate(data).require_resolved()


def test_derived_dimension_preserves_units_and_dependencies():
    data = drawing()
    dimension = dict(data['dimensions'][0])
    dimension.update(id='half_width', value=30, origin='derived',
                     dependencies=['width'], derivation='width / 2')
    data['dimensions'].append(dimension)
    assert DrawingSpecification.model_validate(data).require_resolved().dimensions[1].value == 30


def test_front_drawing_route_preserves_interpretation_and_blocks_uncertainty():
    from bigbrain.front.decision import CadInput
    payload = {'type': 'model_cad', 'drawing': drawing()}
    assert CadInput.model_validate(payload).drawing.dimensions[0].value == 60
    payload['drawing']['dimensions'][0].update(value=None, origin='unresolved')
    with pytest.raises(ValidationError, match='clarification'):
        CadInput.model_validate(payload)


@pytest.mark.asyncio
async def test_planner_cannot_replace_drawing_authority():
    import json
    from bigbrain.cad_planning import draft_cad_plan
    spec = DrawingSpecification.model_validate(drawing())

    class Planner:
        async def chat_complete(self, **arguments):
            prompt = json.loads(arguments['messages'][1]['content'])
            assert prompt['drawing']['sources'][0]['sha256'] == 'a' * 64
            assert 'image_url' not in arguments['messages'][1]['content']
            return json.dumps({'title': 'Support', 'commands': [
                {'command': 'solid.box', 'params': {'length': 60, 'width': 40, 'height': 6}}],
                'criteria': [{'id': 'bounds', 'label': 'Envelope', 'metric': 'dimensions_mm',
                              'expected': [60, 40, 6], 'dimension_bindings': {'width': 0}}]})

    plan = await draft_cad_plan(Planner(), 'Model this drawing', drawing=spec)
    assert plan.drawing == spec
    assert any('60 mm' in item for item in plan.contracts())


@pytest.mark.asyncio
async def test_recipe_cannot_reinterpret_drawing_or_bind_an_invented_dimension():
    import json
    from bigbrain.cad_planning import CadRecipe, draft_cad_plan
    assert 'drawing' not in CadRecipe.model_json_schema()['properties']
    spec = DrawingSpecification.model_validate(drawing())
    base = {'title': 'Support', 'commands': [{'command': 'solid.box', 'params': {'length': 60, 'width': 40, 'height': 6}}],
            'criteria': [{'id': 'bounds', 'label': 'Envelope', 'metric': 'dimensions_mm', 'expected': [60, 40, 6],
                          'dimension_bindings': {'invented': 0}}]}
    class Planner:
        async def chat_complete(self, **kwargs):
            return json.dumps(base)
    with pytest.raises(ValueError, match='invented.*declared'):
        await draft_cad_plan(Planner(), 'Model this drawing', drawing=spec)
    base['drawing'] = drawing()
    with pytest.raises(ValueError, match='invented a drawing'):
        await draft_cad_plan(Planner(), 'Model this drawing', drawing=spec)


@pytest.mark.asyncio
async def test_planner_receives_source_image_with_authoritative_dossier():
    import json
    from bigbrain.cad_planning import draft_cad_plan
    spec = DrawingSpecification.model_validate(drawing())
    image = {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,AA=='}}
    class Planner:
        async def chat_complete(self, **kwargs):
            blocks = kwargs['messages'][1]['content']
            assert blocks[1] == image
            assert json.loads(blocks[0]['text'])['drawing']['dimensions'][0]['id'] == 'width'
            return json.dumps({'title': 'Support', 'commands': [
                {'command': 'solid.box', 'params': {'length': 60, 'width': 40, 'height': 6}}],
                'criteria': [{'id': 'bounds', 'label': 'Envelope', 'metric': 'dimensions_mm',
                              'expected': [60, 40, 6], 'dimension_bindings': {'width': 0}}]})
    assert (await draft_cad_plan(Planner(), 'Model this drawing', drawing=spec, images=[image])).drawing == spec


def test_angular_drawing_binding_requires_checked_rise_and_run():
    from bigbrain.cad_planning import CadPlan
    data = drawing()
    data['dimensions'].append({**data['dimensions'][0], 'id': 'chamfer-angle',
        'label': 'Chamfer angle', 'kind': 'angle', 'unit': 'degree', 'value': 45})
    plan = {'title': 'Chamfered support', 'drawing': data,
        'commands': [{'command': 'solid.box', 'params': {'length': 60, 'width': 40, 'height': 6}}],
        'criteria': [{'id': 'bounds', 'label': 'Envelope', 'metric': 'dimensions_mm',
            'expected': [60, 40, 6], 'dimension_bindings': {'width': 0}}],
        'sections': [
            {'id': 'rise', 'label': 'Rise sample', 'axis': 2, 'point_mm': [50, 20, 0],
             'intervals_mm': [[0, 10]], 'bindings': [{'dimension_id': 'chamfer-angle',
                'quantity': 'length', 'interval': 0, 'angle_denominator': {
                    'section_id': 'run', 'quantity': 'length', 'interval': 0}}]},
            {'id': 'run', 'label': 'Run sample', 'axis': 0, 'point_mm': [0, 20, 5],
             'intervals_mm': [[0, 10]]}]}
    assert CadPlan.model_validate(plan)
    plan['sections'][1]['intervals_mm'] = [[0, 20]]
    with pytest.raises(ValidationError, match='target differs'):
        CadPlan.model_validate(plan)
    plan['sections'][0]['bindings'][0]['angle_denominator']['section_id'] = 'absent'
    with pytest.raises(ValidationError, match='unknown measured section'):
        CadPlan.model_validate(plan)
