"""Worker-boundary identity and source-backed citation anchors."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from bigbrain.brains.researcher import ResearcherBrain
from bigbrain.bus.auth import BusAuth
from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.llm.conversation import current_conversation
from bigbrain.research_quotes import anchor_quote
from bigbrain.research_assessment import apply_assessment
from tests.test_research_assessment import evidence, report


@pytest.mark.parametrize('original,quoted', [
    ('Exceptions will be\nignored for missing files.', 'Exceptions will be ignored for missing files.'),
    ('Déjà\u00a0validé\tici.', 'Déjà validé ici.'),
    ('Prefix: exact source words. Suffix.', 'exact source words.')])
def test_anchor_extracts_the_exact_original_span(original, quoted):
    raw, start, end = anchor_quote(original, quoted)
    assert raw == original[start:end]
    assert ' '.join(raw.split()) == ' '.join(quoted.split())


@pytest.mark.parametrize('quoted', ['Exceptions will NOT be ignored.', 'exceptions will be ignored.',
    'Exceptions will be ignored!', 'Exceptionswillbeignored.'])
def test_anchor_rejects_changes_to_words_case_punctuation_or_boundaries(quoted):
    with pytest.raises(ValueError):
        anchor_quote('Exceptions will be\nignored.', quoted)


def test_repeated_quote_requires_offsets_and_validates_them():
    text = 'The documented value. The documented value.'
    with pytest.raises(ValueError, match='one original span'):
        anchor_quote(text, 'The documented value.')
    raw, start, end = anchor_quote(text, 'The documented value.', 22, len(text))
    assert raw == text[start:end] == 'The documented value.'
    with pytest.raises(ValueError, match='disagree'):
        anchor_quote(text, 'The documented value.', 0, 8)


def test_review_keeps_the_original_quote_and_hash_bound_offsets():
    state = evidence(('The documented API\nreturns an integer.',))
    state.passages[0].observation_sha256 = 'a'*64
    received = report(state)
    received.sources[0].provenance_quote = 'The documented API returns an integer.'
    received.claims[0].citations[0].quote = 'The documented API returns an integer.'
    claims, audit = apply_assessment(state, received)
    assert claims[0].status == 'supported'
    citation = audit[0]['citations'][0]
    anchor = audit[0]['quote_anchors'][0]
    assert citation['quote'] == state.passages[0].text
    assert state.passages[0].text[anchor['start']:anchor['end']] == citation['quote']
    assert anchor['observation_sha256'] == 'a'*64
    assert '\n' not in received.claims[0].citations[0].quote


def test_review_can_reference_full_passages_without_copying_words_or_counting_positions():
    from bigbrain.research_assessment import ModelReviewer, AssessmentReport
    state = evidence(('The documented API\nreturns an integer.',))
    received = report(state)
    received.claims[0].citations[0].quote = None
    received.sources[0].provenance_quote = None
    claims, audit = apply_assessment(state, received)
    assert claims[0].status == 'supported'
    assert audit[0]['citations'][0]['quote'] == state.passages[0].text
    assert audit[0]['citations'][0]['start'] == 0
    assert audit[0]['citations'][0]['end'] == len(state.passages[0].text)
    reviewer = ModelReviewer(AsyncMock())
    reviewer.request(state)
    fields = reviewer.protocol(AssessmentReport)['tool_schema']['parameters']['$defs']['CitationAssessment']['properties']
    assert 'start' not in fields and 'end' not in fields


def test_partial_delivery_preserves_supported_findings_and_excludes_drafts():
    from bigbrain.research_delivery import partial_message
    state = evidence()
    state.claims, state.assessments = apply_assessment(state, report(state))
    state.question_coverage[0].update(status='incomplete',missing_evidence=['A second version remains unread.'])
    text = partial_message(state)
    assert 'The API returns an integer' in text and 'https://source0.test/api' in text
    assert 'A second version remains unread.' in text
    state.claims[0].status = 'unverified'
    assert 'The API returns an integer' not in partial_message(state)


@pytest.mark.asyncio
async def test_valid_review_can_close_without_admitting_unaffordable_rewrites():
    from bigbrain.research import ModelPolicy
    from bigbrain.research_budget import ContextForecast
    from bigbrain.llm.conversation import conversation_scope
    from types import SimpleNamespace
    provider = SimpleNamespace(retains_conversation_context=True,
        estimate_tokens=lambda text:max(1,len(text)//4), complete=AsyncMock())
    provider.complete.return_value = json.dumps({'tool':'conclude','question_id':'q',
        'rationale':'Deliver the retained reviewed conclusions','claims':[]})
    policy = ModelPolicy(provider)
    policy.context_forecast = ContextForecast(retained_units=18000)
    with conversation_scope('closing-test','research'):
        await policy.choose(evidence(), {'tokens':35000,'actions':4,'reviews':1,
            'current_review':True,'revision_review_reserve':25000,'review_reserve':0})
    schema = provider.complete.call_args.kwargs['tool_schema']['parameters']
    assert schema['properties']['claims']['maxItems'] == 0
    assert schema['properties']['tool']['enum'] == ['conclude','clarify']


@pytest.mark.asyncio
async def test_failed_research_delivers_partial_message_once_through_orchestrator_and_front(tmp_path):
    from bigbrain.front.front_brain import FrontBrain
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, TaskPlan, SubTask, TaskStatus
    bus = MessageBus(tmp_path/'logs', auth=None)
    front = FrontBrain(bus, llm_provider=AsyncMock())
    front._soul_enabled = False
    orch = WorkspaceOrchestrator('default', bus)
    frames = []
    async def collect(frame):
        frames.append(frame)
    bus.subscribe('*', collect)
    original = BusMessage(type=MessageType.TASK,source='front_brain',target=orch.name,
        payload={'type':'research','session_id':'partial-test'})
    text = 'Recherche incomplète. Une seconde version reste à établir.'
    subtask = SubTask(id='research-step',description='Read the requested versions',brain_target='researcher',
        payload={'type':'research'},status=TaskStatus.FAILED,error='Coverage incomplete',
        result={'success':False,'data':{'research_status':'partial','public_message':text}})
    plan = TaskPlan(id='partial-plan',original_task=original,subtasks=[subtask],status=TaskStatus.RUNNING)
    try:
        await front.start()
        await orch._check_plan_completion(plan)
        await orch._check_plan_completion(plan)
        messages = [f.payload for f in frames if f.payload.get('event') == 'chat.message']
        terminals = [f.payload for f in frames if f.payload.get('event') == 'task.failed']
        assert len(messages) == len(terminals) == 1
        assert messages[0]['text'] == text
        front.llm_provider.complete.assert_not_awaited()
    finally:
        await front.stop()
        await bus.close()


@pytest.mark.asyncio
async def test_completed_research_preserves_late_citations_and_limits_in_chat(tmp_path):
    from bigbrain.front.front_brain import FrontBrain
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, TaskPlan, SubTask, TaskStatus
    from bigbrain.research_delivery import research_message
    from tests.test_research_documentary import candidate
    state = candidate()
    state.status = 'completed'
    state.claims[0].text = 'The documented API returns an integer.'
    state.claims[0].limitations = ['Applies to the inspected version only.']
    text = research_message(state)
    assert 'https://source0.test/api' in text and 'inspected version' in text
    bus = MessageBus(tmp_path/'logs', auth=None)
    front = FrontBrain(bus, llm_provider=AsyncMock())
    front._soul_enabled = False
    orch = WorkspaceOrchestrator('default', bus)
    frames = []
    async def collect(frame):
        frames.append(frame)
    bus.subscribe('*', collect)
    original = BusMessage(type=MessageType.TASK, source='front_brain', target=orch.name,
        payload={'type':'research', 'session_id':'completed-test'})
    subtask = SubTask(id='research-step', description='Read reference', brain_target='researcher',
        payload={'type':'research'}, status=TaskStatus.COMPLETE,
        result={'success':True, 'data':{'research_status':'completed', 'public_message':text,
            'summary':'Long collected findings. ' * 300 + 'https://source0.test/api'}})
    plan = TaskPlan(id='completed-plan', original_task=original, subtasks=[subtask], status=TaskStatus.RUNNING)
    try:
        await front.start()
        await orch._check_plan_completion(plan)
        await orch._check_plan_completion(plan)
        messages = [f.payload for f in frames if f.payload.get('event') == 'chat.message']
        assert len(messages) == 1 and messages[0]['text'] == text
        assert messages[0]['session_id'] == 'completed-test'
        front.llm_provider.chat_complete.assert_not_awaited()
    finally:
        await front.stop()
        await bus.close()


def test_original_inspection_packet_tracks_sources_questions_and_cited_ids(monkeypatch):
    from bigbrain.research_assessment import ModelReviewer
    from bigbrain.research import Passage, EvidenceLink
    import bigbrain.research_assessment as module
    original = module.review_view
    calls = []
    def assemble(state):
        calls.append(state.objective)
        return original(state)
    monkeypatch.setattr(module, 'review_view', assemble)
    state = evidence()
    reviewer = ModelReviewer(AsyncMock())
    view, _ = reviewer.evidence_view(state)
    state.claims[0].text = 'A narrower assertion requiring fresh semantic review'
    state.claims[0].basis = 'Previous long review explanation '*1000
    updated, _ = reviewer.evidence_view(state)
    assert len(calls) == 1 and updated['passages'] == view['passages']
    assert updated['claims'][0]['text'] == state.claims[0].text
    assert 'basis' not in updated['claims'][0]
    state.questions[0].text += ' with an additional requested aspect'
    reviewer.evidence_view(state)
    assert len(calls) == 2
    state.sources[0].content_sha256 = 'b'*64
    reviewer.evidence_view(state)
    assert len(calls) == 3
    state.passages.append(Passage(id='new',source_id='s0',text='A separately read original condition.'))
    state.claims[0].evidence.append(EvidenceLink(passage_id='new',relation='context'))
    reviewer.evidence_view(state)
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_real_authenticated_worker_dispatch_installs_collection_and_review_scopes(tmp_path):
    """Enter through MessageBus and BaseBrain, without a caller-installed scope."""
    from bigbrain.research_assessment import ModelReviewer
    auth = BusAuth()
    for name in ('morphable_ui', 'researcher'):
        auth.generate_token(name)
    bus = MessageBus(tmp_path/'logs', auth=auth)
    scopes = []
    class Inference:
        async def complete(self, prompt, **kwargs):
            scopes.append(current_conversation.get())
            if kwargs['tool_schema']['name'] == 'research_assessmentreport':
                payload = json.loads(prompt.split('\n', 1)[1])['evidence']
                from bigbrain.research import ResearchState
                state = ResearchState.model_validate({
                    'objective': payload['objective'], 'questions':payload['questions'],
                    'sources':[{'id':'s1','url':'https://docs.test/api','discovered_by':'query','status':'read'}],
                    'claims':[{**c,'basis':'Observed evidence'} for c in payload['claims']],
                    'passages':[{'id':p['id'],'source_id':'s1','text':p['text']} for p in payload['passages']]})
                return report(state).model_dump_json()
            state = json.loads(prompt.split('\n', 1)[1])['state']
            base = {'question_id':'q1','rationale':'Inspect the requested behavior'}
            if not state['sources']:
                return json.dumps({'tool':'search','query':'documented API', **base})
            if not state['passages']:
                return json.dumps({'tool':'open','source_id':'s1', **base})
            p = state['passages'][0]
            return json.dumps({'tool':'conclude','claims':[{'id':'c','question_id':'q1',
                'text':'The API returns an integer','basis':'Observed documentation',
                'evidence':[{'passage_id':p['id'],'relation':'supports'}]}], **base})
    search, reader = AsyncMock(), AsyncMock()
    search.search.return_value = [{'url':'https://docs.test/api'}]
    reader.read.return_value = {'url':'https://docs.test/api','sha256':'a'*64,
                               'text':'The documented API returns an integer.'}
    inference = Inference()
    worker = ResearcherBrain('researcher', bus, llm_provider=inference, search_provider=search,
        page_reader=reader, research_reviewer=ModelReviewer(inference))
    results, done = [], asyncio.Event()
    async def collect(frame):
        if frame.type == MessageType.RESULT:
            results.append(frame.payload)
            done.set()
    bus.subscribe('morphable_ui', collect)
    try:
        await worker.start()
        for session in ('session-one', 'session-two'):
            done.clear()
            await bus.send(BusMessage(type=MessageType.TASK, source='morphable_ui', target='researcher',
                payload={'type':'research','query':'Establish the documented API result','session_id':session}))
            await asyncio.wait_for(done.wait(), 3)
        assert len(results) == 2 and all(r['success'] for r in results)
        for session in ('session-one','session-two'):
            collection = [s for s in scopes if s == (session, 'research')]
            review = [s for s in scopes if s and s[0] == session and s[1].startswith('research-review:')]
            assert len(collection) == 3 and len(review) == 1
        assert current_conversation.get() is None
    finally:
        await worker.stop()
        await bus.close()


@pytest.mark.asyncio
async def test_direct_visit_reads_real_observations_without_search(monkeypatch):
    from bigbrain.research import Action, PageReader, ResearchRuntime, Limits
    from tests.test_research_acquisition import network, html_response
    network(monkeypatch, lambda request: html_response('<h1>Atlas v2</h1><p>The documented limit is 25 milliseconds.</p>'))
    class Policy:
        def __init__(self): self.steps = iter([
            Action(tool='visit',question_id='q1',url='https://public.test/v2',rationale='Read a known versioned URL'),
            Action(tool='conclude',question_id='q1',rationale='Return actual observations')])
        async def choose(self,*args): return next(self.steps)
    search=AsyncMock()
    runtime=ResearchRuntime(search,PageReader(),Policy(),AsyncMock(),limits=Limits(pages=1))
    state=await runtime.run('Read the Atlas version 2 limit')
    search.search.assert_not_awaited()
    assert runtime.counts['pages']==1 and runtime.counts['searches']==0
    assert state.sources[0].status=='read'
    assert any('25 milliseconds' in p.text for p in state.passages)


@pytest.mark.asyncio
async def test_direct_visit_keeps_private_network_guard():
    from bigbrain.research import Action, PageReader, ResearchRuntime
    class Policy:
        def __init__(self): self.steps=iter([
            Action(tool='visit',question_id='q1',url='http://127.0.0.1/private',rationale='Propose a denied address'),
            Action(tool='conclude',question_id='q1',rationale='Report unavailable evidence')])
        async def choose(self,*args): return next(self.steps)
    runtime=ResearchRuntime(AsyncMock(),PageReader(),Policy(),AsyncMock())
    state=await runtime.run('A denied proposal')
    assert not state.passages and state.sources[0].status=='inaccessible'
    assert state.observations[0].status=='error'


@pytest.mark.asyncio
async def test_grouped_visits_reserve_pages_before_any_read():
    from bigbrain.research import Action, CollectionRequest, ResearchRuntime, Limits
    action=Action(tool='batch',question_id='q1',rationale='Read two independent versions',requests=[
        CollectionRequest(tool='visit',question_id='q1',url=f'https://docs.test/v{i}',rationale='Read the selected version')
        for i in (1,2)])
    reader=AsyncMock()
    runtime=ResearchRuntime(AsyncMock(),reader,AsyncMock(),AsyncMock(),limits=Limits(pages=1))
    from bigbrain.research import ResearchState, Question, ResearchActionRejected
    state=ResearchState(objective='versions',questions=[Question(id='q1',text='versions',evidence_needed='versioned text')])
    with pytest.raises(ResearchActionRejected,match='budget'):
        await runtime.execute(state,action,runtime.counts,set(),0)
    reader.read.assert_not_awaited()
    assert not state.sources
