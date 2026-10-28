"""Direct-loop working sets preserve immutable evidence across prompt eviction."""
import pytest

from bigbrain.research import Passage, Question, ResearchState, Source
from bigbrain.research_direct_context import ObservedPassages, WorkingContextOverflow, encoded


def observed(texts=('The documented limit is seven. Applies indoors only.',), digest='a' * 64):
    return ResearchState(objective='What is the limit and its qualification?',
        questions=[Question(id='q1', text='Establish the qualified limit', evidence_needed='Read the reference')],
        sources=[Source(id='s1', url='https://docs.test/reference', discovered_by='fixture',
                        status='read', content_sha256=digest, truncated=True)],
        passages=[Passage(id=f's1:p{i}', source_id='s1', text=text, context=['Limits'],
                          observation_sha256=digest, block_id=f'b{i}') for i, text in enumerate(texts)])


def test_working_set_eviction_retains_receipts_and_separates_semantic_judgment():
    state = observed(('The documented limit is seven.', 'Applies indoors only.'))
    store = ObservedPassages()
    store.ingest(state)
    receipt = store.get('s1:p0')
    packet = store.packet(state, preferred=['s1:p1'], byte_limit=1100)
    assert len(encoded(packet)) <= 1100
    assert len(store.receipts) == 2
    citation = store.citation('s1:p0', 'a' * 64, receipt.text, receipt_id=receipt.identity)
    assert citation['citation_integrity'] == 'verified'
    assert citation['semantic_assessment'] == 'model_judgment'
    assert 'supported' not in citation.values()


def test_refreshed_capture_invalidates_old_citation_and_retains_archive():
    store = ObservedPassages()
    store.ingest(observed())
    old = store.get('s1:p0')
    store.ingest(observed(('The documented limit is nine.',), digest='b' * 64))
    assert old.identity in store.receipts
    with pytest.raises(ValueError, match='stale'):
        store.citation(old.passage_id, old.capture_sha256, old.text, receipt_id=old.identity)


def test_rewriting_a_capture_receipt_is_rejected_atomically():
    store = ObservedPassages()
    store.ingest(observed())
    original = store.get('s1:p0')
    with pytest.raises(ValueError, match='rewritten'):
        store.ingest(observed(('A replacement assertion.',)))
    assert store.get('s1:p0') == original


@pytest.mark.parametrize('quote', ['The documented limit is eight.', 'seven indoors', ''])
def test_unobserved_or_rewritten_quotes_fail(quote):
    store = ObservedPassages()
    store.ingest(observed())
    receipt = store.get('s1:p0')
    with pytest.raises(ValueError):
        store.citation(receipt.passage_id, receipt.capture_sha256, quote, receipt_id=receipt.identity)


def test_discovered_snippets_and_mismatched_capture_passages_never_become_receipts():
    state = observed()
    state.sources[0].status = 'discovered'
    state.sources[0].snippet = 'Invented measured efficiency: 98 percent.'
    store = ObservedPassages()
    store.ingest(state)
    assert not store.current
    state.sources[0].status = 'read'
    state.passages[0].observation_sha256 = 'b' * 64
    store.ingest(state)
    assert not store.current


@pytest.mark.parametrize('limit', [800, 1100, 2000, 12000])
def test_multibyte_and_oversized_passages_keep_bounded_packet_and_explicit_omissions(limit):
    state = observed(('測定条件 ' * 15000, 'Only one writer is allowed.', 'Qualification: local use only.'))
    store = ObservedPassages()
    store.ingest(state)
    packet = store.packet(state, byte_limit=limit)
    assert len(encoded(packet)) <= limit
    assert len(store.receipts) == 3
    assert packet['omitted_passages'] >= 1
    assert all(p['text'] != state.passages[0].text for p in packet['passages'])
    assert all(p['sibling_context_omitted'] for p in packet['passages'])
    assert packet['sources'][0]['selection_incomplete'] is True
    assert len(packet['catalog']) + packet['catalog_omitted'] == packet['omitted_passages']


def test_fixed_objective_overflow_is_explicit_and_preserves_evidence():
    state = observed()
    state.original_request = 'Question ' * 1000
    store = ObservedPassages()
    store.ingest(state)
    with pytest.raises(WorkingContextOverflow):
        store.packet(state, byte_limit=1000)
    assert len(store.receipts) == 1


def test_continuation_replays_cited_evidence_ahead_of_recent_distractors():
    state = observed(('Calibration requires the device to remain indoors.',
                      'The documented limit is seven.',
                      *['A newer limit reference discusses seven devices. ' * 10 for _ in range(30)]))
    state.passages[0].kind = 'p'
    state.passages[1].kind = 'p'
    store = ObservedPassages()
    store.ingest(state)
    receipt = store.get('s1:p1')
    citation = store.citation(receipt.passage_id, receipt.capture_sha256, receipt.text,
                             receipt_id=receipt.identity)
    state.usage['direct_result'] = {'findings': [{'citations': [citation]}]}
    packet = store.packet(state, byte_limit=2500)
    assert packet['passages'][0]['id'] == 's1:p1'
    assert any(p['id'] == 's1:p0' for p in packet['passages'])
    assert len(encoded(packet)) <= 2500


def test_prior_quote_from_refreshed_capture_cannot_reenter_the_working_set():
    state = observed()
    store = ObservedPassages()
    store.ingest(state)
    old = store.get('s1:p0')
    citation = store.citation(old.passage_id, old.capture_sha256, old.text, receipt_id=old.identity)
    state = observed(('The replacement limit is eight.',), digest='b' * 64)
    state.usage['direct_result'] = {'findings': [{'citations': [citation]}]}
    store.ingest(state)
    assert store.retained_views(state) == {}
    assert old.text not in str(store.packet(state)['passages'])


def test_invalid_stored_quote_does_not_receive_continuity_priority():
    state = observed()
    store = ObservedPassages()
    store.ingest(state)
    receipt = store.get('s1:p0')
    state.usage['direct_result'] = {'findings': [{'citations': [{
        'passage_id': receipt.passage_id, 'receipt_id': receipt.identity,
        'capture_sha256': receipt.capture_sha256, 'quote': 'An invented literal quote.'}]}]}
    assert store.retained_views(state) == {}


def test_missing_passage_and_wrong_receipt_fail():
    state = observed()
    store = ObservedPassages()
    store.ingest(state)
    with pytest.raises(ValueError, match='current observed'):
        store.packet(state, preferred=['invented'])
    with pytest.raises(ValueError, match='stale'):
        store.citation('s1:p0', 'a' * 64, state.passages[0].text, receipt_id='wrong')


def test_local_relevance_ranking_keeps_the_question_ahead_of_recent_navigation():
    state = observed(('The documented limit is seven. Applies indoors only.',
                      'Subscribe to the newsletter and browse the navigation.' * 80))
    store = ObservedPassages()
    store.ingest(state)
    packet = store.packet(state, byte_limit=1200)
    assert packet['passages'][0]['id'] == 's1:p0'
    assert packet['passages'][0]['text'] == state.passages[0].text
    assert packet['omitted_passages'] == 1


def test_large_code_passage_has_a_navigable_literal_window():
    text = ('# Previous lines\n' * 10000) + 'if ready:\n\tprint("測定")\n' + ('# Following lines\n' * 10000)
    state = observed((text,))
    state.passages[0].kind = 'code'
    store = ObservedPassages()
    store.ingest(state)
    omitted = store.packet(state)
    assert not omitted['passages']
    assert omitted['catalog'][0]['text_characters'] == len(text)
    start, end = text.index('if ready:'), text.index('# Following lines')
    window = store.packet(state, windows=[('s1:p0', start, end)])
    item = window['passages'][0]
    assert item['text'] == 'if ready:\n\tprint("測定")\n'
    assert item['kind'] == 'code'
    assert item['view_complete'] is False
    assert item['original_characters'] == len(text)
    assert len(encoded(window)) <= 12000
    assert store.get('s1:p0').text == text


@pytest.mark.parametrize('start,end', [(-1, 10), (0, 1000000), (5, 4), (True, 4)])
def test_local_windows_reject_unobserved_or_invalid_ranges(start, end):
    state = observed()
    store = ObservedPassages()
    store.ingest(state)
    with pytest.raises(ValueError, match='original character range'):
        store.packet(state, windows=[('s1:p0', start, end)])
