"""Compact generation schemas for the native research decision bridge."""
from copy import deepcopy


def action_variants(schema, allowed_tools):
    """Expose each executable argument shape with its mutually exclusive selectors."""
    definitions = deepcopy(schema.get('$defs', {}))
    root_fields = schema['properties']

    def nonnull(field):
        result = deepcopy(field)
        if 'anyOf' in result:
            choices = [item for item in result['anyOf'] if item.get('type') != 'null']
            if len(choices) == 1:
                result = {**{key:value for key,value in result.items() if key != 'anyOf'}, **choices[0]}
        if isinstance(result.get('type'), list):
            result['type'] = [item for item in result['type'] if item != 'null']
        if 'enum' in result:
            result['enum'] = [item for item in result['enum'] if item is not None]
        return result

    def shapes(tool, properties, *, child=False):
        common = ['tool', 'question_id', 'rationale']
        fields = ([] if child else ['review_reason'])
        required = []
        if tool == 'search':
            fields += ['query']; required = ['query']
        elif tool == 'visit':
            fields += ['url', 'focus']; required = ['url']
        elif tool == 'open':
            fields += ['source_id', 'mode', 'refresh']; required = ['source_id']
        elif tool == 'batch':
            fields += ['requests']; required = ['requests']
        elif tool in {'conclude', 'assess'}:
            fields += ['claims', 'remaining_gaps']
        elif tool == 'plan':
            fields += ['questions']; required = ['questions']
        elif tool == 'clarify':
            fields += ['clarification']; required = ['clarification']

        def variant(extra=(), mandatory=()):
            chosen = {key:deepcopy(properties[key]) for key in common+fields+list(extra)}
            chosen['tool'] = {'type':'string', 'const':tool}
            for key in required + list(mandatory):
                chosen[key] = nonnull(chosen[key])
            return {'type':'object', 'properties':chosen,
                    'required':common+required+list(mandatory), 'additionalProperties':False}
        if tool == 'open':
            focused = variant(['focus'])
            sections = variant(['group_ids', 'observation_sha256'], ['group_ids', 'observation_sha256'])
            sections['properties']['group_ids']['minItems'] = 1
            sections['properties']['group_ids']['uniqueItems'] = True
            return [focused, sections]
        chosen = variant()
        if tool in {'search', 'clarify'}:
            chosen['properties'][required[0]]['minLength'] = 1
        if tool in {'plan', 'batch'}:
            chosen['properties'][required[0]]['minItems'] = 1
        return [chosen]

    if 'batch' in allowed_tools:
        child_fields = definitions['CollectionRequest']['properties']
        definitions['CollectionRequest'] = {'anyOf':[shape
            for tool in ('search', 'open', 'visit') if tool in allowed_tools
            for shape in shapes(tool, child_fields, child=True)]}
    result = {'anyOf':[shape for tool in allowed_tools for shape in shapes(tool, root_fields)]}

    # Keep only referenced definitions and omit version/default metadata from
    # generation. Local contracts supply those defaults after strict parsing.
    retained = {}
    def references(value):
        if isinstance(value, dict):
            if '$ref' in value:
                name = value['$ref'].rsplit('/', 1)[-1]
                if name not in retained:
                    retained[name] = definitions[name]
                    references(definitions[name])
            for item in value.values():
                references(item)
        elif isinstance(value, list):
            for item in value:
                references(item)
    references(result)
    result['$defs'] = retained

    def compact(value):
        if isinstance(value, dict):
            return {key:compact(item) for key,item in value.items() if key not in {'default', 'schema_version'}}
        if isinstance(value, list):
            return [compact(item) for item in value]
        return value
    return compact(result)
