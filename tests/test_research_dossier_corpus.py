"""Frozen corpus passage and qualification coverage at dossier construction."""
import json
from unittest.mock import AsyncMock

import pytest

from bigbrain.research import Action, Limits, ResearchRuntime
from bigbrain.research_acquisition import PageReader, artifact
from bigbrain.research_dossier import EvidenceDossier
from tests.research_efficiency_benchmark import FixtureFetcher, FixtureSearch, corpus

MANIFEST = corpus.load()


@pytest.mark.asyncio
@pytest.mark.parametrize('case', MANIFEST['cases'], ids=lambda case: case['id'])
async def test_frozen_dossier_retains_critical_corpus_passages(case):
    from tests.test_research_acquisition import Policy
    q = {'question_id': 'q1', 'rationale': 'Inspect the manually audited corpus evidence'}
    reads = [{'tool': 'open', 'source_id': f's{i+1}', **q} for i in range(len(case['documents']))]
    policy = Policy(Action(tool='search', query=case['question'], **q),
                    Action(tool='batch', requests=reads, **q),
                    *([Action(tool='open', source_id='s1', mode='browser', **q)] if case['id'] == 'javascript' else []),
                    Action(tool='conclude', **q))
    class RenderedCorpus:
        async def render(self, response, fetcher, progress):
            document = MANIFEST['documents']['js_shell']
            body = corpus.document_html(document, rendered=True).encode()
            return {'url': response.url, 'body': body, 'artifact': artifact(body, name='rendered-corpus.html'),
                    'requests': [], 'restrictions': [], 'limitations': [], 'browser_version': 'frozen-corpus-fixture'}
    reader = PageReader(fetcher=FixtureFetcher(MANIFEST), browser=RenderedCorpus())
    engine = ResearchRuntime(FixtureSearch(MANIFEST, case), reader, policy, AsyncMock(), limits=Limits(pages=4))
    state = await engine.run(case['question'])
    dossier, _ = EvidenceDossier.freeze(state, byte_limit=6000)
    packet = dossier.view()
    passages = {}
    for item in packet['passages']:
        source_id = packet['passage_contexts'][item['context_ref']]['source_id']
        url = next(s.url for s in state.sources if s.id == source_id)
        document = next(d for d in case['documents'] if MANIFEST['documents'][d]['url'] == url)
        passages.setdefault(document, []).append(item['text'])
    metrics = corpus.score(case, MANIFEST, {'passages': passages,
        'observed_views': {d: 'rendered' for d in passages if d == 'js_shell'}})
    assert not metrics['critical_omissions'], metrics
    assert len(dossier.payload) <= 6000
    assert EvidenceDossier.restore(json.loads(json.dumps(dossier.checkpoint()))) == dossier
    if case['id'] == 'blocked':
        assert not packet['passages']
        assert packet['access_failures']
