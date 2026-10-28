"""Evidence allocation preserves local context and reports bounded visibility."""
from copy import deepcopy

import pytest

from bigbrain.research import Question
from bigbrain.research_allocation import bundles, candidate_queues, interleave
from bigbrain.research_direct_context import ObservedPassages, encoded
from bigbrain.research_direct_model import DirectModelAdapter
from tests.test_research_direct_context import observed
from tests.test_research_direct_model import Provider
from tests.test_research_direct_journey import runtime


def test_sections_keep_their_source_and_capture_boundaries():
    rows = [{'id': str(i), 'text': 'A paragraph', 'source_id': source,
             'capture_sha256': capture, 'context': ['Notes']}
            for i, (source, capture) in enumerate([('s1', 'a'), ('s2', 'a'), ('s2', 'b')])]
    assert len(bundles(rows)) == 3


def test_bundle_split_preserves_each_original_block():
    rows = [{'id': str(i), 'text': text, 'context': ['Notes']} for i, text in enumerate(['a'*50, 'b'*50, 'c'*200])]
    units = bundles(rows, character_limit=110)
    assert [[b['id'] for b in unit['blocks']] for unit in units] == [['0', '1'], ['2']]
    assert units[1]['blocks'][0]['text'] == 'c'*200


def test_round_robin_admits_other_requirements_before_deeper_candidates():
    assert list(interleave([[0, 1, 2], [3, 1, 4]])) == [0, 3, 1, 2, 4]


def test_source_bound_intent_keeps_candidates_on_its_observed_source():
    units = [{'blocks': [{'text': 'A documented limit is seven.', 'source_id': sid, 'kind': 'p'}]}
             for sid in ['s1', 's2']]
    assert candidate_queues([{'text': 'documented limit', 'source_id': 's2'}], units) == [[1]]


def test_coherent_bundle_is_admitted_whole_or_remains_in_catalog():
    state = observed(('The limit is seven. ' * 15, 'Qualification: only indoors. ' * 15))
    for passage in state.passages:
        passage.kind = 'p'
    store = ObservedPassages()
    store.ingest(state)
    packet = store.packet(state, byte_limit=1200)
    assert not packet['passages']
    assert packet['evidence_allocation'][0]['selection'] == 'budget_blocked'
    assert len(encoded(packet)) <= 1200
    assert len(store.receipts) == 2


def test_unmatched_question_keeps_a_first_class_gap():
    state = observed(('Recorded measurements are seven.',))
    state.questions.append(Question(id='q2', text='Unrelated zirconium isotope', evidence_needed='A reference'))
    store = ObservedPassages()
    store.ingest(state)
    packet = store.packet(state)
    assert next(row for row in packet['evidence_allocation'] if row['id'] == 'q2')['selection'] == 'no_match'
    assert packet['coverage'] == 'selected_observations'


def test_compact_model_view_keeps_receipt_hashes_in_the_backend_binding():
    engine, _ = runtime()
    engine.state = observed()
    store = ObservedPassages()
    store.ingest(engine.state)
    full = store.packet(engine.state)
    compact = store.packet(engine.state, compact=True)
    assert len(encoded(compact)) < len(encoded(full))
    assert 'receipt_id' not in compact['passages'][0]
    adapter = DirectModelAdapter(engine, Provider())
    bindings = adapter.bindings({'working_set': compact})
    assert bindings['s1:p0']['receipt_id'] == store.get('s1:p0').identity
    assert bindings['s1:p0']['capture_sha256'] == 'a'*64
    assert 'receipt_id' not in compact['passages'][0]


@pytest.mark.parametrize('mutation', ['text', 'source_id', 'view_start', 'view_end'])
def test_compact_bindings_reject_changes_outside_the_observed_window(mutation):
    engine, _ = runtime()
    engine.state = observed()
    store = ObservedPassages()
    store.ingest(engine.state)
    packet = deepcopy(store.packet(engine.state, compact=True))
    item = packet['passages'][0]
    item[mutation] = {'text': 'Invented', 'source_id': 's99', 'view_start': -1, 'view_end': 99999}[mutation]
    with pytest.raises(ValueError, match='observed receipt'):
        DirectModelAdapter(engine, Provider()).bindings({'working_set': packet})
