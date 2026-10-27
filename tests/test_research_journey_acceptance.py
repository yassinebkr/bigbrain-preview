"""Authenticated worker journeys over frozen HTTP and rendered observations."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bigbrain.brains.researcher import ResearcherBrain
from bigbrain.bus.auth import BusAuth
from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.research import Action, Limits, PageReader, ResearchRuntime
from bigbrain.research_acquisition import ReadFailure, artifact
from tests.test_research_acquisition import network, html_response, Policy, act

FACT = 'Measured value: 7 units. Applies only indoors.'
SHELL = '<main></main><script src="/app.js"></script>'


class FixtureRenderer:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    async def render(self, response, fetcher, progress):
        self.calls += 1
        if self.fail:
            raise ReadFailure('render_failed', 'Frozen renderer failure')
        body = ('<main><p>' + FACT + '</p></main>').encode()
        return {'url':response.url, 'body':body,
            'artifact':artifact(body, name='fixture-rendered.html', media_type='text/html'),
            'requests':[], 'restrictions':[], 'limitations':[], 'browser_version':'offline-fixture'}


class FixtureInference:
    """Script the two decisions; production runtime owns all acquisitions."""
    def __init__(self, url, *, incomplete=False, invented=False):
        self.url, self.incomplete, self.invented = url, incomplete, invented
        self.calls = 0
        from tests.test_research_workflow import StageInference
        self.stages = StageInference(fact=FACT, url=url, invented=invented)

    async def complete(self, prompt, **kwargs):
        self.calls += 1
        if kwargs.get('tool_schema', {}).get('name') in {
                'research_collectiondecision', 'research_draft', 'research_control'}:
            return await self.stages.complete(prompt, **kwargs)
        state = json.loads(prompt.split('\n', 1)[1])['state']
        if not state['sources']:
            return act('visit', url=self.url).model_dump_json()
        matches = [p for p in state['passages'] if FACT in p['text']]
        claims = []
        if matches:
            claims = [{'id':'c1', 'question_id':'q1', 'text':FACT, 'basis':'Observed fixture reference',
                'evidence':[{'passage_id':'invented' if self.invented else matches[0]['id'], 'relation':'supports'}]}]
        return act('conclude', claims=claims,
            remaining_gaps=['The requested reference remains unread'] if not matches else []).model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['static', 'javascript', 'chromium', 'blocked', 'authentication', 'rate_limit',
                                  'private', 'render_disabled', 'render_failure', 'invented_citation'])
async def test_authenticated_documentary_journey(monkeypatch, tmp_path, case):
    code = {'blocked':403, 'authentication':401, 'rate_limit':429}.get(case, 200)
    dynamic = case in {'javascript', 'chromium', 'render_disabled', 'render_failure'}
    def respond(request):
        if case == 'chromium' and request.url.path == '/app.js':
            import httpx
            return httpx.Response(200, headers={'content-type':'application/javascript'},
                text='document.querySelector("main").textContent = ' + json.dumps(FACT))
        return html_response(SHELL if dynamic else '<p>'+FACT+'</p>', code)
    calls = network(monkeypatch, respond)
    if case == 'render_disabled':
        monkeypatch.setenv('BIGBRAIN_RESEARCH_BROWSER', '0')
    renderer = FixtureRenderer(fail=case == 'render_failure')
    if case == 'chromium':
        api = pytest.importorskip('playwright.async_api')
        async with api.async_playwright() as pw:
            if not Path(pw.chromium.executable_path).is_file():
                pytest.skip('Playwright Chromium not installed')
        renderer = None
    inference = FixtureInference('https://private.test/reference' if case == 'private' else 'https://public.test/reference',
        invented=case == 'invented_citation')
    auth = BusAuth()
    for identity in ('morphable_ui', 'researcher'):
        auth.generate_token(identity)
    bus = MessageBus(tmp_path/'logs', auth=auth)
    worker = ResearcherBrain('researcher', bus, llm_provider=inference,
        search_provider=AsyncMock(), page_reader=PageReader(browser=renderer))
    done, results, finished = asyncio.Event(), [], []
    async def observe(frame):
        if frame.type == MessageType.RESULT:
            results.append(frame.payload)
            done.set()
        if frame.payload.get('stage') == 'research_finished':
            finished.append(frame.payload['research'])
    bus.subscribe('morphable_ui', observe)
    try:
        await worker.start()
        await bus.send(BusMessage(type=MessageType.TASK, source='morphable_ui', target='researcher',
            payload={'type':'research', 'query':'Read the measured value and its operating restriction',
                     'session_id':'journey-' + case}), require_target=True)
        await asyncio.wait_for(done.wait(), 8)
        assert len(results) == len(finished) == 1
        data = results[0].get('data', results[0])
        evidence = data['evidence']
        assert evidence['delivery_mode'] == 'reviewed'
        assert finished[0]['counts']['pages'] == 1
        if case in {'static', 'javascript', 'chromium'}:
            assert data['success'] and evidence['claims'][0]['text'] == FACT
            assert evidence['claims'][0]['status'] == 'supported'
            assert inference.calls == 4
            assert finished[0]['counts']['browsers'] == int(dynamic)
            passage = next(p for p in evidence['passages'] if FACT in p['text'])
            assert passage['observation_sha256'] == evidence['sources'][0]['content_sha256']
            if dynamic:
                assert evidence['sources'][0]['acquisition']['upgrade']['reason'] == 'requires_browser'
        else:
            assert not data['success'] and evidence['status'] == 'partial'
            assert not evidence['assessments'] or not evidence['claims']
            assert all(claim['status'] == 'unverified' for claim in evidence['claims'])
            assert inference.calls <= 4
        if case in {'blocked', 'authentication', 'rate_limit', 'private'}:
            assert renderer.calls == 0
        if case == 'private':
            assert not calls
    finally:
        await worker.stop()
        await bus.close()


@pytest.mark.asyncio
async def test_grouped_http_slots_preserve_separate_render_allowance(monkeypatch):
    network(monkeypatch, lambda request: html_response(SHELL))
    renderer = FixtureRenderer()
    runtime = ResearchRuntime(AsyncMock(), PageReader(browser=renderer), AsyncMock(), AsyncMock(),
        limits=Limits(pages=4, browsers=2))
    from bigbrain.research import Question, ResearchState
    runtime.state = state = ResearchState(objective='Measured value',
        questions=[Question(id='q1', text='Measured value', evidence_needed='Value and conditions')])
    import time
    runtime.started = time.monotonic()
    action = act('batch', requests=[{'tool':'visit', 'question_id':'q1', 'rationale':'Read reference',
        'url':f'https://public.test/{i}'} for i in range(4)])
    observation = await runtime.execute(state, action, runtime.counts, set(), 0)
    assert runtime.counts == {'pages':4, 'browsers':2, 'reviews':0, 'searches':0}
    assert renderer.calls == 2
    assert sum(s.status == 'read' for s in state.sources) == 2
    assert sum(item['status'] == 'error' for item in observation.data['items']) == 2
    assert all(FACT in p.text for p in state.passages)


@pytest.mark.asyncio
async def test_upgrade_deadline_settles_and_closes_renderer(monkeypatch):
    network(monkeypatch, lambda request: html_response(SHELL))
    closed = asyncio.Event()
    class WaitingRenderer:
        async def render(self, *args, **kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                closed.set()
    progress = AsyncMock()
    runtime = ResearchRuntime(AsyncMock(), PageReader(browser=WaitingRenderer()),
        Policy(act('visit', url='https://public.test/reference')), progress,
        limits=Limits(seconds=.2, pages=1, browsers=1))
    state = await runtime.run('Measured value')
    assert closed.is_set() and state.status == 'partial'
    assert state.diagnostic['code'] == 'time_budget_exhausted'
    assert not state.claims
    assert progress.call_args.args[0]['stage'] == 'research_finished'


@pytest.mark.asyncio
async def test_retained_http_observation_can_render_after_http_quota(monkeypatch):
    calls = network(monkeypatch, lambda request: html_response(SHELL))
    renderer = FixtureRenderer()
    reader = PageReader(browser=renderer)
    with pytest.raises(ReadFailure) as failed:
        await reader.read('https://public.test/reference')
    from bigbrain.research import Question, ResearchState, Source, research_tools
    import time
    state = ResearchState(objective='Measured value', questions=[Question(id='q1', text='Measured value', evidence_needed='Value and conditions')],
        sources=[Source(id='s1', url='https://public.test/reference', discovered_by='query', acquisition=failed.value.record)])
    runtime = ResearchRuntime(AsyncMock(), reader, AsyncMock(), AsyncMock(), limits=Limits(pages=1, browsers=1))
    runtime.state, runtime.started = state, time.monotonic()
    runtime.counts['pages'] = 1
    tools = research_tools(state, {'actions':2, 'pages':0, 'browsers':1})
    assert 'open' in tools and 'conclude' not in tools
    await runtime.execute(state, act('open', source_id='s1', mode='browser'), runtime.counts, set(), 0)
    assert runtime.counts['pages'] == runtime.counts['browsers'] == 1
    assert len(calls) == renderer.calls == 1
    assert state.sources[0].status == 'read' and FACT in state.passages[0].text
