"""Independent capacities for authored measurements and mandatory runtime gates."""
from copy import deepcopy
import pytest
from bigbrain.cad_planning import CadPlan
from bigbrain.cad_contracts import CAD_CHECK_CAPACITIES, MAX_PROPOSED_CHECKS, MAX_DELIVERY_CHECKS, CadDelivery
from tests.test_cad_workflow import workflow, construction_commands, construction_cut_intents


def test_model_check_capacity_excludes_runtime_slots(monkeypatch):
    monkeypatch.setattr('bigbrain.cad_planning.measurement_diagnostics', lambda _: [])
    data = {'title': 'Capacity fixture', 'commands': construction_commands(),
        'workflow': workflow().model_dump(mode='json'), 'cut_intents': construction_cut_intents(),
        'criteria': [{'id': f'c{i}', 'label': 'Bounds', 'metric': 'dimensions_mm', 'expected': [60, 40, 6]}
                     for i in range(16)],
        'sections': [{'id': f's{i}', 'label': 'Through line', 'axis': 0,
                      'point_mm': [0, 0, 0], 'intervals_mm': []} for i in range(32)],
        'vertices': [{'id': f'v{i}', 'label': 'Endpoint', 'body': 'Mount_plate',
                      'point_mm': [0, 0, 0]} for i in range(16)]}
    data['cylinders'] = [{'id': f'y{i}', 'label': 'Cylinder', 'body': 'Mount_plate',
        'axis': 2, 'center_mm': [0, 0, 0], 'radius_mm': 1} for i in range(16)]
    data['measurements'] = [{'id': f'm{i}', 'dimension_id': 'width',
        'first': {'source': 'vertex', 'reference': 'v0', 'quantity': 'coordinate', 'axis': 0}}
        for i in range(32)]
    assert sum(len(data[key]) for key in CAD_CHECK_CAPACITIES) == MAX_PROPOSED_CHECKS == 112
    plan = CadPlan.model_validate(data)
    assert plan.workflow is not None
    assert CadDelivery.model_json_schema()['properties']['checks']['maxItems'] == MAX_DELIVERY_CHECKS == 114
    overflow = deepcopy(data)
    overflow['measurements'].append({**data['measurements'][0], 'id': 'overflow'})
    with pytest.raises(ValueError, match='at most 32'):
        CadPlan.model_validate(overflow)


@pytest.mark.asyncio
async def test_inspection_stops_before_retry_when_operator_requests_diagnosis():
    from bigbrain.cad_stages import CadConstruction, inspect_candidate
    from tests.test_cad_controller import definition

    class Provider:
        calls = 0
        async def chat_complete(self, **kwargs):
            self.calls += 1
            return '{}'

    construction = CadConstruction(title='Plate', commands=construction_commands(), workflow=workflow(),
                                  cut_intents=construction_cut_intents())
    provider = Provider()
    with pytest.raises(ValueError):
        await inspect_candidate(provider, definition(), construction, {}, stop_on_error=True)
    assert provider.calls == 1
