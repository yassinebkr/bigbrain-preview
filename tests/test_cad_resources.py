"""Explicit capacity extensions preserve default bounds and accumulated usage."""

import json

import pytest
from pydantic import ValidationError

from bigbrain.cad_controller import CadConstructionDriver
from bigbrain.cad_execution import CadExecutionStore, digest
from bigbrain.cad_resources import authorized_capacity, command_capacity
from bigbrain.cad_stages import CadConstruction
from bigbrain.cad_planning import CadPlan
from bigbrain.solidcraft import CadError, SolidCraftSession
from tests.test_cad_controller import Decisions, definition
from tests.test_cad_execution import Session
from tests.test_cad_workflow import construction_commands, construction_cut_intents, workflow


def extended_recipe():
    prefix = [{'command': 'parameters.change', 'params': {'name': 'padding', 'expression': '1 mm'}}] * 64
    intents = construction_cut_intents()
    intents[0]['command_index'] += 64
    return {'title': 'Extended native recipe', 'commands': prefix + construction_commands(),
            'workflow': workflow().model_dump(mode='json'), 'cut_intents': intents}


def test_extended_construction_and_inspection_require_runtime_scope():
    data = extended_recipe()
    with pytest.raises(ValidationError):
        CadConstruction.model_validate(data)
    token = command_capacity.set(96)
    try:
        construction = CadConstruction.model_validate(data)
        assert construction.cut_intents[0].command_index == 71
        inspection = CadPlan.model_validate({**construction.model_dump(mode='json'), 'criteria': [
            {'id': 'size', 'label': 'Measured envelope', 'metric': 'dimensions_mm', 'expected': [60, 40, 6]},
            {'id': 'count', 'label': 'Body count', 'metric': 'body_count', 'expected': [1]}]})
        assert len(inspection.commands) == 72
    finally:
        command_capacity.reset(token)
    with pytest.raises(ValidationError):
        CadPlan.model_validate(inspection.model_dump(mode='json'))


@pytest.mark.asyncio
async def test_extended_native_replay_keeps_each_batch_bounded(tmp_path, cad_native_engine):
    data = extended_recipe()
    token = command_capacity.set(96)
    try:
        construction = CadConstruction.model_validate(data)
        async with SolidCraftSession(tmp_path) as session:
            await session.batch([construction.workflow.parameter_command()])
            await session.construct(data['commands'], construction.workflow,
                cut_intents=construction.cut_intents, enforce_cut_safety=True)
            assert all(len(item['arguments']['commands']) <= 64 for item in session.observations
                       if item['tool'] == 'batch')
            captured = await session.capture('a' * 32, 'a' * 32, 1)
            assert captured.geometry.closed_solid and captured.geometry.body_count == 1
            from bigbrain.cad_cut_safety import revalidate_parameter_edit
            safety = tmp_path / 'safety.json'
            safety.write_text(json.dumps({'source_sha256': captured.document.native.sha256,
                'construction_commands': data['commands'],
                'cut_intents': [c.model_dump(mode='json') for c in construction.cut_intents]}))
            replay = await revalidate_parameter_edit(session, captured.document.native.sha256, safety)
            assert replay['reports']
    finally:
        command_capacity.reset(token)


def grant(store, state, **changes):
    value = dict(contract_sha256=store.contract,
        definition_sha256=digest(definition().model_dump(mode='json')), document_id=store.root.name,
        engine_sha256='e' * 64, baseline_decisions=state['decisions'],
        baseline_failures=len(state['failures']), additional_calls=4,
        decision_ceiling=68, command_capacity=96, inspection_reserve=1,
        authorization_source='Explicit resource extension in this qualification case')
    value.update(changes)
    store._write(store.directory / 'continuation.json', value)
    return value


@pytest.mark.asyncio
async def test_decision_extension_crosses_64_and_preserves_inspection_reserve(tmp_path):
    store = CadExecutionStore(tmp_path, 'a' * 64)
    driver = CadConstructionDriver(Decisions([]), definition(), [], [], store)
    driver.state['decisions'] = 64
    driver.save()
    grant(store, driver.state)
    for expected in [65, 66, 67]:
        provider = Decisions([{'operation': 'blocked', 'reason': 'Controlled offline checkpoint'}])
        resumed = CadConstructionDriver(provider, definition(), [], [], store)
        with pytest.raises(CadError, match='Controlled offline checkpoint'):
            await resumed.run(Session(tmp_path))
        assert resumed.state['decisions'] == expected
        assert len(provider.calls) == 1
    closing = Decisions([{'operation':'blocked','reason':'Final inspection remains unavailable'}])
    resumed = CadConstructionDriver(closing, definition(), [], [], store)
    with pytest.raises(CadError, match='Final inspection remains unavailable'):
        await resumed.run(Session(tmp_path))
    assert resumed.state['decisions'] == 68
    assert closing.calls[0]['allowed_operations'] == ['complete','blocked']
    resumed = CadConstructionDriver(Decisions([]), definition(), [], [], store)
    with pytest.raises(CadError, match='decision allowance exhausted'):
        await resumed.run(Session(tmp_path))
    assert resumed.state['failures'] == []
    assert authorized_capacity(tmp_path, store.contract, definition()) == 96
    with pytest.raises(CadError, match='scope changed'):
        authorized_capacity(tmp_path, 'b' * 64, definition())


@pytest.mark.asyncio
async def test_conclusion_reserve_rejects_geometry_mutation(tmp_path):
    from tests.test_cad_execution import group
    from bigbrain.cad_resources import inference_phase
    store = CadExecutionStore(tmp_path,'a'*64)
    driver = CadConstructionDriver(Decisions([]),definition(),[],[],store)
    driver.state['decisions'] = 64
    driver.save()
    grant(store,driver.state,additional_calls=2,decision_ceiling=66,
          inspection_reserve=1,stop_on_new_error=True)
    driver.state['decisions'] = 65
    driver.save()
    class ClosingProvider(Decisions):
        async def chat_complete(self,**request):
            assert inference_phase.get() == 'inspection'
            assert request['max_tokens'] == 1024
            return await super().chat_complete(**request)
    provider = ClosingProvider([{'operation':'execute','group':group().model_dump(mode='json')}])
    session = Session(tmp_path)
    with pytest.raises(CadError,match='proposal rejected'):
        await CadConstructionDriver(provider,definition(),[],[],store).run(session)
    assert session.mutations == 0 and store.active() == []
    assert inference_phase.get() == 'construction'


@pytest.mark.asyncio
async def test_extension_stops_on_first_new_protocol_error(tmp_path):
    store = CadExecutionStore(tmp_path, 'a' * 64)
    driver = CadConstructionDriver(Decisions([]), definition(), [], [], store)
    driver.save()
    grant(store, driver.state, additional_calls=3, decision_ceiling=64,
          inspection_reserve=1, stop_on_new_error=True)
    provider = Decisions([{'operation': 'observe', 'tool': 'parameter_graph'}])
    with pytest.raises(CadError, match='proposal rejected'):
        await CadConstructionDriver(provider, definition(), [], [], store).run(Session(tmp_path))
    assert len(provider.calls) == 1
