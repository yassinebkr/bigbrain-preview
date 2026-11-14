"""Checkpoint-bound additive references to accepted CAD design intent."""

from copy import deepcopy

from .cad_workflow import CadWorkflow, DesignGroup, DesignParameter, FeatureIntent, SketchIntent


def _merge_named(retained, supplied, model):
    """Preserve accepted members and validate every explicit addition or replacement."""
    old = [model.model_validate(item) for item in retained]
    new = [model.model_validate(item) for item in supplied]
    if len({item.name for item in new}) != len(new):
        raise ValueError('Workflow additions repeat a declared name')
    combined = {item.name: item.model_dump(mode='json') for item in old}
    for item in new:
        value = item.model_dump(mode='json')
        if model is DesignGroup:
            for field in ('features', 'sketches', 'bodies'):
                if len(value[field]) != len(set(value[field])):
                    raise ValueError('Workflow additions repeat a group member')
                previous = combined.get(item.name, {}).get(field, [])
                value[field] = list(dict.fromkeys([*previous, *value[field]]))
        combined[item.name] = value
    return list(combined.values())


def expand_execution_workflow(value, packet):
    """Restore the accepted inventory before full workflow and immutability checks."""
    if value.get('operation') != 'execute' or value.get('inherit_workflow') is not True:
        return value
    group = value.get('group') or {}
    checkpoint = packet.get('base_checkpoint')
    if (checkpoint is None or value.get('base_checkpoint') != checkpoint
            or group.get('base_checkpoint') != checkpoint):
        raise ValueError('Workflow inheritance requires the exact accepted checkpoint')
    workflow = group.get('workflow')
    accepted = packet.get('accepted_workflow')
    if not isinstance(workflow, dict) or not isinstance(accepted, dict):
        raise ValueError('Workflow inheritance requires an accepted workflow')
    accepted = CadWorkflow.model_validate(accepted).model_dump(mode='json')
    expanded = deepcopy(value)
    target = expanded['group']['workflow']
    for field, model in (('parameters', DesignParameter), ('sketches', SketchIntent),
                         ('features', FeatureIntent), ('groups', DesignGroup)):
        supplied = workflow.get(field, [])
        if not isinstance(supplied, list):
            raise ValueError('Workflow additions must be arrays')
        target[field] = _merge_named(accepted[field], supplied, model)
    bodies = workflow.get('bodies', [])
    if (not isinstance(bodies, list) or any(not isinstance(item, str) for item in bodies)
            or len(bodies) != len(set(bodies))):
        raise ValueError('Workflow body additions must have distinct names')
    target['bodies'] = list(dict.fromkeys([*accepted['bodies'], *bodies]))
    if workflow.get('primitive_reason') is None:
        target['primitive_reason'] = accepted.get('primitive_reason')
    # Explicit parameter changes still reach the ancestor-revision guard. The
    # complete validator also checks group ownership, dependencies and limits.
    return expanded
