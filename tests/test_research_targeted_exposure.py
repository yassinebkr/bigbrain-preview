"""Targeted read intents receive bounded evidence exposure across source updates."""
from bigbrain.research import Action, Observation, Passage, Question, ResearchState, Source
from bigbrain.research_direct_context import ObservedPassages, encoded


def test_new_source_inspection_precedes_repeated_general_evidence():
    state = ResearchState(objective='Compare supported behaviors',
        questions=[Question(id='q1', text='general behavior', evidence_needed='reference')],
        sources=[Source(id=f's{i}', url=f'https://docs.test/{i}', discovered_by='fixture',
                        status='read', content_sha256=str(i) * 64) for i in (1, 2)],
        passages=[Passage(id=f's{i}:p1', source_id=f's{i}', text=text,
                          context=['Reference'], observation_sha256=str(i) * 64)
                  for i, text in [(1, 'general behavior ' * 50),
                                  (2, 'Ownership follows the associated column. ' * 10)]],
        observations=[Observation(index=0, action=Action(tool='open', question_id='q1',
            source_id='s2', rationale='Inspect remaining ownership question',
            reading_question='ownership associated column'), status='ok', data={})])
    store = ObservedPassages(require_exposure=True)
    store.ingest(state)
    old = store.get('s1:p1')
    store.expose({'working_set': {'passages': [dict(id=old.passage_id, text=old.text,
        view_start=0, view_end=len(old.text))]}})
    before = dict(store.exposed)
    packet = store.packet(state, compact=True, byte_limit=2200)
    assert len(encoded(packet)) <= 2200
    assert packet['passages'][0]['source_id'] == 's2'
    assert 'Ownership' in packet['passages'][0]['text']
    assert store.exposed == before  # Forecast construction grants no citation access.


def test_optional_scope_guidance_preserves_required_qualifications():
    from bigbrain.research_direct_model import INSTRUCTIONS
    assert 'à définir au besoin' in INSTRUCTIONS
    assert 'accuracy of requested conclusions' in INSTRUCTIONS


def test_latest_intent_replaces_obsolete_source_query():
    state = ResearchState(objective='Compare behavior',
        questions=[Question(id='q1', text='general', evidence_needed='reference')],
        sources=[Source(id='s1', url='https://docs.test/reference', discovered_by='fixture',
                        status='read', content_sha256='a' * 64)],
        passages=[Passage(id=f's1:p{i}', source_id='s1', text=text, context=[str(i)],
                          observation_sha256='a' * 64) for i, text in enumerate([
                              'obsolete alpha ' * 30, 'remaining omega ' * 30])],
        observations=[Observation(index=i, action=Action(tool='open', question_id='q1',
            source_id='s1', rationale='Targeted inspection', reading_question=query),
            status='ok', data={}) for i, query in enumerate(['obsolete alpha', 'remaining omega'])])
    store = ObservedPassages()
    store.ingest(state)
    packet = store.packet(state, compact=True, byte_limit=1800)
    assert packet['passages'][0]['id'] == 's1:p1'
    assert sum(lane['id'] == 'q1@s1' for lane in packet['evidence_allocation']) == 1
