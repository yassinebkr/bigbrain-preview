"""Independent capacities for authored measurements and mandatory runtime gates."""
from copy import deepcopy
import pytest
from bigbrain.cad_planning import CadPlan
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
    assert CadPlan.model_validate(data).workflow is not None
    overflow = deepcopy(data)
    overflow['cylinders'] = [{'id': 'extra', 'label': 'Cylinder', 'body': 'Mount_plate',
        'axis': 2, 'center_mm': [0, 0, 0], 'radius_mm': 1}]
    with pytest.raises(ValueError, match='at most 64 checks'):
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
