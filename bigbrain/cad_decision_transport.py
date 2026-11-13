"""Closed provider schemas for CAD decisions with lossless command parameter transport."""

from copy import deepcopy
import json

from .cad_stages import parse_object


def decision_tool_schema(schema):
    """Keep CAD contracts typed while encoding native command dictionaries as JSON."""
    decision = deepcopy(schema)
    definitions = decision.pop('$defs', {})
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
            'parameters': envelope}


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
