"""Replay failed SQLite feedback and native source-assessment obligations."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from bigbrain.research import Action, Observation, Question, ResearchState, Source
from bigbrain.research_direct import DirectDecision, DirectFinish, run_direct
from bigbrain.research_direct_context import ObservedPassages, encoded
from bigbrain.research_direct_model import DirectModelAdapter
from tests.test_research_direct_model import Provider
from tests.test_research_direct_result import candidate


def replay():
    fixture = json.loads((Path(__file__).parent/'fixtures/research_direct_sqlite_feedback_20261027.json').read_text())
    source = Source(**fixture['source'], acquisition={'navigation': fixture['navigation']})
    state = ResearchState(objective='Compare SQLite reader/writer locking',
        questions=[Question(id='q1', text='Establish rollback locking', evidence_needed='Read the reference')],
        sources=[source], observations=[Observation(index=0, action=Action(**fixture['action']),
            status='error', data={'error': fixture['error']})])
    store = ObservedPassages()
    store.ingest(state)
    return fixture, state, store


def test_exact_sqlite_failure_exposes_error_and_capture_bound_section_alternatives():
    fixture, state, store = replay()
    packet = store.packet(state)
    assert len(encoded(packet)) <= 12000
    assert packet['recent_actions'][0]['focus'] == 'Only one process can have a RESERVED lock'
    assert packet['recent_actions'][0]['error'] == fixture['error']
    assert any('3.0 Locking' in group['headings'] for group in packet['navigation'])
    assert all(group['capture_sha256'] == state.sources[0].content_sha256 for group in packet['navigation'])


def test_section_navigation_supports_local_paging_and_bounded_packets():
    _, state, store = replay()
    first = store.packet(state)
    assert first['navigation']
    second = store.packet(state, catalog_source_id='s3', catalog_offset=1)
    assert second['navigation'][0]['group_id'] == first['navigation'][1]['group_id']
    assert len(encoded(second)) <= 12000
    with pytest.raises(ValueError, match='observed section catalog'):
        store.packet(state, catalog_source_id='s3', catalog_offset=1000)


def test_generation_exposes_only_observed_section_source_and_hash_combinations():
    from tests.test_research_direct_journey import runtime
    _, state, store = replay()
    engine, _ = runtime()
    engine.state = state
    adapter = DirectModelAdapter(engine, Provider())
    adapter.prepare({'working_set': store.packet(state)})
    schema = adapter.actor.protocol(DirectDecision)['tool_schema']['parameters']
    shapes = schema['$defs']['CollectionRequest']['anyOf']
    groups = [shape for shape in shapes if 'group_ids' in shape['properties']]
    assert groups
    for shape in groups:
        fields = shape['properties']
        assert fields['source_id']['const'] == 's3'
        assert fields['observation_sha256']['const'] == state.sources[0].content_sha256
        assert set(fields['group_ids']['items']['enum']) <= {g['group_id'] for g in store.packet(state)['navigation']}


def test_same_section_with_distinct_retrieval_intent_has_a_distinct_action_identity():
    from bigbrain.research import ResearchRuntime
    first = Action(tool='open', question_id='q1', source_id='s2', rationale='Inspect section',
                   group_ids=['observed-section'], observation_sha256='a' * 64,
                   reading_question='What happens to the stored values?')
    second = first.model_copy(update={'reading_question': 'Can the changes be rolled back?'})
    assert ResearchRuntime.action_key(first) != ResearchRuntime.action_key(second)
    assert ResearchRuntime.action_key(first) == ResearchRuntime.action_key(first.model_copy())


@pytest.mark.parametrize('sources', [None, []])
def test_native_generation_rejects_the_old_null_or_empty_source_array(sources):
    from tests.test_research_direct_journey import runtime
    state, store, proposed = candidate()
    engine, _ = runtime()
    engine.state = state
    adapter = DirectModelAdapter(engine, Provider())
    adapter.prepare({'working_set': store.packet(state)})
    schema = adapter.actor.protocol(DirectFinish)['tool_schema']['parameters']
    payload = {'conclusion': proposed.model_dump(mode='json')}
    payload['conclusion']['sources'] = sources
    assert list(Draft202012Validator(schema).iter_errors(payload))
    payload['conclusion'].pop('sources')
    assert list(Draft202012Validator(schema).iter_errors(payload))


def test_unknown_source_suitability_remains_a_legal_model_judgment():
    from tests.test_research_direct_journey import runtime
    state, store, proposed = candidate()
    proposed.sources[0].suitability = 'unknown'
    proposed.sources[0].kind = 'unknown'
    engine, _ = runtime()
    engine.state = state
    adapter = DirectModelAdapter(engine, Provider())
    adapter.prepare({'working_set': store.packet(state)})
    schema = adapter.actor.protocol(DirectFinish)['tool_schema']['parameters']
    payload = proposed.model_dump(mode='json')
    def wire(value):
        if isinstance(value, list):
            return [wire(item) for item in value]
        if isinstance(value, dict):
            return {key: wire(item) for key, item in value.items() if key != 'schema_version'}
        return value
    payload = wire(payload)
    for source in payload['sources']:
        source['source_reference'] = source.pop('provenance_passage_id')
        source.pop('source_id')
        source.pop('provenance_quote', None)
    for finding in payload['findings']:
        for citation in finding['citations']:
            citation.pop('receipt_id')
            citation.pop('quote')
    Draft202012Validator(schema).validate({'conclusion': payload})


@pytest.mark.asyncio
async def test_semantically_rejected_candidate_has_a_first_class_artifact():
    from tests.test_research_direct_journey import runtime, ScriptedAdapter
    from bigbrain.research_direct import DirectReply
    engine, _ = runtime()
    class IncompleteSources(ScriptedAdapter):
        async def infer(self, *args):
            reply = await super().infer(*args)
            if len(self.calls) == 2:
                reply.value['conclusion']['sources'] = []
            return DirectReply(reply.value)
    state = await run_direct(engine, IncompleteSources())
    assert state.execution_outcome == 'failed'
    artifact = state.diagnostic['candidate_artifact']
    assert artifact == state.usage['direct_candidates'][-1]['artifact']
    assert artifact['sha256'] and artifact['locator']


def test_captured_postgresql_pages_retain_explanations_beyond_navigation():
    from bigbrain.research_context import select
    records = json.loads((Path(__file__).parent / 'fixtures/research_direct_postgresql_20261028.json').read_text())
    selected = {}
    for record in records:
        blocks, metadata = select('Comparer DELETE TRUNCATE DROP TABLE données structure transaction identité',
            record['blocks'], 'a' * 64, coverage=True)
        selected[record['url']] = '\n'.join(b['text'] for b in blocks)
        assert metadata['characters_selected'] <= 6000
    truncate = next(text for url, text in selected.items() if 'sql-truncate' in url)
    drop = next(text for url, text in selected.items() if 'sql-droptable' in url)
    assert 'TRUNCATE is transaction-safe' in truncate
    assert 'currval()' in truncate
    assert 'DROP TABLE removes tables from the database.' in drop


def test_captured_document_title_focus_reaches_the_description_across_sibling_headings():
    from bigbrain.research_extraction import window
    records = json.loads((Path(__file__).parent / 'fixtures/research_direct_postgresql_20261028.json').read_text())
    record = next(r for r in records if 'sql-delete' in r['url'])
    blocks, _ = window(record['blocks'], 'DELETE', document_title='PostgreSQL Documentation: DELETE')
    text = '\n'.join(b['text'] for b in blocks)
    assert 'DELETE deletes rows that satisfy the WHERE clause' in text
    assert blocks[0]['text'] == 'DELETE'
    assert sum(len(b['text']) for b in blocks) <= 12000


def test_secondary_reference_heading_keeps_its_own_entry_boundary():
    from bigbrain.research_extraction import window
    blocks = [
        {'id': 'b1', 'kind': 'h2', 'text': 'First entry', 'context': ['First entry']},
        {'id': 'b2', 'kind': 'p', 'text': 'The first entry description.', 'context': ['First entry']},
        {'id': 'b3', 'kind': 'h2', 'text': 'Other entry', 'context': ['Other entry']},
        {'id': 'b4', 'kind': 'p', 'text': 'The other entry description.', 'context': ['Other entry']},
    ]
    selected, _ = window(blocks, 'First entry', document_title='Collected reference entries')
    assert [b['id'] for b in selected] == ['b1', 'b2']
    selected, clipped = window(blocks, 'First entry', limit=20, document_title='First entry manual')
    assert sum(len(b['text']) for b in selected) <= 20
    assert clipped


def test_source_language_intent_retains_identity_and_transaction_qualifications():
    from bigbrain.research import Passage
    from bigbrain.research_context import select
    records = json.loads((Path(__file__).parent / 'fixtures/research_direct_postgresql_20261028.json').read_text())
    intent = 'DELETE TRUNCATE DROP TABLE rows structure transaction rollback RESTART IDENTITY CONTINUE IDENTITY sequences currval'
    state = ResearchState(objective='Comparer les données, la structure, les transactions et les séquences d’identité',
        questions=[Question(id='q1', text='Comparer les effets et les limites', evidence_needed='Documentation officielle')])
    for index, record in enumerate(records):
        sid, digest = f's{index+1}', str(index+1) * 64
        state.sources.append(Source(id=sid, url=record['url'], title='Official reference',
            status='read', content_sha256=digest, discovered_by='captured-regression'))
        blocks, _ = select(intent, record['blocks'], digest, coverage=True)
        state.passages.extend(Passage(id=f'{sid}:p{n}', source_id=sid, text=b['text'],
            kind=b['kind'], context=b['context'], observation_sha256=digest) for n,b in enumerate(blocks))
        state.observations.append(Observation(index=index, status='ok', data={},
            action=Action(tool='open', source_id=sid, question_id='q1', rationale='Read reference', reading_question=intent)))
    store = ObservedPassages()
    store.ingest(state)
    packet = store.packet(state)
    texts = '\n'.join(p['text'] for p in packet['passages'])
    assert len(encoded(packet)) <= 12000
    assert 'TRUNCATE is transaction-safe' in texts
    assert 'CONTINUE IDENTITY' in texts
    assert 'currval()' in texts
    assert {p['source_id'] for p in packet['passages']} == {'s1', 's2', 's3'}


def test_continuation_packet_exposes_remaining_requirements_and_prior_findings():
    state, store, proposed = candidate()
    from bigbrain.research import Claim
    state.previous_attempts = [{'attempt_id': 'previous', 'status': 'partial'}]
    state.question_coverage = [{'question_id': 'q1', 'status': 'incomplete',
        'missing_evidence': ['Inspect the transactional exception.']}]
    state.original_request_coverage = {'complete': False, 'gaps': ['Transactional exception remains unread.']}
    state.claims = [Claim(id='retained', question_id='q1', text='Previously established observation.',
                          status='supported', basis='Observed reference')]
    packet = store.packet(state)
    assert packet['remaining_requirements'][0]['missing_evidence'] == ['Inspect the transactional exception.']
    assert packet['original_request_gaps'] == ['Transactional exception remains unread.']
    assert packet['prior_findings'][0]['id'] == 'retained'
    assert len(encoded(packet)) <= 12000


def test_captured_postgresql_continuation_keeps_quotes_and_adjacent_rollback_scope():
    from bigbrain.research import Passage, Claim
    records = json.loads((Path(__file__).parent / 'fixtures/research_direct_postgresql_20261028.json').read_text())
    state = ResearchState(objective='Comparer données, structure, transactions et séquences',
        questions=[Question(id='q1', text='Comparer les effets et limites',
                            evidence_needed='Documentation officielle')])
    prefixes = ('When RESTART IDENTITY is specified,', 'DROP TABLE removes tables',
                'DELETE deletes rows')
    for index, record in enumerate(records):
        sid, digest = f's{index+1}', str(index+1) * 64
        state.sources.append(Source(id=sid, url=record['url'], title='Official reference',
            status='read', content_sha256=digest, discovered_by='captured-regression'))
        state.passages.extend(Passage(id=f'{sid}:p{n}', source_id=sid, text=b['text'],
            kind=b['kind'], context=b['context'], block_id=b['id'], observation_sha256=digest)
            for n,b in enumerate(record['blocks']))
    state.sources.extend(Source(id=f'found-{n}', url=f'https://docs.test/reference/{n}',
                                discovered_by='fixture') for n in range(8))
    store = ObservedPassages()
    store.ingest(state)
    citations = []
    for prefix in prefixes:
        passage = next(p for p in state.passages if p.text.startswith(prefix))
        receipt = store.get(passage.id)
        citations.append(store.citation(passage.id, receipt.capture_sha256,
                                        receipt.text, receipt_id=receipt.identity))
    state.usage['direct_result'] = {'findings': [{'citations': citations}]}
    state.claims = [Claim(id='prior', question_id='q1', text='Previously established effects.',
                          status='supported', basis='Archived quotations')]
    packet = store.packet(state)
    assert len(encoded(packet)) <= 12000
    for citation in citations:
        receipt = store.get(citation['passage_id'])
        assert any(p['source_id'] == receipt.source_id and citation['quote'] in p['text']
                   for p in packet['passages'])
    assert any('TRUNCATE is transaction-safe with respect to the data' in p['text']
               for p in packet['passages'])


@pytest.mark.asyncio
async def test_native_adapter_rejects_a_foreign_passage_handle():
    from tests.test_research_direct_journey import runtime, conclusion
    class ForeignHandle(Provider):
        async def complete(self, prompt, **kwargs):
            raw = json.loads(await super().complete(prompt, **kwargs))
            if raw.get('conclusion'):
                raw['conclusion']['findings'][0]['citations'][0]['passage_id'] = 'foreign:p1'
            return json.dumps(raw)
    engine, _ = runtime()
    state = await run_direct(engine, DirectModelAdapter(engine, ForeignHandle()))
    assert state.execution_outcome == 'failed'
    assert 'Citation handle' in state.diagnostic['message']
