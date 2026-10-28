"""Complementary page consultations and cited delivery through the worker."""
import asyncio
import json
import time
from unittest.mock import AsyncMock

import pytest

from bigbrain.brains.researcher import ResearcherBrain
from bigbrain.bus.auth import BusAuth
from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.research import (PageReader, Question, ResearchActionRejected,
    ResearchRuntime, ResearchState, Source, Limits)
from tests.test_research_acquisition import act, html_response, network

FACTS = ['Alpha retains the original entry on conflict.',
         'Beta includes ignored items only when explicitly requested.']
HTML = '<main><dl><dt>alpha</dt><dd><p>' + FACTS[0] + '</p></dd><dt>beta</dt><dd><p>' + FACTS[1] + '</p></dd></dl></main>'


def grouped(first=None, second=None):
    return act('batch', requests=[
        {'tool':'open', 'question_id':'q1', 'rationale':'Read the definition',
         'source_id':'s1', 'focus':'alpha', **(first or {})},
        {'tool':'open', 'question_id':'q1', 'rationale':'Read the qualification',
         'source_id':'s1', 'focus':'beta', **(second or {})}])


@pytest.mark.asyncio
@pytest.mark.parametrize('first,second,pages', [
    ({}, {'focus':'alpha'}, 4), ({}, {'refresh':True}, 4),
    ({'refresh':True}, {}, 4), ({}, {'mode':'browser'}, 4),
    ({}, {'focus':None}, 4),
    ({}, {'tool':'visit', 'source_id':None, 'url':'https://public.test/manual', 'focus':'alpha'}, 4),
])
async def test_unsafe_or_duplicate_group_rejected_before_io(monkeypatch, first, second, pages):
    calls = network(monkeypatch, lambda request: html_response(HTML))
    runtime = ResearchRuntime(AsyncMock(), PageReader(), AsyncMock(), AsyncMock(), limits=Limits(pages=pages))
    state = ResearchState(objective='Read both definitions',
        questions=[Question(id='q1', text='Definitions', evidence_needed='Both conditions')],
        sources=[Source(id='s1', url='https://public.test/manual', discovered_by='query',
                        acquisition={'status':'available'})])
    runtime.state, runtime.started = state, time.monotonic()
    with pytest.raises(ResearchActionRejected):
        await runtime.execute(state, grouped(first, second), runtime.counts, set(), 0)
    assert not calls and not state.passages
    assert runtime.counts['pages'] == runtime.counts['browsers'] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('locked_scope', [False, True])
@pytest.mark.parametrize('correction', ['none', 'uncited_gap', 'context_only', 'bad_type'])
async def test_authenticated_same_page_batch_has_bounded_stage_outcomes(monkeypatch, tmp_path, correction, locked_scope):
    uncited_gap = correction == 'uncited_gap'
    calls = network(monkeypatch, lambda request: html_response(HTML))
    class Inference:
        calls = 0

        async def complete(self, prompt, **kwargs):
            self.calls += 1
            from bigbrain.llm.usage import UsageRecord, get_tracker
            get_tracker().record(UsageRecord(model_id='gpt-6-luna', provider='fixture',
                input_tokens=600, output_tokens=150, total_tokens=750))
            packet = json.loads(prompt.split('\n', 1)[1])
            if self.calls == 1:
                assert packet['state']['scope_locked']
                return json.dumps({'requests':[{'tool':'search','question_id':'q1',
                    'query':'Definitions','rationale':'Discover the reference'}]})
            if self.calls == 2:
                decision = {'requests':[r.model_dump() for r in grouped().requests]}
                if correction == 'bad_type':
                    decision['requests'][0]['rationale'] = None
                return json.dumps(decision)
            dossier = packet['dossier']
            if self.calls == 3:
                claims = [{'id':f'c{i}', 'question_id':f'q{i+1}' if locked_scope else 'q1', 'text':text,
                    'basis':'Observed definition', 'evidence':[{
                        'passage_id':next(p['id'] for p in dossier['passages'] if p['text'] == text),
                        'relation':'supports'}]} for i, text in enumerate(FACTS)]
                return json.dumps({'dossier_sha256':packet['dossier_sha256'], 'claims':claims,
                    'remaining_gaps':['The older version remains unread.'] if uncited_gap else []})
            claims = packet['draft']['claims']
            return json.dumps({'dossier_sha256':packet['dossier_sha256'], 'original_request_complete':not uncited_gap,
                'sources':[{'source_id':'s1','kind':'primary','nature':'documentation','suitability':'suitable',
                    'basis':'Observed reference definitions','provenance_passage_id':claims[0]['evidence'][0]['passage_id']}],
                'claims':[{'claim_id':c['id'],'relevant':True,'rationale':'Definition in the reference',
                    'considered_source_ids':['s1'],'citations':[{'passage_id':c['evidence'][0]['passage_id'],
                        'relation':'context' if correction == 'context_only' else 'supports','direct':correction != 'context_only',
                        'explanation':'Inspected definition'}]} for c in claims],
                'questions':[{'question_id':q['id'],'complete':not uncited_gap,
                    'claim_ids':[c['id'] for c in claims if c['question_id']==q['id']], 'rationale':'Definitions inspected'}
                    for q in dossier['questions']]})

    inference = Inference()
    search = AsyncMock()
    search.search.return_value = [{'url':'https://public.test/manual'}]
    auth = BusAuth()
    for name in ('morphable_ui', 'researcher'):
        auth.generate_token(name)
    bus = MessageBus(tmp_path/'logs', auth=auth)
    worker = ResearcherBrain('researcher', bus, llm_provider=inference,
        search_provider=search, page_reader=PageReader(), research_workflow="staged")
    done, results, finished = asyncio.Event(), [], []
    async def observe(message):
        if message.type == MessageType.RESULT:
            results.append(message.payload)
            done.set()
        if message.payload.get('stage') == 'research_finished':
            finished.append(message.payload['research'])
    bus.subscribe('morphable_ui', observe)
    try:
        await worker.start()
        await bus.send(BusMessage(type=MessageType.TASK, source='morphable_ui', target='researcher',
            payload={'type':'research', 'query':'Read both definitions', 'session_id':'complementary',
                     **({'obligations':['Establish the Alpha definition', 'Establish the Beta definition']} if locked_scope else {})}), require_target=True)
        await asyncio.wait_for(done.wait(), 8)
        assert len(results) == len(finished) == 1
        data = results[0].get('data', results[0])
        evidence = data['evidence']
        assert data['success'] is (correction == 'none'), data.get('error')
        assert evidence['status'] == ('completed' if correction == 'none' else 'partial')
        assert [c['text'] for c in evidence['claims']] == ([] if correction == 'bad_type' else FACTS)
        assert evidence['scope_locked']
        assert len(evidence['questions']) == (2 if locked_scope else 1)
        assert len(calls) == (0 if correction == 'bad_type' else 1)
        assert inference.calls == (2 if correction == 'bad_type' else 4)
        assert finished[0]['counts']['pages'] == (0 if correction == 'bad_type' else 1)
        if correction == 'bad_type':
            assert evidence['diagnostic']['code'] == 'schema_invalid'
            return
        assert len({p['observation_sha256'] for p in evidence['passages']}) == 1
        batch = next(o for o in evidence['observations'] if o['action']['tool'] == 'batch')
        assert all(item['status'] == 'ok' for item in batch['data']['items'])
    finally:
        await worker.stop()
        await bus.close()


@pytest.mark.asyncio
async def test_cached_sections_remain_readable_after_network_budget(monkeypatch):
    from bigbrain.research import research_tools
    calls = network(monkeypatch, lambda request: html_response(HTML))
    runtime = ResearchRuntime(AsyncMock(), PageReader(), AsyncMock(), AsyncMock(), limits=Limits(pages=1))
    state = ResearchState(objective='Read both definitions',
        questions=[Question(id='q1', text='Definitions', evidence_needed='Conditions')],
        sources=[Source(id='s1', url='https://public.test/manual', discovered_by='query')])
    runtime.state, runtime.started = state, time.monotonic()
    attempted = set()
    await runtime.execute(state, grouped(), runtime.counts, attempted, 0)
    assert runtime.counts['pages'] == len(calls) == 1
    assert 'open' in research_tools(state, {'pages':0, 'actions':2, 'cached_source_ids':['s1']})
    observation = await runtime.execute(state, act('open', source_id='s1', focus='retains'), runtime.counts, attempted, 4)
    assert observation.status == 'ok'
    assert runtime.counts['pages'] == len(calls) == 1
    assert any(FACTS[0] in p.text for p in state.passages)
    runtime.reader.cache_seconds = 0
    with pytest.raises(ResearchActionRejected):
        await runtime.execute(state, act('open', source_id='s1', focus='original'), runtime.counts, attempted, 5)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_expired_cache_only_read_performs_no_network(monkeypatch):
    from bigbrain.research_acquisition import ReadFailure
    calls = network(monkeypatch, lambda request: html_response(HTML))
    reader = PageReader()
    page = await reader.read('https://public.test/manual', focus='alpha')
    reader.cache_seconds = 0
    with pytest.raises(ReadFailure) as failed:
        await reader.read('https://public.test/manual', focus='beta', cached_snapshot=page['sha256'])
    assert failed.value.status == 'cache_expired'
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_failed_batch_acquisition_cannot_bypass_network_quota(monkeypatch):
    calls = network(monkeypatch, lambda request: html_response('Blocked', 403))
    runtime = ResearchRuntime(AsyncMock(), PageReader(), AsyncMock(), AsyncMock(), limits=Limits(pages=1))
    state = ResearchState(objective='Read definitions',
        questions=[Question(id='q1', text='Definitions', evidence_needed='Conditions')],
        sources=[Source(id='s1', url='https://public.test/manual', discovered_by='query')])
    runtime.state, runtime.started = state, time.monotonic()
    with pytest.raises(ResearchActionRejected):
        await runtime.execute(state, grouped(), runtime.counts, set(), 0)
    assert len(calls) == runtime.counts['pages'] == 1


@pytest.mark.asyncio
async def test_section_selectors_work_in_single_and_grouped_reads(monkeypatch):
    from bigbrain.research_context import groups
    from bigbrain.research_extraction import extract_html
    calls = network(monkeypatch, lambda request: html_response(HTML))
    runtime = ResearchRuntime(AsyncMock(), PageReader(), AsyncMock(), AsyncMock(), limits=Limits(pages=1))
    state = ResearchState(objective='Read definitions',
        questions=[Question(id='q1', text='Definitions', evidence_needed='Conditions')],
        sources=[Source(id='s1', url='https://public.test/manual', discovered_by='query')])
    runtime.state, runtime.started = state, time.monotonic()
    attempted = set()
    await runtime.execute(state, act('open', source_id='s1', focus='alpha'), runtime.counts, attempted, 0)
    digest = state.sources[0].content_sha256
    sections = groups(extract_html(HTML, state.sources[0].url)['original_blocks'], digest)
    ids = [next(s['id'] for s in sections if text in ' '.join(b['text'] for b in s['blocks'])) for text in FACTS]
    action = act('batch', requests=[{'tool':'open', 'question_id':'q1', 'rationale':'Read exact section',
        'source_id':'s1', 'group_ids':[identity], 'observation_sha256':digest} for identity in ids])
    observation = await runtime.execute(state, action, runtime.counts, attempted, 1)
    assert observation.status == 'ok' and all(item['status'] == 'ok' for item in observation.data['items'])
    assert len(calls) == runtime.counts['pages'] == 1
    assert all(any(text == p.text for p in state.passages) for text in FACTS)
    # Exact repeated sections are rejected before touching the retained page.
    with pytest.raises(ResearchActionRejected):
        await runtime.execute(state, action, runtime.counts, attempted, 4)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_delegated_scope_survives_plan_rejection_and_continuation():
    from tests.test_research_acquisition import Policy
    obligations = ['Establish the Alpha definition', 'Establish the Beta definition']
    runtime = ResearchRuntime(AsyncMock(), AsyncMock(), Policy(
        act('plan', questions=[{'id':'q1', 'text':'Expanded unrelated scope', 'evidence_needed':'Other facts'}]),
        act('clarify', clarification='Fixture pause')), AsyncMock(), documentary=True)
    state = await runtime.run('Compare definitions', obligations=obligations)
    assert [q.text for q in state.questions] == obligations
    assert state.observations[0].data['code'] == 'action_not_allowed'
    runtime.reader.read.assert_not_awaited()
    continued = ResearchRuntime(AsyncMock(), AsyncMock(), Policy(act('conclude')), AsyncMock(), documentary=True)
    restored = await continued.run('Retry', continuation=(state, 0), obligations=['Replace the scope'])
    assert restored.scope_locked and [q.text for q in restored.questions] == obligations
    assert restored.status == 'partial'


@pytest.mark.parametrize('obligations', [[], ['     '], ['A valid obligation']*2, ['A valid obligation']*7])
def test_front_research_scope_contract_rejects_ambiguous_obligations(obligations):
    from bigbrain.front.decision import ResearchInput
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ResearchInput(type='research', obligations=obligations)
