"""Claim-specific scope judgments preserve versions, disputes and uncertainty."""
import pytest
from pydantic import ValidationError

from bigbrain.research_direct_result import DirectCitation, validate_conclusion
from tests.test_research_direct_result import candidate


def test_unknown_applicability_keeps_an_explicit_continuation_gap():
    state, store, conclusion = candidate()
    citation = conclusion.findings[0].citations[0]
    citation.applicability = 'unknown'
    citation.applicability_basis = 'The source does not identify the applicable release.'
    result = validate_conclusion(conclusion, state, store)
    assert result['outcome'] == 'partial'
    assert result['findings'][0]['semantic_support'] == 'unverified'
    assert result['questions'][0]['gaps']
    assert result['question_coverage'][0]['missing_evidence']
    assert not conclusion.questions[0].gaps


def test_read_version_distinction_can_remain_contextual():
    state, store, conclusion = candidate()
    text = 'Release 2 permits seven indoors. Release 1 permitted nine outdoors.'
    state.passages[0].text = text
    store = type(store)()
    store.ingest(state)
    receipt = store.get('s1:p0')
    first = conclusion.findings[0].citations[0]
    first.receipt_id, first.quote = receipt.identity, 'Release 2 permits seven indoors.'
    first.applicability_basis = 'This finding is restricted to release 2 indoors.'
    other = first.model_copy(update={'quote': 'Release 1 permitted nine outdoors.',
        'relation': 'context', 'applicability': 'different_scope',
        'applicability_basis': 'The quoted release and location differ from the requested release 2 indoors.'})
    conclusion.findings[0].citations.append(other)
    conclusion.findings[0].scope_detail = 'The release 1 statement has a distinct documented scope.'
    conclusion.sources[0].provenance_quote = text
    result = validate_conclusion(conclusion, state, store)
    assert result['outcome'] == 'complete'
    assert result['findings'][0]['citations'][1]['applicability'] == 'different_scope'
    # Comparable counterevidence stays a dispute when its scope applies.
    other.applicability, other.relation = 'applicable', 'contradicts'
    result = validate_conclusion(conclusion, state, store)
    assert result['outcome'] == 'partial'
    assert result['findings'][0]['semantic_support'] == 'contested'
    assert result['questions'][0]['gaps']


@pytest.mark.parametrize('payload', [
    {'applicability': 'different_scope', 'relation': 'supports', 'applicability_basis': 'Other version'},
    {'applicability': 'unknown'},
])
def test_scope_labels_require_coherent_explanations(payload):
    _, _, conclusion = candidate()
    raw = conclusion.findings[0].citations[0].model_dump()
    raw.update(payload)
    with pytest.raises(ValidationError):
        DirectCitation.model_validate(raw)


def test_testimony_can_support_attributed_experience_with_its_limits():
    state, store, conclusion = candidate()
    finding = conclusion.findings[0]
    finding.scope = 'attributed_experience'
    finding.scope_detail = 'Only this speaker reports this result; no prevalence is established.'
    conclusion.sources[0].kind = 'testimony'
    conclusion.sources[0].nature = 'experience'
    conclusion.sources[0].limitations = ['No reproducible measurement or independent replication.']
    result = validate_conclusion(conclusion, state, store)
    assert result['findings'][0]['scope'] == 'attributed_experience'
    assert 'No reproducible measurement or independent replication.' in result['findings'][0]['limitations']
    finding.scope = 'general'
    assert validate_conclusion(conclusion, state, store)['outcome'] == 'partial'
