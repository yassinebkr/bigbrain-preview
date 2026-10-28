"""Acquired sources and model source judgments have distinct exposure contracts."""
import pytest

from bigbrain.research_direct_context import ObservedPassages
from bigbrain.research_direct_result import validate_conclusion
from bigbrain.research_direct_model import DirectModelAdapter
from bigbrain.research_direct import DirectFinish
from tests.test_research_direct_result import candidate
from tests.test_research_direct_journey import runtime
from tests.test_research_direct_model import Provider


def inventory_candidate():
    state, _, conclusion = candidate()
    state.sources.append(state.sources[0].model_copy(update={
        'id':'s2', 'url':'https://second.test/reference', 'content_sha256':'b'*64}))
    state.passages.append(state.passages[0].model_copy(update={
        'id':'s2:p0', 'source_id':'s2', 'observation_sha256':'b'*64}))
    store = ObservedPassages(require_exposure=True)
    store.ingest(state)
    receipt = store.get('s1:p0')
    store.expose({'working_set':{'passages':[dict(id=receipt.passage_id,
        text=receipt.text, view_start=0, view_end=len(receipt.text))]}})
    return state, store, conclusion


def test_uncited_unexposed_source_remains_in_inventory_without_a_fabricated_judgment():
    state, store, conclusion = inventory_candidate()
    result = validate_conclusion(conclusion, state, store)
    assert result['outcome'] == 'complete'
    assert result['source_inventory'][1] == dict(source_id='s2', acquisition_status='read',
        capture_sha256='b'*64, exposed=False, assessment='unassessed')
    assert len(state.sources) == 2 and len(state.passages) == 2
    assert len(result['sources']) == 1


def test_missing_requested_evidence_remains_partial_with_uncited_sources():
    state, store, conclusion = inventory_candidate()
    conclusion.questions[0].gaps = ['The second source has not been inspected for the requested comparison.']
    assert validate_conclusion(conclusion,state,store)['outcome'] == 'partial'


def test_source_judgment_still_requires_its_own_exposed_provenance():
    state, store, conclusion = inventory_candidate()
    source = conclusion.sources[0].model_copy(update={'source_id':'s2', 'provenance_passage_id':'s2:p0'})
    conclusion.sources.append(source)
    with pytest.raises(ValueError, match='model-exposed'):
        validate_conclusion(conclusion,state,store)
    conclusion.sources[-1].provenance_passage_id = 's1:p0'
    with pytest.raises(ValueError, match='another source'):
        validate_conclusion(conclusion,state,store)


def test_native_schema_admits_the_exposed_subset_and_an_empty_gap_only_result():
    state, store, _ = inventory_candidate()
    engine, _ = runtime()
    engine.state = state
    adapter = DirectModelAdapter(engine,Provider())
    view = store.packet(state)
    view['passages'] = [p for p in view['passages'] if p['source_id']=='s1']
    adapter.forecast({'working_set':view},DirectFinish)
    schema = adapter.actor.protocol(DirectFinish)['tool_schema']['parameters']
    sources = schema['$defs']['DirectConclusion']['properties']['sources']
    assert sources['minItems'] == 0 and sources['maxItems'] == 1
    handles = schema['$defs']['SourceAssessment']['properties']['source_reference']['enum']
    assert handles and all(handle.startswith('s1:') for handle in handles)
