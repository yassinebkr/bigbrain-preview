"""Generation shapes expose executable action forms and preserve runtime gates."""
from types import SimpleNamespace

import jsonschema
import pytest

from bigbrain.research import Action, ModelPolicy


def schema(bridge=True, **overrides):
    constraints = {'allowed_tools':['search','visit','open','batch','conclude','clarify'],
                   'question_ids':['q1'], 'source_ids':['s1'], 'passage_ids':['s1:p1'], **overrides}
    provider = SimpleNamespace(supports_research_action_bridge=bridge)
    return ModelPolicy(provider).generation_protocol(Action, constraints)['tool_schema']['parameters']


def action(tool, **fields):
    return {'tool':tool, 'question_id':'q1', 'rationale':'Inspect the requested source', **fields}


@pytest.mark.parametrize('decision', [
    action('search', query='Exact source'),
    action('visit', url='https://public.test/manual'),
    action('open', source_id='s1', focus='Literal term'),
    action('open', source_id='s1', group_ids=['g1'], observation_sha256='a'*64),
    action('batch', requests=[action('open', source_id='s1', focus='Literal term'),
                             action('open', source_id='s1', group_ids=['g1'], observation_sha256='a'*64)]),
    action('conclude', claims=[{'id':'c1', 'question_id':'q1', 'text':'An observed finding.',
        'basis':'Original reference', 'evidence':[{'passage_id':'s1:p1', 'relation':'supports'}]}]),
])
def test_native_shapes_accept_valid_collection_and_delivery(decision):
    generated = schema()
    jsonschema.Draft202012Validator.check_schema(generated)
    jsonschema.validate(decision, generated)
    assert Action.model_validate(decision).tool == decision['tool']


@pytest.mark.parametrize('decision', [
    action('open', source_id='s1', focus='Literal term', group_ids=['g1'], observation_sha256='a'*64),
    action('open', source_id='s1', group_ids=['g1']),
    action('open', source_id='invented', focus='Literal term'),
    action('open', source_id='s1', focus=''),
    action('open', source_id='s1', rationale=None),
    action('batch', requests=[]),
    action('batch', requests=[action('open', source_id='s1', focus='', rationale='')]),
    action('conclude', claims=[{'id':'c1', 'question_id':'q1', 'text':'Claim', 'basis':'Reference', 'evidence':[]}]),
    action('plan', questions=[]),
])
def test_native_shapes_exclude_conflicts_and_inactive_arguments(decision):
    assert not jsonschema.Draft202012Validator(schema()).is_valid(decision)


def test_api_schema_and_frozen_claim_rules_remain_available():
    assert 'properties' in schema(bridge=False)
    closed = schema(allowed_tools=['conclude','clarify'], claims_frozen=True)
    assert jsonschema.Draft202012Validator(closed).is_valid(action('conclude', claims=[]))
    assert not jsonschema.Draft202012Validator(closed).is_valid(action('search', query='Out of phase'))
    assert 'CollectionRequest' not in closed['$defs']
