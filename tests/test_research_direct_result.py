"""Direct results distinguish grounded quotations from semantic review."""
import pytest

from bigbrain.research_direct_context import ObservedPassages
from bigbrain.research_direct_result import DirectConclusion, validate_conclusion
from tests.test_research_direct_context import observed


def candidate():
    state = observed()
    store = ObservedPassages()
    store.ingest(state)
    receipt = store.get('s1:p0')
    conclusion = DirectConclusion.model_validate({
        'findings': [{'id': 'f1', 'question_id': 'q1', 'text': 'Seven, indoors only.',
            'semantic_support': 'supported', 'scope_detail': 'Documented indoor usage',
            'citations': [{'passage_id': receipt.passage_id, 'receipt_id': receipt.identity,
                           'quote': receipt.text, 'relation': 'supports', 'direct': True}]}],
        'questions': [{'question_id': 'q1', 'finding_ids': ['f1']}],
        'sources': [{'source_id': 's1', 'suitability': 'suitable', 'nature': 'documentation',
                     'kind': 'primary', 'provenance_passage_id': receipt.passage_id,
                     'provenance_quote': receipt.text, 'basis': 'Directly observed reference statement'}]})
    return state, store, conclusion


def test_direct_conclusion_has_verified_citations_and_explicit_review_status():
    state, store, conclusion = candidate()
    result = validate_conclusion(conclusion, state, store)
    assert result['outcome'] == 'complete'
    assert result['citation_integrity'] == 'verified'
    assert result['semantic_assessment'] == 'model_judgment'
    assert result['independent_review'] == 'skipped'


def test_required_review_remains_partial_until_trusted_runtime_completion():
    state, store, conclusion = candidate()
    assert validate_conclusion(conclusion, state, store, review_required=True)['outcome'] == 'partial'
    assert validate_conclusion(conclusion, state, store, review_required=True,
                               review_completed=True)['independent_review'] == 'completed'


@pytest.mark.parametrize('mutation', ['missing_question', 'duplicate_finding', 'wrong_quote',
    'wrong_receipt', 'unknown_source', 'missing_suitability', 'unassigned_finding', 'wrong_relation'])
def test_invalid_conclusions_fail_closed(mutation):
    state, store, conclusion = candidate()
    if mutation == 'missing_question':
        conclusion.questions[0].question_id = 'q-other'
    elif mutation == 'duplicate_finding':
        conclusion.findings.append(conclusion.findings[0])
    elif mutation == 'wrong_quote':
        conclusion.findings[0].citations[0].quote = 'The limit is unlimited.'
    elif mutation == 'wrong_receipt':
        conclusion.findings[0].citations[0].receipt_id = 'b' * 64
    elif mutation == 'unknown_source':
        conclusion.sources[0].source_id = 'invented'
    elif mutation == 'missing_suitability':
        conclusion.sources = []
    elif mutation == 'unassigned_finding':
        conclusion.questions[0].finding_ids = []
        conclusion.questions[0].gaps = ['Missing information']
    else:
        conclusion.findings[0].citations[0].relation = 'context'
    with pytest.raises(ValueError):
        validate_conclusion(conclusion, state, store)


@pytest.mark.parametrize('reason', ['gap', 'contradiction', 'limited_source'])
def test_qualified_or_unresolved_answers_stay_partial(reason):
    state, store, conclusion = candidate()
    if reason == 'gap':
        conclusion.questions[0].gaps = ['A requested version comparison remains unread']
    elif reason == 'contradiction':
        conclusion.findings[0].semantic_support = 'unresolved'
    else:
        conclusion.sources[0].suitability = 'limited'
    assert validate_conclusion(conclusion, state, store)['outcome'] == 'partial'


def test_empty_answer_requires_explicit_gap_and_carries_no_citation_verdict():
    state, store, _ = candidate()
    conclusion = DirectConclusion.model_validate({
        'questions': [{'question_id': 'q1', 'gaps': ['Access to the report was blocked']} ]})
    result = validate_conclusion(conclusion, state, store)
    assert result['outcome'] == 'partial'
    assert result['citation_integrity'] == 'no_citations'


def test_literal_support_preserves_explicit_semantic_uncertainty():
    state, store, conclusion = candidate()
    conclusion.findings[0].semantic_support = 'unresolved'
    result = validate_conclusion(conclusion, state, store)
    assert result['findings'][0]['proposed_semantic_support'] == 'unresolved'
    assert result['findings'][0]['semantic_support'] == 'unverified'
    assert result['outcome'] == 'partial'


def test_final_check_refreshes_receipts_from_the_actual_runtime_state():
    state, store, conclusion = candidate()
    state.sources[0].content_sha256 = 'b' * 64
    state.passages[0].observation_sha256 = 'b' * 64
    with pytest.raises(ValueError, match='stale'):
        validate_conclusion(conclusion, state, store)


def test_model_cannot_supply_an_independent_review_flag():
    from pydantic import ValidationError
    _, _, conclusion = candidate()
    payload = conclusion.model_dump()
    payload['review_completed'] = True
    with pytest.raises(ValidationError):
        DirectConclusion.model_validate(payload)


@pytest.mark.parametrize('reason', ['independent_required', 'testimony', 'opinion'])
def test_existing_proof_standard_cannot_be_weakened_by_the_direct_path(reason):
    state, store, conclusion = candidate()
    if reason == 'independent_required':
        state.questions[0].proof_standard = 'independent_corroboration'
    elif reason == 'testimony':
        conclusion.sources[0].kind = 'testimony'
    else:
        conclusion.sources[0].nature = 'opinion'
    result = validate_conclusion(conclusion, state, store)
    assert result['outcome'] == 'partial'
    assert result['findings'][0]['semantic_support'] == 'unverified'


def test_provenance_requires_observed_text_even_when_model_declares_source_suitable():
    state, store, conclusion = candidate()
    conclusion.sources[0].provenance_quote = 'An invented provenance statement.'
    with pytest.raises(ValueError, match='quotation was not observed'):
        validate_conclusion(conclusion, state, store)


def test_copied_text_cannot_satisfy_independent_corroboration():
    state, store, conclusion = candidate()
    state.questions[0].proof_standard = 'independent_corroboration'
    state.sources.append(state.sources[0].model_copy(update={'id': 's2', 'url': 'https://copy.test/reference'}))
    state.passages.append(state.passages[0].model_copy(update={'id': 's2:p0', 'source_id': 's2'}))
    store.ingest(state)
    second = store.get('s2:p0')
    first_judgment = conclusion.sources[0]
    first_judgment.independent_basis = 'The source describes its own result'
    first_judgment.independent_quote = state.passages[0].text
    conclusion.sources.append(first_judgment.model_copy(update={'source_id': 's2',
        'provenance_passage_id': second.passage_id}))
    conclusion.findings[0].citations.append(conclusion.findings[0].citations[0].model_copy(update={
        'passage_id': second.passage_id, 'receipt_id': second.identity}))
    result = validate_conclusion(conclusion, state, store)
    assert result['outcome'] == 'partial'
    assert result['findings'][0]['semantic_support'] == 'unverified'
    groups = result['evidence_audits'][0]['origin_groups']
    assert groups['s1'] == groups['s2']


def test_explicit_contrary_evidence_remains_a_contested_finding():
    state, store, conclusion = candidate()
    state.passages.append(state.passages[0].model_copy(update={'id': 's1:p1',
        'text': 'The documented limit is nine. Applies outdoors only.'}))
    store.ingest(state)
    contrary = store.get('s1:p1')
    conclusion.findings[0].citations.append(conclusion.findings[0].citations[0].model_copy(update={
        'passage_id': contrary.passage_id, 'receipt_id': contrary.identity,
        'quote': contrary.text, 'relation': 'contradicts'}))
    result = validate_conclusion(conclusion, state, store)
    assert result['outcome'] == 'partial'
    assert result['findings'][0]['semantic_support'] == 'contested'
