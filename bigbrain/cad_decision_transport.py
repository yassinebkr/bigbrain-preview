"""Closed provider schemas for CAD decisions with lossless command parameter transport."""

from copy import deepcopy
import json

from .cad_stages import parse_object


def decision_tool_schema(schema):
    """Keep CAD contracts typed while encoding native command dictionaries as JSON."""
    decision = deepcopy(schema)
    definitions = decision.pop('$defs', {})
    workflow = definitions.get('CadWorkflow')
    if workflow is not None:
        # Additive proposals inherit existing members before the complete local
        # workflow validator applies its nonempty inventory requirements.
        for name in ('features', 'bodies', 'groups'):
            workflow['properties'][name]['minItems'] = 0
    command = definitions.get('CadCommand')
    if command is not None:
        # Command parameters depend on the discovered SolidCraft command. A JSON
        # string carries that object through providers requiring closed schemas.
        # The runtime restores the object before all existing command checks.
        command['properties']['params'] = {
            'type': 'string',
            'description': 'JSON object containing the exact native command parameters.',
        }
    envelope = {'type': 'object', 'properties': {'decision': decision},
                'required': ['decision'], 'additionalProperties': False, '$defs': definitions}
    return {'name': 'bigbrain_cad_decision',
            'description': 'Propose the next checkpoint-bound CAD decision.',
            'parameters': _provider_schema(envelope)}


def parse_decision_response(raw):
    """Decode the wire envelope and preserve legacy retained decision responses."""
    value = parse_object(raw)
    if not isinstance(value, dict):
        raise ValueError('CAD decision must be an object')
    if set(value) == {'decision'}:
        value = value['decision']
    if not isinstance(value, dict):
        raise ValueError('CAD decision must be an object')
    if value.get('operation') == 'execute' and isinstance(value.get('group'), dict):
        commands = value['group'].get('commands', [])
        if isinstance(commands, list):
            for command in commands:
                if isinstance(command, dict) and isinstance(command.get('params'), str):
                    parameters = json.loads(command['params'])
                    if not isinstance(parameters, dict):
                        raise ValueError('CAD command parameters must encode a JSON object')
                    command['params'] = parameters
    return value


def _provider_schema(schema, root=None):
    """Encode disjoint tagged unions and homogeneous vectors for strict providers."""
    root = schema if root is None else root
    if isinstance(schema, list):
        return [_provider_schema(value, root) for value in schema]
    if not isinstance(schema, dict):
        return schema
    result = {key: _provider_schema(value, root) for key, value in schema.items()}
    if 'oneOf' in result:
        tag = schema.get('discriminator', {}).get('propertyName')
        tags = set()
        for branch in schema['oneOf']:
            if '$ref' in branch:
                reference = branch['$ref']
                if not reference.startswith('#/$defs/'):
                    raise ValueError('CAD tagged union requires local definition references')
                branch = root['$defs'][reference[len('#/$defs/'):]]
            value = branch.get('properties', {}).get(tag, {}).get('const')
            if (not isinstance(value, str) or tag not in branch.get('required', [])
                    or value in tags):
                raise ValueError('CAD tagged union requires distinct required string constants')
            tags.add(value)
        # Distinct required tags prove that these branches cannot overlap.
        # The local Pydantic discriminator retains the complete domain validation.
        result['anyOf'] = result.pop('oneOf')
        result.pop('discriminator', None)
    if 'prefixItems' in result:
        items = result.pop('prefixItems')
        if not items or any(value != items[0] for value in items):
            raise ValueError('CAD transport requires homogeneous fixed vectors')
        result['items'] = items[0]
        result['minItems'] = len(items)
        result['maxItems'] = len(items)
    return result


# Fields with a stable meaning across construction decisions. Request-local
# authorities and measurements stay in the checkpoint packet.
CONSTRUCTION_CONTEXT_FIELDS = (
    'definition', 'native_compatibility', 'command_reference',
    'available_commands', 'observation_coverage', 'geometry_record_encoding',
)


def construction_messages(packet, messages, images):
    """Use a reusable user-message prefix and a fresh checkpoint suffix."""
    context = {key: packet[key] for key in CONSTRUCTION_CONTEXT_FIELDS if key in packet}
    foreground = {key: value for key, value in packet.items() if key not in context}
    prefix = json.dumps({'construction_context': context}, ensure_ascii=False, separators=(',', ':'))
    suffix = json.dumps(foreground, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    return [
        {**messages[0], 'content': messages[0]['content'] + (
            ' The construction_context message contains stable definition and tool reference fields. '
            'Use the latest checkpoint packet for current authority, observations and progress.')},
        {'role': 'user', 'content': [{'type': 'text', 'text': prefix}, *images]},
        {'role': 'user', 'content': [{'type': 'text', 'text': suffix}]},
    ], context
