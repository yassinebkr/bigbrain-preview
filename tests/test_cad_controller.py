"""Progressive decisions exercised against native geometry and durable state."""

import json

import pytest

from bigbrain.cad_controller import CadConstructionDriver, boundary_diagnostics
from bigbrain.cad_execution import CadExecutionStore, ExecutionGroup
from bigbrain.cad_stages import CadDefinition
from bigbrain.solidcraft import CadError, SolidCraftSession
from tests.test_cad_drawings import drawing
from tests.test_cad_workflow import construction_commands, construction_cut_intents, workflow


def actions(construction=None):
    commands = construction['commands'] if construction else construction_commands()
    intent = construction['workflow'] if construction else workflow().model_dump(mode='json')
    if construction is None:
        intent['parameters'][0]['source_dimension'] = 'width'
    result = []
    for index, (start, stop) in enumerate([(0, 3), (3, 4), (4, 7), (7, 8)]):
        result.append({'operation': 'execute', 'group': {
            'id': f'group-{index}', 'purpose': ['Esquisse du socle', 'Extrusion du socle',
                'Esquisse du perçage', 'Perçage traversant'][index],
            'commands': commands[start:stop], 'workflow': intent,
            'cut_intents': [{**cut, 'command_index': 0} for cut in
                           (construction['cut_intents'] if construction else construction_cut_intents())]
                          if start == 7 else []}})
    result.append({'operation': 'complete'})
    return result


def packet(kwargs):
    return json.loads(kwargs['messages'][-1]['content'][0]['text'])


def fixture_decision(kwargs, construction):
    """Provide deterministic staged choices to native worker integration cases."""
    state = packet(kwargs)
    action = actions(construction)[len(state['accepted_groups'])]
    action['base_checkpoint'] = state['base_checkpoint']
    if action['operation'] == 'execute':
        action['group']['base_checkpoint'] = state['base_checkpoint']
    return action


class Decisions:
    def __init__(self, values):
        self.values = values
        self.calls = []

    async def chat_complete(self, **kwargs):
        state = packet(kwargs)
        self.calls.append(state)
        action = json.loads(json.dumps(self.values.pop(0)))
        action['base_checkpoint'] = state['base_checkpoint']
        if action['operation'] == 'execute':
            action['group']['base_checkpoint'] = state['base_checkpoint']
        return json.dumps(action)


def definition():
    return CadDefinition(title='Plaque', objective='Constrained plate with through hole', drawing=drawing())


@pytest.mark.parametrize('field', ['contract_sha256', 'definition_sha256', 'document_id'])
def test_execution_authorization_must_match_candidate_and_definition(tmp_path, field):
    from bigbrain.cad_execution import digest
    spec = definition()
    authorization = {'status': 'confirmed', 'contract_sha256': 'a' * 64,
        'definition_sha256': digest(spec.model_dump(mode='json')), 'design_id': 'design',
        'revision': 1, 'approval_plan_id': 'plan', 'document_id': tmp_path.name}
    store = CadExecutionStore(tmp_path, 'a' * 64)
    driver = CadConstructionDriver(Decisions([]), spec, [], [], store, authorization=authorization)
    assert driver.packet()['execution_authorization']['status'] == 'confirmed'
    authorization[field] = 'b' * 64
    with pytest.raises(CadError, match='authorization differs'):
        CadConstructionDriver(Decisions([]), spec, [], [], store, authorization=authorization)


@pytest.mark.asyncio
async def test_paid_execution_replay_preserves_counters_and_rejects_stale_base(tmp_path, cad_native_engine):
    store = CadExecutionStore(tmp_path, 'a' * 64)
    provider = Decisions([])
    driver = CadConstructionDriver(provider, definition(), [], [], store)
    async with SolidCraftSession(tmp_path) as session:
        await store.recover(session)
        driver.state['decisions'] = 1
        driver.save()
        value = actions()[0]
        value['base_checkpoint'] = None
        value['group']['base_checkpoint'] = None
        record = {'status': 'returned', 'packet': driver.packet(), 'response': json.dumps(value)}
        path = store.directory / 'decision-1.json'
        store._write(path, record)
        before = path.read_bytes()
        await driver.run(session, replay_decision=1)
        assert provider.calls == []
        assert driver.state['decisions'] == 1
        assert len(store.active()) == 1
        assert path.read_bytes() == before
        assert driver.state['replayed_decisions'][0]['decision'] == 1
        with pytest.raises(CadError, match='scope or checkpoint changed'):
            await driver.run(session, replay_decision=1)
        assert len(store.active()) == 1


@pytest.mark.asyncio
async def test_native_model_decisions_observe_each_accepted_prefix(tmp_path, cad_native_engine):
    store = CadExecutionStore(tmp_path, 'a' * 64)
    provider = Decisions(actions())
    events = []

    async def progress(stage, detail):
        events.append((stage, detail))

    driver = CadConstructionDriver(provider, definition(), [], [], store, progress=progress)
    async with SolidCraftSession(tmp_path) as session:
        result = await driver.run(session)
        capture = await session.capture('a' * 32, 'a' * 32, 1)
        assert len(session.cut_safety_reports) == 1
    assert len(result.commands) == 8
    assert len(store.active()) == 4
    from bigbrain.verification.evidence import default_repository
    for path in store.directory.glob('decision-*.json'):
        record = json.loads(path.read_text())
        assert record['duration_ms'] >= 0
        trace = default_repository().root / 'inference' / (record['call_id'] + '.jsonl')
        trace_events = [json.loads(line) for line in trace.read_text().splitlines()]
        assert trace_events[0]['document_id'] == store.root.name
        assert trace_events[0]['decision_id'] == path.stem
        assert trace_events[-1]['event'] == 'call.finished'
        assert trace_events[-1]['outcome'] == 'completed'
    assert result.cut_intents[0].command_index == 7
    assert capture.geometry.bounds_max_mm == pytest.approx((60, 40, 6), abs=0.001)
    assert provider.calls[0]['current_design'] is None
    assert provider.calls[1]['current_design']['sketches'][0]['fully_constrained']
    assert provider.calls[1]['last_action']['status'] == 'accepted'
    assert provider.calls[1]['last_action']['checkpoint'] == store.active()[0].id
    assert provider.calls[1]['accepted_workflow']['parameters'] == result.workflow.model_dump(mode='json')['parameters']
    assert provider.calls[2]['current_design']['bodies'][0]['name'] == 'Mount_plate'
    assert all(call['unverified_requirements'] == ['width'] for call in provider.calls)
    assert len([event for event in events if event[0] == 'cad_group_checkpoint']) == 4
    # Completing and reopening the same candidate consumes no additional model call.
    resumed = CadConstructionDriver(provider, definition(), [], [], store)
    async with SolidCraftSession(tmp_path) as session:
        assert await resumed.run(session) == result
        assert len(session.cut_safety_reports) == 1


@pytest.mark.asyncio
async def test_native_proposal_boundary_rejected_before_mutation(tmp_path, cad_native_engine):
    values = actions()
    unsafe = json.loads(json.dumps(values[0]))
    unsafe['group']['commands'].append(construction_commands()[3])
    provider = Decisions([unsafe, *values])
    store = CadExecutionStore(tmp_path, 'a' * 64)
    async with SolidCraftSession(tmp_path) as session:
        driver = CadConstructionDriver(provider, definition(), [], [], store)
        await driver.run(session)
    assert len(store.active()) == 4
    assert 'End the group' in provider.calls[1]['feedback']
    assert provider.calls[1]['current_design'] is None


@pytest.mark.asyncio
async def test_cancelled_decision_resumes_native_prefix(tmp_path, cad_native_engine):
    provider = Decisions(actions()[:1])
    original = provider.chat_complete

    async def interrupted(**kwargs):
        if provider.calls:
            raise TimeoutError('Synthetic inference interruption')
        return await original(**kwargs)

    provider.chat_complete = interrupted
    store = CadExecutionStore(tmp_path, 'a' * 64)
    async with SolidCraftSession(tmp_path) as session:
        driver = CadConstructionDriver(provider, definition(), [], [], store)
        with pytest.raises(TimeoutError, match='inference interruption'):
            await driver.run(session)
    assert len(store.active()) == 1
    resumed_provider = Decisions(actions()[1:])
    async with SolidCraftSession(tmp_path) as session:
        resumed = CadConstructionDriver(resumed_provider, definition(), [], [], store)
        await resumed.run(session)
    assert len(resumed_provider.calls[0]['current_design']['sketches']) == 1
    assert len(store.active()) == 4


@pytest.mark.asyncio
async def test_decision_limit_preserves_incomplete_state(tmp_path, cad_native_engine):
    store = CadExecutionStore(tmp_path, 'a' * 64)
    provider = Decisions(actions()[:1])
    async with SolidCraftSession(tmp_path) as session:
        driver = CadConstructionDriver(provider, definition(), [], [], store, max_decisions=1)
        with pytest.raises(CadError, match='decision allowance exhausted'):
            await driver.run(session)
    assert len(store.active()) == 1
    assert driver.state.get('completed') is not True


def test_finishing_requires_its_own_observed_group():
    data = actions()[1]['group']
    data['commands'].append({'command': 'solid.fillet', 'params': {
        'body': 'Mount_plate', 'edges': [[0, 0, 3]], 'radius': 1}})
    assert boundary_diagnostics(ExecutionGroup.model_validate(data))


@pytest.mark.asyncio
async def test_native_rejection_repairs_from_accepted_sketch(tmp_path, cad_native_engine):
    values = actions()
    rejected = json.loads(json.dumps(values[1]))
    rejected['group']['commands'][0]['params']['distance'] = 'unknown_dimension'
    provider = Decisions([values[0], rejected, *values[1:]])
    store = CadExecutionStore(tmp_path, 'a' * 64)
    async with SolidCraftSession(tmp_path) as session:
        driver = CadConstructionDriver(provider, definition(), [], [], store)
        await driver.run(session)
    assert len(store.active()) == 4
    assert len(driver.state['failures']) == 1
    recovery_packet = provider.calls[2]
    assert len(recovery_packet['accepted_groups']) == 1
    assert len(recovery_packet['current_design']['sketches']) == 1
    assert recovery_packet['current_design']['bodies'] == []
    assert recovery_packet['failures'][0]['diagnostic']['command'] == 'solid.extrude'


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [None, 'Mount_plate'])
async def test_precise_observation_precedes_further_modeling(tmp_path, cad_native_engine, body):
    values = actions()
    provider = Decisions([*values[:2], {'operation': 'observe', 'tool': 'precise_geometry', 'body': body,
        'question': 'What are the exact bounds and volume of the current solid?'}, *values[2:]])
    store = CadExecutionStore(tmp_path, 'a' * 64)
    async with SolidCraftSession(tmp_path) as session:
        await CadConstructionDriver(provider, definition(), [], [], store).run(session)
    measured = provider.calls[3]['observations']['precise_geometry:']['result']
    assert measured['geometry']['volume_mm3'] == pytest.approx(14400, abs=0.001)
    assert 'Mount_plate' in measured['bodies']
    assert measured['measurement_scope'] == 'whole_document'
    assert measured['requested_body'] == body
    assert (tmp_path / measured['geometry']['evidence_ref']).is_file()
    assert len(store.active()) == 4


@pytest.mark.asyncio
async def test_explicit_root_revision_rebuilds_suffix_and_preserves_evidence(tmp_path, cad_native_engine):
    values = actions()
    provider = Decisions([*values[:2], {'operation': 'revise', 'checkpoint': None,
        'reason': 'Rebuild the accepted sequence from its initial state.'}, *values])
    store = CadExecutionStore(tmp_path, 'a' * 64)
    async with SolidCraftSession(tmp_path) as session:
        driver = CadConstructionDriver(provider, definition(), [], [], store)
        await driver.run(session)
    assert len(store.active()) == 4
    assert len(list(store.directory.glob('invalidation-*.json'))) == 1
    assert len(list(store.directory.glob('*/part.sc'))) == 6
    assert provider.calls[3]['accepted_groups'] == []


@pytest.mark.asyncio
async def test_reference_cache_survives_owned_controller_restart(tmp_path):
    from bigbrain.cad_tool_reference import CadCommandCatalog
    from tests.test_cad_execution import Session
    calls = []

    async def load(names, skills):
        calls.append(names)
        return {'command_reference': [{'id': 'solid.box', 'params': 'native box signature'}]}

    catalog = CadCommandCatalog([], [{'id': 'solid.box', 'params': 'box'}], load)
    provider = Decisions([{'operation': 'reference', 'commands': ['solid.box']},
                          {'operation': 'blocked', 'reason': 'Synthetic qualification stop'}])
    store = CadExecutionStore(tmp_path, 'a' * 64)
    driver = CadConstructionDriver(provider, definition(), catalog, [], store)
    with pytest.raises(CadError, match='Synthetic qualification stop'):
        await driver.run(Session(tmp_path))
    restored = CadCommandCatalog([], [{'id': 'solid.box', 'params': 'box'}], load)
    resumed = CadConstructionDriver(provider, definition(), restored, [], store)
    assert resumed.packet()['retrieved_reference']['command_reference'][0]['params'] == 'native box signature'
    assert calls == [('solid.box',)]


@pytest.mark.asyncio
async def test_repeated_reference_read_stops_and_keeps_completed_result(tmp_path):
    from bigbrain.cad_tool_reference import CadCommandCatalog
    from tests.test_cad_execution import Session
    calls = []

    async def load(names, skills):
        calls.append(names)
        return {'command_reference': [{'id': 'solid.box', 'params': 'observed box signature'}]}

    reference = CadCommandCatalog([], [{'id': 'solid.box', 'params': 'box'}], load)
    decision = {'operation': 'reference', 'commands': ['solid.box']}
    provider = Decisions([decision, decision, decision])
    store = CadExecutionStore(tmp_path, 'a' * 64)
    driver = CadConstructionDriver(provider, definition(), reference, [], store)
    with pytest.raises(CadError, match='Repeated invalid CAD decision.*already in retrieved_reference'):
        await driver.run(Session(tmp_path))
    assert calls == [('solid.box',)]
    assert len(provider.calls) == 3
    assert provider.calls[1]['last_action']['status'] == 'completed'
    assert provider.calls[1]['retrieved_reference']['command_reference'][0]['params'] == 'observed box signature'
    assert 'already in retrieved_reference' in provider.calls[2]['protocol_diagnostics'][0]['diagnostic']
    restored = CadConstructionDriver(provider, definition(), reference, [], store)
    assert restored.packet()['protocol_diagnostics'] == driver.packet()['protocol_diagnostics']
    assert store.active() == []


@pytest.mark.asyncio
async def test_omitted_workflow_parameters_recover_from_authoritative_packet(tmp_path, cad_native_engine):
    values = actions()
    omitted = json.loads(json.dumps(values[1]))
    omitted['group']['workflow'].pop('parameters')

    class RestoringDecisions(Decisions):
        async def chat_complete(self, **kwargs):
            state = packet(kwargs)
            if len(self.calls) == 2:
                assert 'Missing accepted workflow parameters' in state['feedback']
                self.values[0]['group']['workflow']['parameters'] = state['accepted_workflow']['parameters']
            return await super().chat_complete(**kwargs)

    provider = RestoringDecisions([values[0], omitted, *values[1:]])
    store = CadExecutionStore(tmp_path, 'a' * 64)
    async with SolidCraftSession(tmp_path) as session:
        driver = CadConstructionDriver(provider, definition(), [], [], store)
        await driver.run(session)
    assert len(store.active()) == 4 and len(provider.calls) == 6
    assert driver.state['failures'] == []
    assert provider.calls[1]['base_checkpoint'] == provider.calls[2]['base_checkpoint']


@pytest.mark.asyncio
async def test_completion_without_geometry_stops_without_mutation(tmp_path):
    from tests.test_cad_execution import Session
    provider = Decisions([{'operation': 'complete'}, {'operation': 'complete'}])
    store = CadExecutionStore(tmp_path, 'a' * 64)
    driver = CadConstructionDriver(provider, definition(), [], [], store)
    with pytest.raises(CadError, match='constructed native geometry'):
        await driver.run(Session(tmp_path))
    assert store.active() == []
    assert len(provider.calls) == 1
@pytest.mark.asyncio
async def test_native_axis_preflight_preserves_repair_allowance(tmp_path):
    from tests.test_cad_execution import Session, group
    invalid = group().model_dump(mode='json')
    invalid['commands'] = [{'command': 'solid.revolve', 'params': {
        'axis': {'origin': ['radius', 0, 'height'], 'dir': [0, 1, 0]}}}]
    provider = Decisions([{'operation': 'execute', 'group': invalid},
        {'operation': 'blocked', 'reason': 'Stop after native parameter diagnosis'}])
    session = Session(tmp_path)
    driver = CadConstructionDriver(provider, definition(), [], [], CadExecutionStore(tmp_path, 'a' * 64))
    with pytest.raises(CadError, match='Stop after native parameter diagnosis'):
        await driver.run(session)
    assert session.mutations == 0 and driver.state['failures'] == []
    assert 'silently replaces' in provider.calls[1]['feedback']


@pytest.mark.asyncio
async def test_exhausted_repairs_cannot_resume_additional_model_calls(tmp_path):
    from tests.test_cad_execution import Session
    provider = Decisions([])
    store = CadExecutionStore(tmp_path, 'a' * 64)
    driver = CadConstructionDriver(provider, definition(), [], [], store)
    driver.state['failures'] = [{'qualification_case': index} for index in range(3)]
    driver.save()
    restored = CadConstructionDriver(provider, definition(), [], [], store)
    session = Session(tmp_path)
    with pytest.raises(CadError, match='repair allowance exhausted'):
        await restored.run(session)
    assert provider.calls == [] and session.mutations == 0
    assert len(restored.state['failures']) == 3


@pytest.mark.asyncio
async def test_continuation_preserves_counters_and_reserves_calls_across_restart(tmp_path):
    from bigbrain.cad_execution import digest
    from tests.test_cad_execution import Session
    store = CadExecutionStore(tmp_path, 'a' * 64)
    driver = CadConstructionDriver(Decisions([]), definition(), [], [], store)
    driver.state.update(decisions=7, failures=[{'case': i} for i in range(3)])
    driver.save()
    grant = dict(contract_sha256=store.contract,
        definition_sha256=digest(definition().model_dump(mode='json')),
        document_id=tmp_path.name, engine_sha256='e' * 64,
        baseline_decisions=7, baseline_failures=3, additional_calls=4,
        authorization_source='Explicit user authorization in the current conversation')
    store._write(store.directory / 'continuation.json', grant)
    for index in range(4):
        provider = Decisions([{'operation': 'blocked', 'reason': 'Synthetic retained candidate'}])
        restored = CadConstructionDriver(provider, definition(), [], [], store)
        with pytest.raises(CadError, match='Synthetic retained candidate'):
            await restored.run(Session(tmp_path))
        assert len(provider.calls) == 1
        assert restored.state['decisions'] == 8 + index
        assert len(restored.state['failures']) == 3
    provider = Decisions([])
    restored = CadConstructionDriver(provider, definition(), [], [], store)
    with pytest.raises(CadError, match='continuation call allowance exhausted'):
        await restored.run(Session(tmp_path))
    assert provider.calls == []
    store._write(store.directory / 'continuation.json', {**grant, 'additional_calls': 5})
    with pytest.raises(CadError, match='authorization changed'):
        await CadConstructionDriver(provider, definition(), [], [], store).run(Session(tmp_path))
    renewal = {**grant, 'baseline_decisions': 11, 'additional_calls': 2,
               'previous_authorization_sha256': restored.state['continuation_sha256']}
    store._write(store.directory / 'continuation.json', renewal)
    provider = Decisions([{'operation': 'blocked', 'reason': 'Explicit continuation renewal'}])
    renewed = CadConstructionDriver(provider, definition(), [], [], store)
    with pytest.raises(CadError, match='Explicit continuation renewal'):
        await renewed.run(Session(tmp_path))
    assert renewed.state['decisions'] == 12
    assert len(renewed.state['continuation_authorizations']) == 2
    store._write(store.directory / 'continuation.json', grant)
    with pytest.raises(CadError, match='authorization changed'):
        await CadConstructionDriver(Decisions([]), definition(), [], [], store).run(Session(tmp_path))


@pytest.mark.asyncio
async def test_continuation_rejects_another_candidate_before_call(tmp_path):
    from bigbrain.cad_execution import digest
    from tests.test_cad_execution import Session
    store = CadExecutionStore(tmp_path, 'a' * 64)
    store._write(store.directory / 'continuation.json', dict(
        contract_sha256='b' * 64, definition_sha256=digest(definition().model_dump(mode='json')),
        document_id=tmp_path.name, engine_sha256='e' * 64,
        baseline_decisions=0, baseline_failures=0, additional_calls=4,
        authorization_source='Explicit user authorization in the current conversation'))
    provider = Decisions([])
    with pytest.raises(CadError, match='scope or baseline changed'):
        await CadConstructionDriver(provider, definition(), [], [], store).run(Session(tmp_path))
    assert provider.calls == []


@pytest.mark.asyncio
async def test_checkpoint_evidence_and_targeted_definition_are_available(tmp_path, cad_native_engine):
    values = actions()
    values[0]['group']['unresolved_obligations'] = ['Inspect the native construction frame before the next feature']
    provider = Decisions([values[0],
        {'operation': 'observe', 'tool': 'feature_definition', 'feature': 'Socle',
         'question': 'Which native feature definition and dimension inputs drive this sketch?'},
        {'operation': 'blocked', 'reason': 'Stop after targeted native inspection'}])
    # Resolve the real fixture name from its declared inventory.
    name = values[0]['group']['workflow']['sketches'][0]['name']
    provider.values[1]['feature'] = name
    store = CadExecutionStore(tmp_path, 'a' * 64)
    async with SolidCraftSession(tmp_path) as session:
        with pytest.raises(CadError, match='Stop after targeted native inspection'):
            await CadConstructionDriver(provider, definition(), [], [], store).run(session)
    before, after = provider.calls[1:]
    assert before['observations']['parameter_graph:']['source'] == 'accepted_checkpoint'
    assert before['observations']['inspect_design:']['result']['sketches'][0]['dof'] == 0
    assert before['current_design']['timeline'][0]['type'] == 'Sketch'
    assert before['construction_questions']['origin'] == 'model_execution_group'
    assert before['construction_questions']['items'] == values[0]['group']['unresolved_obligations']
    assert before['definition'] == definition().model_dump(mode='json')
    observed = after['observations']['feature_definition:' + name]
    assert observed['result']['name'] == name and 'definition' in observed['result']
    assert observed['checkpoint'] == after['base_checkpoint']
    trace = store._read(store.directory / 'decision-2.json')
    assert trace['status'] == 'returned' and trace['packet'] == before
    assert 'observation_coverage' in trace['system']
    assert len(store.active()) == 1


@pytest.mark.asyncio
async def test_cached_observation_rejected_without_native_reread(tmp_path, cad_native_engine):
    provider = Decisions([actions()[0],
        {'operation': 'observe', 'tool': 'parameter_graph',
         'question': 'Do the current parameters contain cycles or expression errors?'},
        {'operation': 'blocked', 'reason': 'Stop after cached evidence diagnostic'}])
    store = CadExecutionStore(tmp_path, 'a' * 64)
    async with SolidCraftSession(tmp_path) as session:
        with pytest.raises(CadError, match='Stop after cached evidence diagnostic'):
            await CadConstructionDriver(provider, definition(), [], [], store).run(session)
    assert 'already available' in provider.calls[-1]['feedback']
    assert len(store.active()) == 1


@pytest.mark.asyncio
async def test_provider_failure_retains_decision_inputs(tmp_path):
    from tests.test_cad_execution import Session
    class BrokenProvider:
        async def chat_complete(self, **kwargs):
            raise RuntimeError('Synthetic provider outage')
    store = CadExecutionStore(tmp_path, 'a' * 64)
    with pytest.raises(RuntimeError, match='Synthetic provider outage'):
        await CadConstructionDriver(BrokenProvider(), definition(), [], [], store).run(Session(tmp_path))
    trace = store._read(store.directory / 'decision-1.json')
    assert trace['status'] == 'interrupted' and trace['error_type'] == 'RuntimeError'
    assert trace['packet']['base_checkpoint'] is None


@pytest.mark.parametrize('legacy', [False, True])
def test_failed_command_inputs_are_bound_to_the_retained_proposal(tmp_path, legacy):
    from bigbrain.cad_controller import group_fingerprint
    from bigbrain.cad_execution import digest
    from tests.test_cad_execution import group
    store = CadExecutionStore(tmp_path, 'a' * 64)
    proposal = group()
    folder = store.directory / ('1' * 32)
    folder.mkdir()
    value = proposal.model_dump(mode='json')
    store._write(folder / 'proposal.json', value)
    store._write(folder / 'failure.json', {'type': 'CadCommandError', 'diagnostic': 'Synthetic failure'})
    failure = {'fingerprint': group_fingerprint(proposal), 'group': proposal.id,
               'diagnostic': {'command': 'solid.box', 'error': 'Synthetic failure'}}
    if not legacy:
        failure.update(proposal_ref=f'execution-checkpoints/{folder.name}/proposal.json',
                       proposal_sha256=digest(value))
    driver = CadConstructionDriver(Decisions([]), definition(), [], [], store)
    driver.state['failures'] = [failure]
    before = json.dumps(driver.state, sort_keys=True)
    recovered = driver.packet()['failures'][0]
    assert recovered['attempt']['commands'] == value['commands']
    assert recovered['attempt']['base_checkpoint'] is None
    assert recovered['attempt']['provenance'] == 'fingerprint_matched_native_attempt'
    assert recovered['scope'] == 'historical_attempt'
    assert json.dumps(driver.state, sort_keys=True) == before
    store._write(folder / 'proposal.json', {**value, 'purpose': 'Changed historical proposal'})
    if not legacy:
        with pytest.raises(CadError, match='failed proposal changed'):
            driver.packet()


def test_missing_historical_proposal_remains_explicitly_unknown(tmp_path):
    driver = CadConstructionDriver(Decisions([]), definition(), [], [], CadExecutionStore(tmp_path, 'a' * 64))
    driver.state['failures'] = [{'fingerprint': 'f' * 64, 'diagnostic': {'error': 'Legacy error'}}]
    assert driver.packet()['failures'][0]['attempt'] == {'provenance': 'unavailable'}


def test_repair_packet_contains_hash_bound_native_warning(tmp_path):
    import hashlib
    from bigbrain.cad_controller import group_fingerprint
    from bigbrain.cad_execution import digest
    from tests.test_cad_execution import group
    store = CadExecutionStore(tmp_path, 'a' * 64)
    proposal = group()
    folder = store.directory / ('1' * 32)
    folder.mkdir()
    store._write(folder / 'proposal.json', proposal.model_dump(mode='json'))
    observed = folder / 'rejected-observations.json'
    store._write(observed, {'design': {'timeline': [
        {'name': 'Bore', 'type': 'RevolveFeature', 'warning': 'Boolean retry: tool displacement',
         'boolean_diagnostics': {'events': [{'strategy': 'tool_nudge'}]}}]}})
    driver = CadConstructionDriver(Decisions([]), definition(), [], [], store)
    driver.state['failures'] = [{'fingerprint': group_fingerprint(proposal),
        'proposal_ref': f'execution-checkpoints/{folder.name}/proposal.json',
        'proposal_sha256': digest(proposal.model_dump(mode='json')),
        'diagnostic': {'observation_ref': f'execution-checkpoints/{folder.name}/rejected-observations.json',
                       'observation_sha256': hashlib.sha256(observed.read_bytes()).hexdigest()}}]
    detail = driver.failure_context()[0]['native_feature_diagnostics'][0]
    assert detail['name'] == 'Bore'
    assert detail['boolean_diagnostics']['events'][0]['strategy'] == 'tool_nudge'
    store._write(observed, {'design': {}})
    with pytest.raises(CadError, match='rejected observation changed'):
        driver.failure_context()


@pytest.mark.asyncio
async def test_offline_diagnosis_survives_observation_and_restart(tmp_path):
    import hashlib
    from tests.test_cad_execution import Session
    store = CadExecutionStore(tmp_path, 'a' * 64)
    diagnosis = store.directory / 'offline-diagnosis-example.json'
    store._write(diagnosis, {'contract_sha256': store.contract,
                            'finding': 'Observed native plane basis and cut warning'})
    provider = Decisions([{'operation': 'observe', 'tool': 'parameter_graph',
                           'question': 'Inspect the current parameter dependencies'},
                          {'operation': 'blocked', 'reason': 'Offline test boundary'}])
    driver = CadConstructionDriver(provider, definition(), [], [], store)
    driver.state['offline_diagnostics'] = [{'name': diagnosis.name,
        'sha256': hashlib.sha256(diagnosis.read_bytes()).hexdigest()}]
    driver.state['feedback'] = 'Temporary diagnostic'
    driver.save()
    with pytest.raises(CadError, match='Offline test boundary'):
        await driver.run(Session(tmp_path))
    restored = CadConstructionDriver(Decisions([]), definition(), [], [], store)
    assert restored.packet()['feedback'] is None
    assert restored.packet()['offline_diagnostics'][0]['finding'].startswith('Observed native')
    store._write(diagnosis, {'contract_sha256': 'b' * 64})
    with pytest.raises(CadError, match='offline diagnosis scope changed'):
        restored.packet()


@pytest.mark.asyncio
async def test_blockage_persists_its_actual_reason(tmp_path):
    from tests.test_cad_execution import Session
    store = CadExecutionStore(tmp_path, 'a' * 64)
    driver = CadConstructionDriver(Decisions([{'operation': 'blocked',
        'reason': 'Native capability is unavailable for this operation'}]), definition(), [], [], store)
    with pytest.raises(CadError, match='Native capability is unavailable'):
        await driver.run(Session(tmp_path))
    saved = store._read(store.directory / 'controller.json')
    assert saved['last_action']['operation'] == 'blocked'
    assert saved['last_action']['reason'] == 'Native capability is unavailable for this operation'


@pytest.mark.asyncio
@pytest.mark.parametrize('new_evidence', [False, True])
async def test_failed_retry_requires_verified_additional_evidence(tmp_path, new_evidence):
    import hashlib
    from bigbrain.cad_controller import group_fingerprint
    from bigbrain.cad_execution import digest
    from tests.test_cad_execution import Session, group, accept
    store = CadExecutionStore(tmp_path, 'a' * 64)
    proposal = group()
    folder = store.directory / ('1' * 32)
    folder.mkdir()
    store._write(folder/'proposal.json',proposal.model_dump(mode='json'))
    provider = Decisions([{'operation':'execute','group':proposal.model_dump(mode='json')},
                          {'operation':'blocked','reason':'Controlled retry boundary'}])
    driver = CadConstructionDriver(provider,definition(),[],[],store)
    driver.check_step = accept
    driver.state['failures'] = [{'fingerprint':group_fingerprint(proposal),
        'observations':digest({}),'proposal_ref':f'execution-checkpoints/{folder.name}/proposal.json',
        'proposal_sha256':digest(proposal.model_dump(mode='json'))}]
    if new_evidence:
        path = store.directory/'offline-diagnosis-retry.json'
        store._write(path,{'contract_sha256':store.contract,'finding':'Exact offline replay after runtime correction'})
        driver.state['offline_diagnostics'] = [{'name':path.name,
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]
    session = Session(tmp_path)
    with pytest.raises(CadError,match='Controlled retry boundary'):
        await driver.run(session)
    assert session.mutations == int(new_evidence)
    assert len(store.active()) == int(new_evidence)
    if not new_evidence:
        assert 'identical failed group' in provider.calls[1]['feedback']
