"""Accepted parameter references preserve checkpoint and immutability checks."""

from copy import deepcopy

import pytest

from bigbrain.cad_controller import Decision
from bigbrain.cad_workflow_transport import expand_execution_workflow
from tests.test_cad_controller import actions


def example():
    value = actions()[1]
    value['base_checkpoint'] = 'a' * 32
    value['group']['base_checkpoint'] = 'a' * 32
    packet = {'base_checkpoint': 'a' * 32, 'accepted_workflow': deepcopy(value['group']['workflow'])}
    return value, packet


def test_parameter_reference_restores_exact_inventory_and_preserves_wire_record():
    value, packet = example()
    value['inherit_workflow'] = True
    value['group']['workflow']['parameters'] = []
    original = deepcopy(value)
    expanded = expand_execution_workflow(value, packet)
    assert value == original
    assert expanded['group']['workflow']['parameters'] == packet['accepted_workflow']['parameters']
    assert Decision.validate_python(expanded).inherit_workflow is True


def test_legacy_full_inventory_and_omission_keep_their_existing_validation_path():
    value, packet = example()
    value['group']['workflow']['parameters'] = []
    assert expand_execution_workflow(value, packet) == value


@pytest.mark.parametrize('field', ['base_checkpoint', 'group_checkpoint', 'accepted_workflow'])
def test_reference_requires_the_current_accepted_state(field):
    value, packet = example()
    value['inherit_workflow'] = True
    if field == 'base_checkpoint':
        value['base_checkpoint'] = 'b' * 32
    elif field == 'group_checkpoint':
        value['group']['base_checkpoint'] = None
    else:
        packet['accepted_workflow'] = None
    with pytest.raises(ValueError, match='inheritance'):
        expand_execution_workflow(value, packet)


def test_explicit_parameter_change_is_preserved_for_ancestor_revision_guard():
    value, packet = example()
    value['inherit_workflow'] = True
    value['group']['workflow']['parameters'][0]['expression'] = '99 mm'
    expanded = expand_execution_workflow(value, packet)
    assert expanded['group']['workflow']['parameters'][0]['expression'] == '99 mm'
    assert packet['accepted_workflow']['parameters'][0]['expression'] != '99 mm'


def test_additive_workflow_restores_all_named_inventories():
    from bigbrain.cad_workflow import CadWorkflow
    value, packet = example()
    value['inherit_workflow'] = True
    for field in ('parameters', 'sketches', 'features', 'bodies', 'groups'):
        value['group']['workflow'][field] = []
    expanded = expand_execution_workflow(value, packet)
    assert CadWorkflow.model_validate(expanded['group']['workflow']) == CadWorkflow.model_validate(packet['accepted_workflow'])


def test_additive_parameters_can_depend_on_retained_parameters():
    from bigbrain.cad_workflow import CadWorkflow
    value, packet = example()
    parent = packet['accepted_workflow']['parameters'][0]['name']
    value['inherit_workflow'] = True
    value['group']['workflow']['parameters'] = [{'name': 'half_length', 'expression': parent + ' / 2',
        'unit': 'mm', 'purpose': 'Derived half length', 'dependencies': [parent]}]
    expanded = expand_execution_workflow(value, packet)
    result = CadWorkflow.model_validate(expanded['group']['workflow'])
    assert result.parameters[-1].dependencies == (parent,)
    assert len(result.parameters) == len(packet['accepted_workflow']['parameters']) + 1


def test_additive_reorganization_cannot_hide_conflicting_group_ownership():
    from pydantic import ValidationError
    value, packet = example()
    value['inherit_workflow'] = True
    value['group']['workflow']['groups'][0]['name'] = 'Another group'
    with pytest.raises(ValidationError, match='exactly one group'):
        Decision.validate_python(expand_execution_workflow(value, packet))


def test_additions_preserve_duplicate_name_rejection():
    value, packet = example()
    value['inherit_workflow'] = True
    item = value['group']['workflow']['features'][0]
    value['group']['workflow']['features'] = [item, deepcopy(item)]
    with pytest.raises(ValueError, match='repeat'):
        expand_execution_workflow(value, packet)
