"""Construction discovers installed geometry tools without changing its definition."""

import json

import pytest

from bigbrain.cad_tool_reference import CadCommandCatalog
from bigbrain.cad_stages import CadDefinition, draft_construction
from tests.test_cad_drawings import drawing
from tests.test_cad_workflow import workflow, construction_commands, construction_cut_intents


def test_catalog_excludes_file_operations_and_returns_installed_signatures():
    catalog = CadCommandCatalog([], [
        {'id': 'solid.sweep', 'params': 'sketch, path_sketch, path'},
        {'id': 'file.open', 'params': 'path'},
    ])
    assert list(catalog.catalog) == ['solid.sweep']
    assert catalog.selected(['solid.sweep', 'solid.sweep']) == [
        {'id': 'solid.sweep', 'params': 'sketch, path_sketch, path'}]
    with pytest.raises(ValueError, match='unavailable'):
        catalog.selected(['file.open'])


@pytest.mark.asyncio
async def test_native_loader_preserves_schemas_and_refuses_unknown_requests():
    calls = []
    async def loader(names, skills):
        calls.append((names, skills))
        return {'command_reference': [{'id': names[0], 'input': {'type': 'object'}, 'output': None}],
                'skill_reference': {skills[0]: {'text': 'native guide'}}}
    catalog = CadCommandCatalog([], [{'id': 'solid.sweep', 'params': 'path'}], loader)
    result = await catalog.describe(['solid.sweep'], ['solidcraft-modeling'])
    assert result['command_reference'][0]['input'] == {'type': 'object'}
    assert result['skill_reference']['solidcraft-modeling']['text'] == 'native guide'
    with pytest.raises(ValueError, match='unavailable'):
        await catalog.describe(['file.open'])
    with pytest.raises(ValueError, match='unavailable'):
        await catalog.describe([], ['arbitrary-file'])
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_installed_native_discovery():
    from bigbrain.brains.cad_brain import cad_command_reference
    from bigbrain.solidcraft import CadError, solidcraft_executable
    try:
        solidcraft_executable()
    except CadError:
        pytest.skip('Native SolidCraft installation is required')
    catalog = await cad_command_reference()
    result = await catalog.describe(['solid.sweep'], catalog.skills)
    command = result['command_reference'][0]
    assert command['id'] == 'solid.sweep'
    assert 'path_sketch' in command['params']
    assert 'input' in command and 'output' in command
    assert all(result['skill_reference'][skill]['text'] for skill in catalog.skills)


@pytest.mark.asyncio
async def test_construction_requests_related_signatures_before_complete_recipe():
    definition = CadDefinition(title='Plate', objective='Build the complete plate', drawing=drawing())
    catalog = CadCommandCatalog([], [{'id': 'solid.sweep', 'params': 'installed sweep signature'}])
    recipe = {'title': 'Plate', 'commands': construction_commands(), 'workflow': workflow().model_dump(mode='json'),
              'cut_intents': construction_cut_intents()}
    class Provider:
        def __init__(self):
            self.calls = []
        async def chat_complete(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                packet = json.loads(kwargs['messages'][1]['content'][0]['text'])
                assert packet['available_commands'] == ['solid.sweep']
                return json.dumps({'operation': 'request_command_reference', 'commands': ['solid.sweep']})
            signatures = json.loads(kwargs['messages'][-1]['content'])
            assert signatures['command_reference'][0]['params'] == 'installed sweep signature'
            return json.dumps(recipe)
    provider = Provider()
    result = await draft_construction(provider, definition, catalog, [])
    assert len(provider.calls) == 2
    assert result.workflow == workflow()
    assert provider.calls[0]['messages'][1] == provider.calls[1]['messages'][1]


@pytest.mark.asyncio
async def test_repeated_reference_requests_stop_within_allowance():
    class Provider:
        calls = 0
        async def chat_complete(self, **kwargs):
            self.calls += 1
            return json.dumps({'operation': 'request_command_reference', 'commands': ['solid.sweep']})
    provider = Provider()
    catalog = CadCommandCatalog([], [{'id': 'solid.sweep', 'params': 'sketch, path'}])
    definition = CadDefinition(title='Plate', objective='Build the plate', drawing=drawing())
    with pytest.raises(ValueError, match='budget'):
        await draft_construction(provider, definition, catalog, [])
    assert provider.calls == 4


@pytest.mark.asyncio
async def test_reference_correction_preserves_construction_correction_slot():
    definition = CadDefinition(title='Plate', objective='Build the plate', drawing=drawing())
    recipe = {'title': 'Plate', 'commands': construction_commands(),
              'workflow': workflow().model_dump(mode='json'),
              'cut_intents': construction_cut_intents()}
    invalid = {**recipe, 'cut_intents': []}
    responses = [
        {'operation': 'request_command_reference', 'commands': ['unknown.command']},
        invalid, recipe,
    ]

    class Provider:
        calls = 0

        async def chat_complete(self, **kwargs):
            if self.calls == 2:
                assert 'missing indices=' in kwargs['messages'][-1]['content']
            response = responses[self.calls]
            self.calls += 1
            return json.dumps(response)

    provider = Provider()
    catalog = CadCommandCatalog([], [{'id': 'solid.sweep', 'params': 'sketch, path'}])
    result = await draft_construction(provider, definition, catalog, [])
    assert result.cut_intents
    assert provider.calls == 3


@pytest.mark.asyncio
async def test_repair_receives_previously_read_native_reference():
    catalog = CadCommandCatalog([], [{'id': 'solid.sweep', 'params': 'installed signature'}])
    await catalog.describe(['solid.sweep'])
    detached = catalog.retrieved()
    detached['command_reference'].clear()
    definition = CadDefinition(title='Plate', objective='Build the plate', drawing=drawing())
    recipe = {'title': 'Plate', 'commands': construction_commands(),
              'workflow': workflow().model_dump(mode='json'),
              'cut_intents': construction_cut_intents()}

    class Provider:
        async def chat_complete(self, **kwargs):
            packet = json.loads(kwargs['messages'][1]['content'][0]['text'])
            assert packet['retrieved_reference']['command_reference'] == [
                {'id': 'solid.sweep', 'params': 'installed signature'}]
            assert packet['previous_recipe'] == CadConstruction.model_validate(recipe).model_dump(mode='json')
            assert packet['diagnostic_history'] == [{'observed_failure': {'command': 'solid.cone',
                                                                         'stage': 'native_timeout'}}]
            return json.dumps(recipe)

    from bigbrain.cad_stages import CadConstruction
    await draft_construction(Provider(), definition, catalog, [],
                             previous=CadConstruction.model_validate(recipe),
                             diagnostic_history=[{'observed_failure': {'command': 'solid.cone',
                                                                      'stage': 'native_timeout'}}])


@pytest.mark.asyncio
async def test_failed_finish_retains_actual_operand_for_repair(tmp_path):
    from bigbrain.solidcraft import SolidCraftSession, CadCommandError
    async with SolidCraftSession(tmp_path) as session:
        with pytest.raises(CadCommandError) as caught:
            await session.construct([
                {'command': 'solid.box', 'params': {'length': 10, 'width': 10,
                                                   'height': 10, 'body_name': 'Operand'}},
                {'command': 'solid.fillet', 'params': {'body': 'Operand',
                    'edges': [[1000, 1000, 1000]], 'radius': 1}},
            ], enforce_cut_safety=True)
        failed = caught.value.result['failed']
        assert failed['recipe_command_index'] == 1
        geometry = failed['actual_operand_geometry']
        assert geometry['measurements']['body_count'] == 1
        assert geometry['measurements']['total']['volume_mm3'] == pytest.approx(1000)
        assert len(geometry['source_sha256']) == 64
        assert geometry['topology'][0]['body'] == 'Operand'
        assert isinstance(geometry['topology'][0]['edges'], list)
        assert geometry['topology'][0]['edges']
        assert (tmp_path / geometry['evidence_ref']).is_file()
