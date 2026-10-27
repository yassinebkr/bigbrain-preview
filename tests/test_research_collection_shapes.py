"""Generation rejects collection selectors that executable actions cannot use."""
import jsonschema
import pytest

from bigbrain.research_workflow import CollectionDecision, WorkflowPolicy


@pytest.mark.parametrize('sources', [[], ['s1']])
def test_collection_generation_matches_executable_selectors(sources):
    actor = WorkflowPolicy(object(), 'collect')
    actor.generation_scope = dict(questions=['q1'], sources=sources, passages=[], claims=[], dossier=None,
                                 section_ids=['b1'] if sources else [], capture_hashes=['a'*64])
    schema = actor.protocol(CollectionDecision)['tool_schema']['parameters']
    validator = jsonschema.Draft202012Validator(schema)
    visit = dict(tool='visit', question_id='q1', rationale='Read the reference', url='https://example.org/')
    assert not list(validator.iter_errors({'requests':[visit]}))
    assert list(validator.iter_errors({'requests':[{**visit, 'group_ids':['invented']}]}))
    if sources:
        opened = dict(tool='open', question_id='q1', rationale='Read captured section', source_id='s1',
                      group_ids=['b1'], observation_sha256='a'*64)
        assert not list(validator.iter_errors({'requests':[opened]}))
        assert list(validator.iter_errors({'requests':[{**opened, 'focus':'literal'}]}))
        assert list(validator.iter_errors({'requests':[{**opened, 'group_ids':['invented']}]}))


def test_discovery_exposes_no_unobserved_section_selectors():
    actor = WorkflowPolicy(object(), 'collect')
    actor.generation_scope = dict(questions=['q1'], sources=['s1'], passages=[], claims=[], dossier=None)
    schema = actor.protocol(CollectionDecision)['tool_schema']['parameters']
    validator = jsonschema.Draft202012Validator(schema)
    request = dict(tool='open', question_id='q1', rationale='Read discovered page', source_id='s1')
    assert not list(validator.iter_errors({'requests':[request]}))
    assert list(validator.iter_errors({'requests':[{**request, 'group_ids':['invented'],
                                                   'observation_sha256':'a'*64}]}))


def test_control_generation_leaves_offsets_to_runtime_and_bounds_origins():
    from bigbrain.research_workflow import Control
    actor = WorkflowPolicy(object(), 'control')
    actor.generation_scope = dict(questions=['q1'], sources=['s1'], passages=['p1'], claims=['c1'],
                                 dossier='b'*64, origin_urls=['https://source.test/original'])
    definitions = actor.protocol(Control)['tool_schema']['parameters']['$defs']
    assert 'start' not in definitions['CitationAssessment']['properties']
    assert 'end' not in definitions['CitationAssessment']['properties']
    assert definitions['SourceAssessment']['properties']['origin_urls']['items']['enum'] == [
        'https://source.test/original']
