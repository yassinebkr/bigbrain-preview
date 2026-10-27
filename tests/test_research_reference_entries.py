"""Reference-entry boundaries using the captured SQLite envelope failure."""
import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock
import zlib

import pytest

from bigbrain.research import Action, Limits, PageReader, ResearchRuntime
from bigbrain.research_acquisition import ReadFailure, Response, artifact
from bigbrain.research_context import groups
from bigbrain.research_dossier import EvidenceDossier
from bigbrain.research_extraction import extract_html
from tests.test_research_acquisition import Policy


def captured_pragma():
    record = json.loads((Path(__file__).parent / 'fixtures/research_sqlite_pragma_capture.json').read_text())
    body = zlib.decompress(base64.b64decode(record['body']))
    assert hashlib.sha256(body).hexdigest() == 'af75d7d7ab00c29e6eea98618cb1259a3919c308af60a6173215bf9798706034'
    return record['url'], body


def test_nonstandard_headings_and_named_entries_retain_qualifications():
    html = ('<body><h1>Reference</h1><a name="first"></a><h _id="first">First API</h>'
            '<p>Returns a value.</p><p>Warning: only valid for positive inputs.</p>'
            '<a name="second"></a><h _id="second">Second API</h><p>Other behavior.</p></body>')
    document = extract_html(html, 'https://reference.test/api')
    sections = groups(document['original_blocks'], 'a'*64)
    first = next(g for g in sections if g['context'][-1] == 'First API')
    assert [b['text'] for b in first['blocks']] == [
        'First API', 'Returns a value.', 'Warning: only valid for positive inputs.']
    assert all(b['section_id'] == 'first' for b in first['blocks'])
    plain = extract_html('<body><a name="one"></a><p>First condition.</p>'
                         '<a name="two"></a><p>Second condition.</p></body>', 'https://reference.test/plain')
    assert len(groups(plain['original_blocks'], 'b'*64)) == 2


class CapturedFetcher:
    async def fetch(self, url):
        expected, body = captured_pragma()
        assert url == expected
        return Response(url, 200, body, {'content-type':'text/html'}, 'utf-8',
                        artifact(body, name='captured-pragma.html', media_type='text/html'), ())


@pytest.mark.asyncio
async def test_exact_visit_preserves_fragment_and_freezes_qualified_entry():
    url, _ = captured_pragma()
    args = dict(question_id='q1', rationale='Read the journal-mode definition')
    visit = Action(tool='visit', url=url + '#pragma_journal_mode', focus='DELETE', **args)
    reader = PageReader(fetcher=CapturedFetcher())
    runtime = ResearchRuntime(AsyncMock(), reader, Policy(visit, Action(tool='conclude', **args)),
                             AsyncMock(), limits=Limits(seconds=120))
    state = await runtime.run('Compare DELETE and WAL journaling and retain important qualifications')
    assert len(state.sources) == 1 and state.sources[0].status == 'read'
    assert len(state.passages) < 40
    assert all('PRAGMA journal_mode' in p.context for p in state.passages)
    text = '\n'.join(p.text for p in state.passages)
    assert 'rollback journal is deleted' in text
    assert 'corrupt' in text.lower()
    assert 'PRAGMA secure_delete' not in text
    dossier, _ = EvidenceDossier.freeze_bounded(state)
    assert len(dossier.payload) <= 24000
    assert all(any(p.text in b['text'] for b in dossier.view()['passages']) for p in state.passages)
    assert Action.model_validate(state.observations[0].action.model_dump()).url.endswith('#pragma_journal_mode')


@pytest.mark.asyncio
async def test_unobserved_fragment_fails_explicitly():
    reader = PageReader(fetcher=CapturedFetcher())
    with pytest.raises(ReadFailure, match='fragment was not observed'):
        await reader.read(captured_pragma()[0], fragment='invented-entry')


def test_fragment_identity_is_distinct_from_page_and_literal_focus():
    args = dict(tool='visit', question_id='q1', rationale='Read a known reference entry', focus='DELETE')
    first = Action(url='https://source.test/reference#first', **args)
    second = Action(url='https://source.test/reference#second', **args)
    assert ResearchRuntime.action_key(first) != ResearchRuntime.action_key(second)
