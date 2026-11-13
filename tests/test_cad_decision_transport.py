"""Provider CAD decisions retain typed removal intent and native parameter semantics."""

from copy import deepcopy
import json

from jsonschema import Draft202012Validator
import pytest

from bigbrain.cad_controller import Decision, ClosingDecision
from bigbrain.cad_decision_transport import decision_tool_schema, parse_decision_response
from bigbrain.llm.codex_provider import _strict_schema
from tests.test_cad_controller import actions


def removal():
    value = deepcopy(actions()[3])
    value['base_checkpoint'] = 'a' * 32
    value['group']['base_checkpoint'] = 'a' * 32
    return value


def wire(value):
    result = deepcopy(value)
    for command in result.get('group', {}).get('commands', []):
        command['params'] = json.dumps(command['params'], ensure_ascii=False)
    return {'decision': result}


def test_typed_schema_supports_codex_and_roundtrips_a_complete_cut():
    schema = decision_tool_schema(Decision.json_schema())['parameters']
    Draft202012Validator.check_schema(_strict_schema(schema))
    value = removal()
    encoded = wire(value)
    Draft202012Validator(schema).validate(encoded)
    parsed = Decision.validate_python(parse_decision_response(json.dumps(encoded)))
    legacy = Decision.validate_python(parse_decision_response(json.dumps(value)))
    assert parsed == legacy
    assert parsed.group.commands[0].params == value['group']['commands'][0]['params']
    assert parsed.group.cut_intents == legacy.group.cut_intents


@pytest.mark.parametrize('damage', ['missing_intent_identity', 'invented_openings', 'invented_boundary_fields'])
def test_live_protocol_failure_shapes_are_rejected_by_the_native_schema(damage):
    encoded = wire(removal())
    intent = encoded['decision']['group']['cut_intents'][0]
    if damage == 'missing_intent_identity':
        del intent['id']
        del intent['feature_id']
        del intent['dimension_ids']
    elif damage == 'invented_openings':
        intent['openings'] = intent.pop('boundaries')
    else:
        intent['boundaries'][0] = {'kind': 'opening', 'body': 'Base',
                                  'point': [0, 0, 0], 'normal': [0, 0, 1]}
    schema = decision_tool_schema(Decision.json_schema())['parameters']
    assert list(Draft202012Validator(schema).iter_errors(encoded))
    with pytest.raises(ValueError):
        Decision.validate_python(parse_decision_response(json.dumps(encoded)))


@pytest.mark.parametrize('parameters', ['[]', 'null', 'true', '7', '"command"'])
def test_command_parameters_require_an_object(parameters):
    encoded = wire(removal())
    encoded['decision']['group']['commands'][0]['params'] = parameters
    with pytest.raises(ValueError, match='JSON object'):
        parse_decision_response(json.dumps(encoded))


@pytest.mark.parametrize('raw', ['[]', 'null', '7', '{"decision":[]}'])
def test_malformed_decision_envelopes_raise_a_protocol_error(raw):
    with pytest.raises(ValueError, match='object'):
        parse_decision_response(raw)


def test_finalization_schema_excludes_mutation():
    schema = decision_tool_schema(ClosingDecision.json_schema())['parameters']
    _strict_schema(schema)
    valid = {'decision': {'operation': 'complete', 'base_checkpoint': 'a' * 32}}
    Draft202012Validator(schema).validate(valid)
    assert list(Draft202012Validator(schema).iter_errors(wire(removal())))


def test_provider_schema_uses_supported_union_and_vector_representations():
    schema = decision_tool_schema(Decision.json_schema())['parameters']
    encoded = _strict_schema(schema)
    text = json.dumps(encoded)
    assert '"oneOf"' not in text
    assert '"discriminator"' not in text
    assert '"prefixItems"' not in text
    validator = Draft202012Validator(schema)
    encoded_cut = wire(removal())
    validator.validate(encoded_cut)
    for vector in ([0, 0], [0, 0, 0, 0]):
        invalid = deepcopy(encoded_cut)
        invalid['decision']['group']['cut_intents'][0]['boundaries'][0]['origin_mm'] = vector
        assert list(validator.iter_errors(invalid))
    for decision in ({'operation': 'complete', 'base_checkpoint': None},
                     {'operation': 'blocked', 'base_checkpoint': None, 'reason': 'Missing source dimension'}):
        validator.validate({'decision': decision})
        Decision.validate_python(parse_decision_response(json.dumps({'decision': decision})))
