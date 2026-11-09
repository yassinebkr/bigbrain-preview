"""Offline regressions for observation scope, native prereads and repair evidence."""

import json

import pytest

from bigbrain.cad_controller import CadConstructionDriver, Observe, observation_key
from bigbrain.cad_execution import CadExecutionStore
from bigbrain.solidcraft import CadError, SolidCraftSession
from tests.test_cad_controller import Decisions, actions, definition


@pytest.mark.parametrize('tool,body,feature,valid', [
    ('inspect_design', None, None, True),
    ('parameter_graph', None, None, True),
    ('precise_geometry', None, None, True),
    ('precise_geometry', 'BodyA', None, True),
    ('body_topology', 'BodyA', None, True),
    ('feature_definition', None, 'Profile', True),
    ('body_topology', None, None, False),
    ('body_topology', 'Unknown', None, False),
    ('precise_geometry', 'Unknown', None, False),
    ('feature_definition', None, 'Unknown', False),
    ('feature_definition', 'BodyA', 'Profile', False),
    ('inspect_design', 'BodyA', None, False),
    ('parameter_graph', 'BodyA', None, False),
    ('precise_geometry', None, 'Profile', False),
    ('body_topology', 'BodyA', 'Profile', False),
])
def test_observation_target_matrix(tool, body, feature, valid):
    decision = Observe(operation='observe', tool=tool, body=body, feature=feature,
        question='Which current native evidence answers the construction question?')
    design = {'timeline': [{'name': 'Profile'}], 'bodies': [{'name': 'BodyA'}]}
    if valid:
        key = observation_key(decision, design)
        if tool == 'precise_geometry':
            assert key == 'precise_geometry:'
    else:
        with pytest.raises(ValueError):
            observation_key(decision, design)


@pytest.mark.asyncio
async def test_every_decision_receives_fresh_native_topology_without_read_decisions(tmp_path, cad_native_engine):
    provider = Decisions(actions())
    store = CadExecutionStore(tmp_path, 'a' * 64)
    async with SolidCraftSession(tmp_path) as session:
        await CadConstructionDriver(provider, definition(), [], [], store).run(session)
    assert len(provider.calls) == 5
    assert 'body_topology:Mount_plate' not in provider.calls[1]['observations']
    for packet in provider.calls[2:]:
        observed = packet['observations']['body_topology:Mount_plate']
        assert observed['checkpoint'] == packet['base_checkpoint']
        assert observed['source'] == 'runtime_native_read'
        assert observed['result']['body'] == 'Mount_plate'
        assert observed['result']['faces']
    # The hole changes topology. Both sides retain their own native observation.
    assert provider.calls[2]['base_checkpoint'] != provider.calls[4]['base_checkpoint']
    assert (provider.calls[2]['observations']['body_topology:Mount_plate']['result'] !=
            provider.calls[4]['observations']['body_topology:Mount_plate']['result'])


@pytest.mark.asyncio
async def test_same_checkpoint_preread_is_cached_and_wrong_body_is_rejected(tmp_path, cad_native_engine):
    values = actions()
    provider = Decisions([*values[:2], {'operation': 'blocked', 'reason': 'Stop after runtime topology read'}])
    store = CadExecutionStore(tmp_path, 'a' * 64)
    async with SolidCraftSession(tmp_path) as session:
        driver = CadConstructionDriver(provider, definition(), [], [], store)
        with pytest.raises(CadError, match='Stop after runtime topology read'):
            await driver.run(session)
        count = sum(x['tool'] == 'body_topology' for x in session.observations)
        await driver.supply_topology(session)
        assert sum(x['tool'] == 'body_topology' for x in session.observations) == count
        driver.state['observations'].clear()
        original = session.tool
        async def wrong_body(name, arguments=None):
            if name == 'body_topology':
                return {'body': 'AnotherBody', 'faces': []}
            return await original(name, arguments)
        session.tool = wrong_body
        with pytest.raises(CadError, match='another body'):
            await driver.supply_topology(session)


@pytest.mark.asyncio
async def test_face_extrusion_reports_actual_undeclared_objects_and_preserves_prefix(tmp_path, cad_native_engine):
    values = actions()
    extension = json.loads(json.dumps(values[1]))
    extension['group']['id'] = 'face-extension'
    extension['group']['commands'] = [{'command': 'solid.extrude', 'params': {
        'face': [30, 20, 6], 'face_body': 'Mount_plate', 'distance': 2,
        'operation': 'join', 'targets': ['Mount_plate'], 'name': 'Extension'}}]
    extension['group']['workflow']['features'].append({'name': 'Extension', 'purpose': 'Extend the native top face'})
    extension['group']['workflow']['groups'][0]['features'].append('Extension')
    provider = Decisions([*values[:2], extension,
        {'operation': 'blocked', 'reason': 'Stop after rejected inventory evidence'}])
    store = CadExecutionStore(tmp_path, 'a' * 64)
    async with SolidCraftSession(tmp_path) as session:
        with pytest.raises(CadError, match='Stop after rejected inventory evidence'):
            await CadConstructionDriver(provider, definition(), [], [], store).run(session)
    assert len(store.active()) == 2
    failure = provider.calls[-1]['failures'][-1]['diagnostic']
    errors = failure['diagnostics']
    assert any('undeclared construction objects: ' in message for message in errors)
    rejected = store._read(tmp_path / failure['observation_ref'])
    assert failure['observed_inventory']['sketches'] == [s['name'] for s in rejected['design']['sketches']]
    assert 'Mount_plate' in failure['observed_inventory']['bodies']
    assert (tmp_path / failure['observation_ref']).is_file()
