"""Compact direct working sets against the manually annotated acquisition corpus."""
from unittest.mock import AsyncMock

import pytest

from bigbrain.research import Action, Limits, PageReader, ResearchRuntime
from bigbrain.research_acquisition import artifact
from bigbrain.research_direct_context import ObservedPassages, encoded
from tests.research_efficiency_benchmark import FixtureFetcher, FixtureSearch, corpus
from tests.test_research_acquisition import Policy

MANIFEST = corpus.load()


class RenderedCorpus:
    async def render(self, response, fetcher, progress):
        document = MANIFEST['documents']['js_shell']
        body = corpus.document_html(document, rendered=True).encode()
        return {'url': response.url, 'body': body, 'artifact': artifact(body, name='direct-rendered-corpus.html'),
                'requests': [], 'restrictions': [], 'limitations': [], 'browser_version': 'frozen-fixture'}


@pytest.mark.asyncio
@pytest.mark.parametrize('case', MANIFEST['cases'], ids=lambda case: case['id'])
async def test_compact_working_set_retains_required_passages_and_qualifications(case):
    args = dict(question_id='q1', rationale='Read the manually annotated corpus documents')
    reads = [dict(tool='open', source_id=f's{i+1}', **args) for i in range(len(case['documents']))]
    policy = Policy(Action(tool='search', query=case['question'], **args),
        Action(tool='batch', requests=reads, **args),
        *([Action(tool='open', source_id='s1', mode='browser', **args)] if case['id'] == 'javascript' else []),
        Action(tool='conclude', **args))
    reader = PageReader(fetcher=FixtureFetcher(MANIFEST), browser=RenderedCorpus())
    runtime = ResearchRuntime(FixtureSearch(MANIFEST, case), reader, policy, AsyncMock(), limits=Limits(pages=4))
    state = await runtime.run(case['question'])
    receipts = ObservedPassages()
    receipts.ingest(state)
    packet = receipts.packet(state)
    assert len(encoded(packet)) <= 12000
    passages = {}
    for item in packet['passages']:
        url = next(s.url for s in state.sources if s.id == item['source_id'])
        document = next(d for d in case['documents'] if MANIFEST['documents'][d]['url'] == url)
        passages.setdefault(document, []).append(item['text'])
    metrics = corpus.score(case, MANIFEST, {'passages': passages,
        'observed_views': {'js_shell': 'rendered'} if case['id'] == 'javascript' else {}})
    assert not metrics['critical_omissions'], metrics
    if case['id'] == 'blocked':
        assert not packet['passages']
        assert any(source['status'] == 'inaccessible' for source in packet['sources'])
