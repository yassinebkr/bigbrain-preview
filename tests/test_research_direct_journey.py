"""Offline direct-controller journeys through the production acquisition boundary."""
import asyncio
import json
import time
from unittest.mock import AsyncMock

import pytest

from bigbrain.research import Limits, PageReader, Question, ResearchRuntime, ResearchState
from bigbrain.research_acquisition import Response, artifact
from bigbrain.research_direct import DirectFinish, DirectReply, run_direct
from bigbrain.research_direct_controller import DirectLimits

URL = 'https://docs.test/reference'
FACT = 'The documented limit is seven. Applies indoors only.'


class FixtureFetcher:
    def __init__(self, status=200):
        self.status, self.calls = status, []

    async def fetch(self, url):
        self.calls.append(url)
        body = ('<main><p>' + FACT + '</p></main>').encode()
        return Response(url, self.status, body, {'content-type': 'text/html'}, 'utf-8',
                        artifact(body, name='direct-fixture.html', media_type='text/html'), ())


def runtime(status=200):
    fetcher = FixtureFetcher(status)
    engine = ResearchRuntime(AsyncMock(), PageReader(fetcher=fetcher), AsyncMock(), AsyncMock(),
                             limits=Limits(seconds=120))
    engine.state = ResearchState(objective=f'Establish the limit from {URL}',
        questions=[Question(id='q1', text='Establish the qualified limit', evidence_needed='Read the reference')])
    engine.started = time.monotonic()
    return engine, fetcher


def conclusion(packet):
    passages = packet['working_set']['passages']
    if not passages:
        return {'questions': [{'question_id': 'q1', 'gaps': ['Report contents remain unread']}]}
    passage = next(p for p in passages if FACT in p['text'])
    citation = {'passage_id': passage['id'], 'receipt_id': passage.get('receipt_id', ''),
                'quote': FACT, 'relation': 'supports', 'direct': True}
    return {'findings': [{'id': 'f1', 'question_id': 'q1', 'text': FACT,
                         'semantic_support': 'supported', 'scope_detail': 'Documented indoor limit',
                         'citations': [citation]}],
            'questions': [{'question_id': 'q1', 'finding_ids': ['f1']}],
            'sources': [{'source_id': passage['source_id'], 'kind': 'primary',
                         'nature': 'documentation', 'suitability': 'suitable',
                         'basis': 'Observed reference statement', 'provenance_passage_id': passage['id'],
                         'provenance_quote': FACT}]}


class ScriptedAdapter:
    def __init__(self):
        self.calls = []

    def forecast(self, packet, contract):
        return 1000, 1000 if contract is DirectFinish else 200

    async def infer(self, packet, reservation, contract):
        self.calls.append((packet, reservation, contract))
        if len(self.calls) == 1:
            return DirectReply({'kind': 'acquire', 'requests': [{'tool': 'visit', 'url': URL,
                'question_id': 'q1', 'rationale': 'Read the supplied public reference'}]})
        result = {'conclusion': conclusion(packet)}
        if contract is not DirectFinish:
            result['kind'] = 'finish'
        return DirectReply(result)


@pytest.mark.asyncio
async def test_direct_read_and_finish_use_one_adapter_without_an_independent_review():
    engine, fetcher = runtime()
    adapter = ScriptedAdapter()
    state = await run_direct(engine, adapter, limits=DirectLimits(calls=2))
    assert state.execution_outcome == 'complete', state.reason
    assert fetcher.calls == [URL]
    assert len(adapter.calls) == 2
    assert adapter.calls[-1][2] is DirectFinish
    assert all(len(json.dumps(p, ensure_ascii=False).encode()) < 12000 for p, _, _ in adapter.calls)
    assert state.claims[0].status == 'supported'
    assert state.usage['direct_result']['independent_review'] == 'skipped'
    assert engine.counts['reviews'] == 0
    assert state.question_coverage[0]['status'] == 'covered'


@pytest.mark.asyncio
async def test_visit_forwards_source_language_reading_intent_to_the_reader():
    engine, _ = runtime()
    adapter = ScriptedAdapter()
    original = adapter.infer
    intent = 'What is the documented limit and its qualification?'

    async def with_intent(packet, reservation, contract):
        reply = await original(packet, reservation, contract)
        if len(adapter.calls) == 1:
            reply.value['requests'][0]['reading_question'] = intent
        return reply

    adapter.infer = with_intent
    engine.reader.read = AsyncMock(wraps=engine.reader.read)
    state = await run_direct(engine, adapter)
    assert state.execution_outcome == 'complete'
    assert intent in str(engine.reader.read.call_args)


@pytest.mark.asyncio
async def test_rejected_repeated_proposal_returns_feedback_within_the_same_allowance():
    engine, fetcher = runtime()
    adapter = ScriptedAdapter()
    original = adapter.infer

    async def repeat_once(packet, reservation, contract):
        reply = await original(packet, reservation, contract)
        if len(adapter.calls) == 2:
            return DirectReply({'kind': 'acquire', 'requests': [{
                'tool': 'visit', 'url': URL, 'question_id': 'q1',
                'rationale': 'Repeat the exact same read'}]})
        return reply

    adapter.infer = repeat_once
    state = await run_direct(engine, adapter)
    assert state.execution_outcome == 'complete', state.reason
    assert fetcher.calls == [URL]
    assert len(adapter.calls) == 3
    assert state.observations[-1].data['executed'] is False
    assert 'Repeated action blocked' in state.observations[-1].data['error']
    assert 'Repeated action blocked' in str(adapter.calls[2][0]['working_set']['recent_actions'])


@pytest.mark.asyncio
async def test_premature_partial_gets_one_targeted_complement_with_finish_reserve():
    engine, _ = runtime()
    adapter = ScriptedAdapter()
    original = adapter.infer

    async def partial_then_complete(packet, reservation, contract):
        reply = await original(packet, reservation, contract)
        if len(adapter.calls) == 2:
            reply.value['conclusion']['questions'][0]['gaps'] = ['Read the usage qualification']
        return reply

    adapter.infer = partial_then_complete
    state = await run_direct(engine, adapter, limits=DirectLimits(calls=4))
    assert state.execution_outcome == 'complete', state.reason
    assert len(adapter.calls) == 3
    assert state.usage['direct_complement']['after_call'] == 2
    assert adapter.calls[2][0]['working_set']['original_request_gaps'] == ['Read the usage qualification']


@pytest.mark.asyncio
async def test_persistent_gap_cannot_repeat_the_complement_cycle():
    engine, _ = runtime()
    adapter = ScriptedAdapter()
    original = adapter.infer

    async def always_partial(packet, reservation, contract):
        reply = await original(packet, reservation, contract)
        if 'conclusion' in reply.value:
            reply.value['conclusion']['questions'][0]['gaps'] = ['Unread qualification']
        return reply

    adapter.infer = always_partial
    state = await run_direct(engine, adapter)
    assert state.execution_outcome == 'partial'
    assert len(adapter.calls) == 3


@pytest.mark.asyncio
async def test_complement_preserves_the_finish_allowance():
    engine, _ = runtime()
    adapter = ScriptedAdapter()
    original = adapter.infer

    async def partial(packet, reservation, contract):
        reply = await original(packet, reservation, contract)
        if 'conclusion' in reply.value:
            reply.value['conclusion']['questions'][0]['gaps'] = ['Unread qualification']
        return reply

    adapter.infer = partial
    state = await run_direct(engine, adapter, limits=DirectLimits(input_units=3300))
    assert state.execution_outcome == 'partial'
    assert len(adapter.calls) == 2
    assert 'direct_complement' not in state.usage


@pytest.mark.asyncio
async def test_real_403_receipt_settles_blocked_without_an_invented_answer():
    engine, fetcher = runtime(403)
    state = await run_direct(engine, ScriptedAdapter(), limits=DirectLimits(calls=2))
    assert state.execution_outcome == 'blocked', state.reason
    assert fetcher.calls == [URL]
    assert not state.claims and not state.passages
    assert '403' in str(state.observations)


@pytest.mark.asyncio
async def test_required_review_preserves_the_cited_result_as_partial():
    engine, _ = runtime()
    state = await run_direct(engine, ScriptedAdapter(), limits=DirectLimits(calls=2), review_required=True)
    assert state.execution_outcome == 'partial'
    assert state.usage['direct_result']['independent_review'] == 'required'


@pytest.mark.asyncio
async def test_malformed_model_decision_settles_failed_without_tool_execution():
    engine, fetcher = runtime()
    adapter = ScriptedAdapter()
    adapter.infer = AsyncMock(return_value=DirectReply('unstructured text'))
    state = await run_direct(engine, adapter)
    assert state.execution_outcome == 'failed'
    assert state.diagnostic['type'] == 'ModelResponseError'
    assert 'response_artifact' in state.diagnostic
    assert not fetcher.calls
    assert state.workflow['budget']['calls'] == 1


@pytest.mark.asyncio
async def test_unknown_usage_overrun_stops_before_new_acquisition():
    engine, fetcher = runtime()
    adapter = ScriptedAdapter()
    original = adapter.infer
    async def overrun(*args):
        reply = await original(*args)
        return DirectReply(reply.value, input_units=65000, output_units=100)
    adapter.infer = overrun
    state = await run_direct(engine, adapter)
    assert state.execution_outcome == 'partial'
    assert not fetcher.calls
    assert state.workflow['budget']['input_units'] == 65000


@pytest.mark.asyncio
async def test_stop_interrupts_a_pending_model_call_and_records_its_allowance():
    engine, _ = runtime()
    adapter = ScriptedAdapter()
    started = asyncio.Event()
    stopped = False
    engine.cancelled = lambda: stopped
    async def pending(*args):
        started.set()
        await asyncio.Event().wait()
    adapter.infer = pending
    task = asyncio.create_task(run_direct(engine, adapter))
    await asyncio.wait_for(started.wait(), 1)
    stopped = True
    state = await asyncio.wait_for(task, 1)
    assert state.execution_outcome == 'cancelled'
    assert len(state.workflow['budget']['records']) == 1
    assert state.workflow['budget']['records'][0]['outcome'] == 'cancelled'


@pytest.mark.asyncio
async def test_provider_timeout_has_a_terminal_result():
    engine, _ = runtime()
    adapter = ScriptedAdapter()
    async def pending(*args):
        await asyncio.Event().wait()
    adapter.infer = pending
    state = await run_direct(engine, adapter, limits=DirectLimits(seconds=.05, finish_seconds=.01))
    assert state.execution_outcome == 'partial'
    assert state.phase == 'settled'
    assert len(state.workflow['budget']['records']) == 1


@pytest.mark.asyncio
async def test_progress_failure_still_settles_the_admitted_attempt():
    engine, _ = runtime()
    engine.emit = AsyncMock(side_effect=RuntimeError('Controlled progress failure'))
    state = await run_direct(engine, ScriptedAdapter())
    assert state.execution_outcome == 'failed'
    assert state.workflow['budget']['records'][0]['outcome'] == 'interrupted'


@pytest.mark.asyncio
async def test_acquisition_timeout_uses_its_remaining_synthesis_reserve():
    engine, _ = runtime()
    adapter = ScriptedAdapter()
    engine.execute = AsyncMock(side_effect=TimeoutError('Controlled acquisition timeout'))
    state = await run_direct(engine, adapter)
    assert state.execution_outcome == 'partial'
    assert adapter.calls[-1][2] is DirectFinish
    assert len(adapter.calls) == 2
    assert state.observations[0].status == 'error'


@pytest.mark.asyncio
async def test_invalid_adapter_usage_still_has_a_terminal_diagnostic():
    engine, _ = runtime()
    adapter = ScriptedAdapter()
    adapter.infer = AsyncMock(return_value=DirectReply({'kind': 'clarify',
        'clarification': 'Which document?'}, input_units=-1))
    state = await run_direct(engine, adapter)
    assert state.execution_outcome == 'failed'
    assert state.workflow['budget']['records'][0]['outcome'] == 'interrupted'


@pytest.mark.asyncio
async def test_direct_defaults_bound_acquisition_without_expanding_stricter_runtime_limits():
    engine, _ = runtime()
    engine.limits.browsers = 0
    await run_direct(engine, ScriptedAdapter(), limits=DirectLimits(calls=2))
    assert engine.limits.pages == 4
    assert engine.limits.searches == 3
    assert engine.limits.browsers == 0


@pytest.mark.asyncio
async def test_unreservable_money_cap_stops_before_any_model_call():
    engine, _ = runtime()
    engine.limits.cost_usd = .01
    adapter = ScriptedAdapter()
    state = await run_direct(engine, adapter)
    assert state.execution_outcome == 'failed'
    assert not adapter.calls
    assert 'priced transport' in state.diagnostic['message']


@pytest.mark.asyncio
async def test_local_selection_reads_stored_text_without_repeating_a_network_operation():
    engine, fetcher = runtime()
    class SelectingAdapter(ScriptedAdapter):
        async def infer(self, packet, reservation, contract):
            if len(self.calls) == 1:
                self.calls.append((packet, reservation, contract))
                passage = packet['working_set']['passages'][0]
                return DirectReply({'kind': 'select', 'windows': [{'passage_id': passage['id'],
                    'start': 0, 'end': len(passage['text'])}]})
            return await super().infer(packet, reservation, contract)
    adapter = SelectingAdapter()
    state = await run_direct(engine, adapter, limits=DirectLimits(calls=3))
    assert state.execution_outcome == 'complete', state.reason
    assert len(adapter.calls) == 3
    assert fetcher.calls == [URL]


@pytest.mark.asyncio
async def test_invalid_local_selection_settles_with_a_diagnostic():
    engine, _ = runtime()
    adapter = ScriptedAdapter()
    adapter.infer = AsyncMock(return_value=DirectReply({'kind': 'select',
        'windows': [{'passage_id': 'invented', 'start': 0, 'end': 10}]}))
    state = await run_direct(engine, adapter)
    assert state.execution_outcome == 'failed'
    assert 'current observed receipt' in state.diagnostic['message']
