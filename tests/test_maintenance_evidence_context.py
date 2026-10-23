"""Runtime provenance and event transport regressions; no paid inference."""
import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from bigbrain.maintenance_context import MaintenanceContext
from bigbrain.llm.codex_sessions import digest as message_digest, incremental_messages
from bigbrain.project_inspection import digest
from bigbrain.verification.evidence import default_repository
from bigbrain.verification.semantics import review_semantics, _progressive_review


SOURCES = {'main.py': 'def twice(n):\n    return n * 2\n',
           'test_main.py': 'from main import twice\ndef test_twice():\n    assert twice(3) == 6\n'}


@pytest.mark.asyncio
@pytest.mark.parametrize('persistent', [False, True])
async def test_review_transport_does_not_repeat_evidence_in_persistent_history(persistent):
    """Same generic investigation; only stateful delivery changes, not gates."""
    from types import SimpleNamespace
    replies = [json.dumps({'action': {'type': 'read', 'path': 'module.py', 'start': i,
                                      'count': 1}, 'notebook': 'inspected'}) for i in (1, 2, 3)]
    replies[2] = json.dumps({'action': {'type': 'read', 'path': 'test_module.py',
                                      'start': 1, 'count': 1}, 'notebook': 'inspected'})
    replies.append(json.dumps({'decision': 'needs_arbitration', 'contradictions': ['unknown'],
                               'coverage': []}))
    answers = iter(replies)
    async def complete(**kwargs):
        from tests.test_maintenance import recorded_stub_usage
        recorded_stub_usage()
        return next(answers)
    provider = SimpleNamespace(review_event_context=persistent,
                               chat_complete=AsyncMock(side_effect=complete))
    context = {'sources': {'module.py': ''.join(f'# unique_page_{i}\n' for i in range(1, 4000)),
                           'test_module.py': 'assert "unique_assertion"\n'},
               'baseline_sources': {}, 'request': 'Inspect generic module',
               'criteria': [{'id': '0', 'text': 'Approved behavior'}],
               'passing_tests': ['test_module.py::test_behavior'], 'test_report': {'status': 'passed'},
               'runtime_evidence': {}, 'baseline': None, 'initial_diagnostic': None}
    raw = await _progressive_review(provider, {'content': 'Independent review rules'}, context)
    assert json.loads(raw)['decision'] == 'needs_arbitration'
    calls = provider.chat_complete.call_args_list
    assert len(calls) == 4
    if not persistent:
        assert all(len(c.kwargs['messages']) == 2 for c in calls)
        assert 'criteria' in json.loads(calls[-1].kwargs['messages'][1]['content'])
        return
    state, sent = {}, []
    for index, call in enumerate(calls):
        messages = call.kwargs['messages']
        delta, hashes = incremental_messages(messages, state)
        state = {**hashes, 'message_hashes': [*hashes['message_hashes'],
                                            message_digest({'role': 'assistant', 'content': replies[index]})]}
        sent.extend(delta)
        if index:
            assert len(delta) == 1 and delta[0]['role'] == 'user'
            event = json.loads(delta[0]['content'])
            assert 'criteria' not in event and 'baseline' not in event
            assert len(event['observations']) == 1
        checkpoint = call.kwargs['context_checkpoint']
        assert checkpoint['criteria'] == context['criteria']
    wire = json.dumps(sent)
    assert wire.count('unique_page_1') == 1
    assert wire.count('unique_page_2') == 1
    assert wire.count('unique_assertion') == 1
    assert len(calls[0].kwargs['messages']) == 2  # no later mutation


def baseline():
    before = {**SOURCES, 'main.py': 'def twice(n):\n    return n + 2\n'}
    hashes = {p: digest(s) for p, s in before.items()}
    current = {p: digest(s) for p, s in SOURCES.items()}
    artifact = default_repository().put_artifact(json.dumps(before, sort_keys=True).encode(),
                                               name='baseline.json', media_type='application/json')
    return {'sources': before, 'source_hashes': hashes, 'current_hashes': current,
            'revision': digest(json.dumps(hashes, sort_keys=True)),
            'current_revision': digest(json.dumps(current, sort_keys=True)),
            'artifact_sha256': artifact.sha256}


def gap(revision, **updates):
    return {'criterion_id': '0', 'kind': 'executed_assertion', 'path': 'main.py',
            'source_revision': revision, 'request': 'Assert argument handling', **updates}


async def review(provider, evidence):
    return await review_semantics(provider, request='Double and preserve CLI',
        contracts=['Double and preserve CLI'], sources=SOURCES,
        tests={'status': 'passed', 'passed_cases': ['test_main.py::test_twice']},
        progressive=True, runtime_evidence={'_baseline': evidence})


@pytest.mark.asyncio
async def test_reviewer_receives_runtime_original_and_diff():
    evidence = baseline()
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps({'decision': 'needs_evidence',
        'contradictions': [], 'coverage': [], 'missing_evidence': [gap(evidence['current_revision'])]})
    result = await review(provider, evidence)
    context = json.loads(provider.chat_complete.call_args.kwargs['messages'][1]['content'])
    assert context['observations'][0]['runtime_baseline_sources']['main.py'] == evidence['sources']['main.py']
    assert '-    return n + 2' in context['baseline']['changes'][0]['diff']
    assert result.details['evidence_requests'][0]['criterion_id'] == '0'
    assert result.details['repairable_evidence_gap']


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['original', 'candidate', 'artifact'])
async def test_baseline_substitution_and_stale_revision_block_before_review(mutation):
    evidence = baseline()
    if mutation == 'original':
        evidence['sources']['main.py'] = SOURCES['main.py']
    elif mutation == 'candidate':
        evidence['current_hashes']['main.py'] = '0' * 64
    else:
        evidence['artifact_sha256'] = '0' * 64
    provider = AsyncMock()
    result = await review(provider, evidence)
    assert result.status == 'inconclusive'
    assert result.details['requires_arbitration']
    provider.chat_complete.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('updates', [{'criterion_id': '99'}, {'source_revision': 'stale'}, {'path': '../other.py'}])
async def test_structured_gap_rejects_wrong_criterion_revision_or_path(updates):
    evidence = baseline()
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps({'decision': 'needs_evidence',
        'contradictions': [], 'coverage': [], 'missing_evidence': [gap(evidence['current_revision'], **updates)]})
    result = await review(provider, evidence)
    assert result.details['requires_arbitration']
    assert not result.details.get('repairable_evidence_gap')


@pytest.mark.asyncio
async def test_available_baseline_is_resolved_inside_review_without_worker_patch():
    calls = []
    responses = iter([
        {'action': {'type': 'read', 'path': 'main.py'}},
        {'action': {'type': 'read', 'path': 'test_main.py'}},
        {'decision': 'needs_evidence', 'coverage': [], 'missing_evidence': [gap('rev', kind='baseline_source')]},
        {'decision': 'needs_evidence', 'coverage': [], 'missing_evidence': [gap('rev')]},
    ])
    async def complete(**kwargs):
        from tests.test_maintenance import recorded_stub_usage
        recorded_stub_usage()
        calls.append(json.loads(kwargs['messages'][1]['content']))
        return json.dumps(next(responses))
    context = {'sources': SOURCES, 'baseline_sources': {**SOURCES, 'large.py': '# original\n' * 6000},
        'baseline': {'current_revision': 'rev'}, 'criteria': [{'id': '0', 'text': 'Preserve CLI'}],
        'passing_tests': ['test_main.py::test_twice'], 'test_report': {'status': 'passed'}, 'runtime_evidence': {}}
    result = await _progressive_review(type('Provider', (), {'chat_complete': staticmethod(complete)})(),
                                        {'content': 'Review'}, context)
    assert json.loads(result)['missing_evidence'][0]['kind'] == 'executed_assertion'
    assert calls[-1]['observations'][-1]['runtime_baseline'] == 'main.py'
    assert len(calls) == 4


def state(epoch=0):
    return {'source_epoch': epoch, 'phase': 'investigating', 'reads': {'items': []}}


def test_events_send_only_new_batch_and_preserve_initial_context_on_restart():
    log = MaintenanceContext()
    context = {'objective': 'repair', 'acceptance': ['preserve'], 'runtime_state': state(),
               'observations': [], 'remaining_actions': 40}
    log.append({'id': 'initial', 'result': {'status': 'failed'}})
    first = log.messages('Rules', context, persistent=True)
    accepted = {'message_hashes': [message_digest(m) for m in first[1:]],
                'instructions_hash': message_digest([first[0]])}
    log.append({'id': 'read-1', 'result': {'content': 'actual source'}})
    second = log.messages('Rules', {**context, 'runtime_state': state(1)}, persistent=True)
    delta, hashes = incremental_messages(second, json.loads(json.dumps(accepted)))
    assert len(delta) == 1
    batch = json.loads(delta[0]['content'])
    assert batch['events'][0]['event_id'] == 2
    assert batch['state_changes'] == {'source_epoch': 1}
    assert 'objective' not in batch and 'initial' not in batch
    assert second[:len(first)] == first
    repeated = log.messages('Rules', {**context, 'runtime_state': state(1)}, persistent=True)
    assert repeated == second
    assert incremental_messages(repeated, hashes)[0][0]['content'].startswith('Continue')


def test_stateless_provider_always_receives_self_contained_context():
    context = {'objective': 'repair', 'runtime_state': state(), 'observations': [{'source': 'x'}]}
    messages = MaintenanceContext().messages('Rules', deepcopy(context))
    assert json.loads(messages[1]['content']) == context


def test_mutating_live_read_metadata_never_changes_previously_sent_batches():
    log = MaintenanceContext()
    read = {'path': 'main.py', 'observation_ids': ['read-1'], 'ranges': [[1, 10]]}
    context = {'runtime_state': {'reads': [read]}, 'remaining_actions': 40, 'observations': []}
    result = {'pages': [{'content': 'original'}]}
    log.append({'result': result})
    first = log.messages('Rules', context, persistent=True)
    accepted = {'instructions_hash': message_digest([first[0]]),
                'message_hashes': [message_digest(m) for m in first[1:]]}
    # MaintenanceState.read extends observation_ids in place when rereading a file.
    read['observation_ids'].append('read-2')
    read['ranges'].append([11, 20])
    result['pages'][0]['content'] = 'mutated caller value'
    log.append({'result': {'content': 'new page'}})
    second = log.messages('Rules', context, persistent=True)
    assert second[:len(first)] == first
    delta, _ = incremental_messages(second, accepted)
    assert len(delta) == 1
    assert json.loads(delta[0]['content'])['state_changes']['reads'][0]['observation_ids'] == ['read-1', 'read-2']
    assert log.events[0]['result']['pages'][0]['content'] == 'original'


@pytest.mark.asyncio
async def test_real_maintenance_captures_baseline_and_persists_unique_grouped_events(tmp_path):
    from tests.test_maintenance import project, approved_payload, ScriptedProvider, patch
    from bigbrain.brains.python_brain import PythonBrain
    from bigbrain.bus.bus import MessageBus
    target = project(tmp_path)
    payload, transaction = approved_payload(target)
    original = target.file('arithmetic.py').read_text()
    provider = ScriptedProvider([
        {'type': 'read_many', 'reads': [{'path': 'arithmetic.py'}, {'path': 'main.py'}]}, patch()])
    provider.maintenance_event_context = True
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=target.root, llm_provider=provider)
    brain.maintenance_diagnose = AsyncMock(return_value={'status': 'failed',
        'diagnostic_output': 'original failure', 'output_tail': 'original failure'})
    captured = {}
    async def verify(received, tools):
        captured.update(received['_maintenance_runtime_evidence']['_baseline'])
        return {'success': True, 'verification': {'verdict': 'passed'}}
    brain.maintenance_verify = verify
    try:
        with brain.execution_scope(payload):
            result = await brain.maintain_project(payload)
        assert result['success']
        assert captured['sources']['arithmetic.py'] == original
        assert captured['current_hashes']['arithmetic.py'] != captured['source_hashes']['arithmetic.py']
        original_diagnostic = json.loads(default_repository().get_artifact(captured['initial_diagnostic']['artifact_sha256']))
        assert original_diagnostic['diagnostic_output'] == 'original failure'
        steps = [s for s in result['maintenance']['actions'] if 'event_id' in s]
        assert [s['event_id'] for s in steps] == list(range(1, len(steps) + 1))
        events = [json.loads(default_repository().get_artifact(s['event_artifact_sha256'])) for s in steps]
        assert events[0]['result'].get('output_tail') is None
        assert sum(e['action'] == 'read_many' for e in events) == 1
        assert not any(e['action'] == 'read' for e in events)
        first = provider.calls[0]
        state = {'instructions_hash': message_digest([first[0]]),
                 'message_hashes': [message_digest(m) for m in first[1:]]}
        delta, _ = incremental_messages(provider.calls[1], state)
        assert len(delta) == 1
        batch = json.loads(delta[0]['content'])
        assert len(batch['events']) == 1
        assert batch['events'][0]['result']['pages'][0]['path'] == 'arithmetic.py'
        assert 'contract_revision' not in batch
    finally:
        transaction.finish()
        await bus.close()


@pytest.mark.asyncio
async def test_original_diagnostic_is_authenticated_and_shown_to_reviewer():
    evidence = baseline()
    diagnostic = {'status': 'failed', 'diagnostic_output': 'assert 5 == 6', 'output_tail': 'assert 5 == 6'}
    artifact = default_repository().put_artifact(json.dumps(diagnostic).encode(),
        name='diagnostic.json', media_type='application/json')
    evidence['initial_diagnostic'] = {'source_hashes': evidence['source_hashes'], 'artifact_sha256': artifact.sha256}
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps({'decision': 'needs_evidence', 'contradictions': [],
        'coverage': [], 'missing_evidence': [gap(evidence['current_revision'])]})
    result = await review(provider, evidence)
    assert result.details['repairable_evidence_gap']
    sent = json.loads(provider.chat_complete.call_args.kwargs['messages'][1]['content'])
    assert sent['initial_diagnostic'] == {'status': 'failed', 'diagnostic_output': 'assert 5 == 6'}


@pytest.mark.asyncio
@pytest.mark.parametrize('request_text', [None, 'A different approved task'])
async def test_contract_request_mismatch_stops_before_diagnostics_or_inference(tmp_path, request_text):
    from tests.test_maintenance import project, approved_payload, ScriptedProvider
    from bigbrain.brains.python_brain import PythonBrain
    from bigbrain.bus.bus import MessageBus
    from bigbrain.maintenance import maintain
    target = project(tmp_path)
    payload, transaction = approved_payload(target)
    payload['user_request'] = request_text
    provider = ScriptedProvider([])
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=target.root, llm_provider=provider)
    diagnose, verify = AsyncMock(), AsyncMock()
    try:
        with brain.execution_scope(payload), pytest.raises(ValueError, match='another request'):
            await maintain(brain, payload, diagnose=diagnose, verify=verify)
        diagnose.assert_not_called()
        verify.assert_not_called()
        assert not provider.calls
    finally:
        transaction.finish()
        await bus.close()
