"""Lossless columnar geometry records for CAD decision packets."""
from copy import deepcopy
import json


def geometry_records(records):
    """Share repeated field names while retaining values and original positions."""
    if not isinstance(records, list) or not records or not all(isinstance(x, dict) for x in records):
        return records
    groups = {}
    for position, record in enumerate(records):
        columns = tuple(sorted(record))
        group = groups.setdefault(columns, {'columns':list(columns),'positions':[],'rows':[]})
        group['positions'].append(position)
        group['rows'].append([record[key] for key in columns])
    packed = {'encoding':'columnar-records-v1','count':len(records),'groups':list(groups.values())}
    size = lambda value: len(json.dumps(value,separators=(',',':'),ensure_ascii=False).encode())
    return packed if size(packed) < size(records) else records


def decision_observations(observations, shared_design=None):
    """Encode repeated native records in a detached transport view of evidence."""
    def encode(value):
        if isinstance(value,dict):
            return {key:encode(item) for key,item in value.items()}
        if isinstance(value,list):
            return geometry_records([encode(item) for item in value])
        return value
    result = deepcopy(observations)
    for key, observation in result.items():
        value = observation.get('result', {})
        if key.startswith('inspect_design:'):
            if shared_design is not None and value.get('params') == shared_design.get('params'):
                value['params'] = {'$ref':'#/current_design/params'}
            observation['result'] = encode(value)
            continue
        bodies = ([value] if key.startswith('body_topology:') else
                  list(value.get('bodies', {}).values()) if key.startswith('precise_geometry:') else [])
        for body in bodies:
            for field in ('faces','edges'):
                if field in body:
                    body[field] = encode(body[field])
    return result
