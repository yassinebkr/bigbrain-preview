"""Campaign inputs expose the source identity needed to exercise blocked access."""
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bigbrain.research import Action, Limits, PageReader, ResearchRuntime
from tests.research_efficiency_benchmark import FixtureFetcher, corpus
from tests.test_research_acquisition import Policy

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = json.loads((ROOT / 'docs/RESEARCH_GATE4_CAMPAIGN.json').read_text())
MANIFEST = corpus.load()
BLOCKED_CASES = [case for case in CAMPAIGN['cases'] if case['family'] == 'blocked_access']


@pytest.mark.parametrize('case', BLOCKED_CASES, ids=lambda case: case['id'])
def test_blocked_report_identity_is_visible_in_the_actual_request(case):
    report = MANIFEST['documents'][case['documents'][0]]
    assert report['url'] in case['question']
    assert report['http_status'] == 403
    assert '98' not in case['question']


@pytest.mark.asyncio
@pytest.mark.parametrize('case', BLOCKED_CASES, ids=lambda case: case['id'])
async def test_explicit_report_visit_preserves_the_access_failure(case):
    report = MANIFEST['documents'][case['documents'][0]]
    request = dict(question_id='q1', rationale='Inspect the explicitly supplied report')
    policy = Policy(Action(tool='visit', url=report['url'], **request),
                    Action(tool='conclude', remaining_gaps=['Report contents remain unread'], **request))
    reader = PageReader(fetcher=FixtureFetcher(MANIFEST))
    runtime = ResearchRuntime(AsyncMock(), reader, policy, AsyncMock(), limits=Limits(pages=1))
    state = await runtime.run(case['question'])
    assert state.observations
    assert state.observations[0].action.url == report['url']
    assert state.observations[0].status == 'error'
    assert '403' in json.dumps(state.observations[0].data)
    assert not state.passages
    assert not state.claims
