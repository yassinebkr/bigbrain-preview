"""Closed provider schemas for CAD decisions with lossless command parameter transport."""

from copy import deepcopy
import json

from .cad_stages import parse_object


def decision_tool_schema(schema):
    """Keep CAD contracts typed while encoding native command dictionaries as JSON."""
    decision = deepcopy(schema)
    definitions = decision.pop('$defs', {})
    # Operation constants make these branches disjoint. The provider accepts
    # anyOf, while local validation retains the discriminator for precise errors.
    if decision.get('discriminator', {}).get('propertyName') == 'operation':
        decision['anyOf'] = decision.pop('oneOf')
        decision.pop('discriminator')
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
            'parameters': _homogeneous_vectors(envelope)}


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


def _homogeneous_vectors(schema):
    """Represent fixed homogeneous tuples with supported array length bounds."""
    if isinstance(schema, list):
        return [_homogeneous_vectors(value) for value in schema]
    if not isinstance(schema, dict):
        return schema
    result = {key: _homogeneous_vectors(value) for key, value in schema.items()}
    if 'prefixItems' in result:
        items = result.pop('prefixItems')
        if not items or any(value != items[0] for value in items):
            raise ValueError('CAD transport requires homogeneous fixed vectors')
        result['items'] = items[0]
        result['minItems'] = len(items)
        result['maxItems'] = len(items)
    return result
