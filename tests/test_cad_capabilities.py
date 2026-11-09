"""Complete command accounting and conservative capability evidence states."""

import pytest

from bigbrain.cad_capabilities import (
    attach_description, catalog_digest, command_inventory, inventory_summary,
)


def test_every_native_namespace_remains_visible_and_unqualified():
    catalog = [{'id': name, 'params': ''} for name in
               ['solid.sweep', 'construct.plane', 'surface.loft', 'sheet.flange',
                'joint.create', 'file.open', 'future.new_feature']]
    records = command_inventory(catalog)
    assert {record['id'] for record in records} == {entry['id'] for entry in catalog}
    assert sum(record['worker_scope'] == 'allowed' for record in records) == 2
    for record in records:
        assert record['qualification']['evidence'] == []
        assert record['qualification']['isolated_execution'] == 'untested'
    assert inventory_summary(records)['construct']['allowed'] == 1


def test_construction_uses_native_namespace_with_file_access_still_scoped():
    from bigbrain.cad_workflow import allowed_cad_command
    assert allowed_cad_command('construct.plane.offset')
    assert not allowed_cad_command('construction.plane.offset')
    assert not allowed_cad_command('file.open')


def test_description_schema_availability_does_not_prove_execution():
    record = command_inventory([{'id': 'solid.sweep', 'params': 'path'}])[0]
    description = {'id': 'solid.sweep', 'input': None, 'output': None, 'params': 'path'}
    attach_description(record, description)
    assert record['description_status'] == 'available'
    assert record['qualification']['geometric_checks'] == 'untested'
    with pytest.raises(ValueError, match='identity'):
        attach_description(record, {'id': 'solid.extrude'})


def test_duplicate_native_ids_fail_inventory_and_digest_tracks_catalog_changes():
    entry = {'id': 'solid.sweep', 'params': 'path'}
    with pytest.raises(ValueError, match='unique'):
        command_inventory([entry, entry])
    assert catalog_digest([entry]) == catalog_digest([dict(reversed(list(entry.items())))])
    assert catalog_digest([entry]) != catalog_digest([{**entry, 'params': 'updated path contract'}])
def test_helix_guidance_is_bound_to_qualified_executable():
    from bigbrain.cad_native_compat import construction_guidance, QUALIFIED_HELIX_BUILDS
    assert construction_guidance('0.28.0')[-1]['status'] == 'limited'
    assert construction_guidance('0.28.0', 'a' * 64)[-1]['status'] == 'limited'
    for build in QUALIFIED_HELIX_BUILDS:
        record = construction_guidance('0.28.0', build)[-1]
        assert record['status'] == 'qualified_examples'
        assert '1e-5' in record['qualified_cases']
        assert 'Other profiles' in record['limitation']
    assert construction_guidance('0.30.0', next(iter(QUALIFIED_HELIX_BUILDS))) == []

@pytest.mark.parametrize('origin', [None, [], [0, 0], ['radius', 0, 'height'],
    [True, 0, 0], [float('inf'), 0, 0], [float('nan'), 0, 0], [10**1000, 0, 0],
    {'x': 0, 'y': 0}, {'x': 'radius', 'y': 0, 'z': 0}])
def test_revolve_origin_fallback_is_rejected_before_native_mutation(origin):
    from bigbrain.solidcraft import CadError, SolidCraftSession
    with pytest.raises(CadError, match='silently replaces unsupported expressions'):
        SolidCraftSession.validate_commands([{'command': 'solid.revolve',
            'params': {'axis': {'origin': origin, 'dir': [0, 1, 0]}}}])


@pytest.mark.parametrize('axis', ['NamedAxis', {'origin': [260, 0, 150], 'dir': [0, 1, 0]},
    {'origin': {'x': 260, 'y': 0, 'z': 150}, 'dir': [0, 1, 0]}, {'type': 'world', 'axis': 'Y'}])
def test_revolve_numeric_and_named_axis_inputs_remain_available(axis):
    from bigbrain.solidcraft import SolidCraftSession
    SolidCraftSession.validate_commands([{'command': 'solid.revolve', 'params': {'axis': axis}}])
