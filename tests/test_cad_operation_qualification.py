"""Measured native operation cases with an explicit parameter-edit regression."""

import math
import json

import pytest

from bigbrain.solidcraft import CadError, SolidCraftSession, solidcraft_executable


def primitive_case(kind, value):
    """Analytic expectations are independent of the engine's reported geometry."""
    if kind == 'box':
        return {'length': 'size', 'width': 10, 'height': 5}, (value, 10, 5), value * 50
    if kind == 'cylinder':
        return {'radius': 'size', 'height': 10}, (2 * value, 2 * value, 10), math.pi * value**2 * 10
    if kind == 'sphere':
        return {'radius': 'size'}, (2 * value,) * 3, 4 * math.pi * value**3 / 3
    if kind == 'cone':
        return {'radius': 'size', 'height': 10}, (2 * value, 2 * value, 10), math.pi * value**2 * 10 / 3
    if kind == 'torus':
        return {'major': 'size', 'minor': 2}, (2 * (value + 2), 2 * (value + 2), 4), 8 * math.pi**2 * value
    raise ValueError(kind)


async def check_capture(session, revision, dimensions, volume, *, body_count=1):
    capture = await session.capture('a' * 32, 'a' * 32, revision)
    geometry = capture.geometry
    assert geometry.body_count == body_count
    assert geometry.closed_solid
    observed = tuple(high - low for low, high in zip(geometry.bounds_min_mm, geometry.bounds_max_mm))
    assert observed == pytest.approx(dimensions, abs=0.001)
    assert geometry.volume_mm3 == pytest.approx(volume, rel=0.00001, abs=0.001)
    return capture


def check_bore_material(step_path, radius):
    """Probe bore continuity and retained walls on the exported exact surfaces."""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_IN
    from OCP.gp import gp_Pnt
    reader = STEPControl_Reader()
    reader.ReadFile(str(step_path))
    assert reader.TransferRoots()
    shape = reader.OneShape()
    diagonal = radius / math.sqrt(2)
    wall = (radius + 4.5) / math.sqrt(2)
    probes = [
        ('flange_bore', (radius, -8, 0), False),
        ('bend_bore', (diagonal, diagonal, 0), False),
        ('outlet_bore', (0.1, radius, 0), False),
        ('bend_wall', (wall, wall, 0), True),
        ('flange_material', (radius + 6, -8, 0), True),
    ]
    results = []
    for label, point, expected in probes:
        actual = BRepClass3d_SolidClassifier(shape, gp_Pnt(*point), 1e-7).State() == TopAbs_IN
        results.append({'label': label, 'point_mm': point, 'material': actual, 'expected': expected})
        assert actual == expected, label
    return results


@pytest.fixture
def native_engine():
    try:
        return solidcraft_executable()
    except CadError:
        pytest.skip('Installed SolidCraft is required for native operation qualification')


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['box', 'cylinder', 'sphere', 'cone', 'torus'])
async def test_native_primitive_and_parameter_edit(tmp_path, native_engine, kind):
    async with SolidCraftSession(tmp_path, executable=native_engine) as session:
        params, dimensions, volume = primitive_case(kind, 10)
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'size', 'expression': '10 mm'}},
            {'command': 'solid.' + kind, 'params': {**params, 'body_name': 'QualificationBody'}},
        ])
        await check_capture(session, 1, dimensions, volume)
        edit = await session.tool('set_parameter', {'name': 'size', 'value': '12 mm'})
        assert not edit.get('errors')
        _, dimensions, volume = primitive_case(kind, 12)
        await check_capture(session, 2, dimensions, volume)


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['join', 'cut', 'intersect'])
async def test_native_boolean_and_parameter_edit(tmp_path, native_engine, operation):
    async with SolidCraftSession(tmp_path, executable=native_engine) as session:
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'size', 'expression': '20 mm'}},
            {'command': 'solid.box', 'params': {'length': 'size', 'width': 10, 'height': 5,
                                               'corner': [0, 0, 0], 'body_name': 'Target'}},
            {'command': 'solid.box', 'params': {'length': 'size', 'width': 10, 'height': 5,
                                               'corner': ['size/2', 0, 0], 'body_name': 'Tool'}},
            {'command': 'solid.combine', 'params': {'target': 'Target', 'tools': ['Tool'],
                                                   'operation': operation}},
        ])
        factor = 1.5 if operation == 'join' else 0.5
        await check_capture(session, 1, (20 * factor, 10, 5), 20 * factor * 50)
        edit = await session.tool('set_parameter', {'name': 'size', 'value': '24 mm'})
        assert not edit.get('errors')
        await check_capture(session, 2, (24 * factor, 10, 5), 24 * factor * 50)


@pytest.mark.asyncio
async def test_native_offset_plane_preserves_downstream_parameter_reference(tmp_path, native_engine):
    async with SolidCraftSession(tmp_path, executable=native_engine) as session:
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'offset', 'expression': '10 mm'}},
            {'command': 'construct.plane.offset', 'params': {'base': 'XY', 'offset': 'offset', 'name': 'Datum'}},
            {'command': 'sketch.create', 'params': {'plane': 'Datum', 'name': 'Profile'}},
            {'command': 'sketch.draw.dimensioned', 'params': {
                'command': 'sketch.rectangle.two_point', 'params': {'p0': [0, 0], 'p1': [10, 10]},
                'dimensions': {'width': 10, 'height': 10}, 'locate': True}},
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'solid.extrude', 'params': {'sketch': 'Profile', 'distance': 10}},
        ])
        await check_capture(session, 1, (10, 10, 10), 1000)
        before = await session.tool('inspect_design')
        assert before['bodies'][0]['bbox']['min'][2] == pytest.approx(10, abs=0.001)
        edit = await session.tool('set_parameter', {'name': 'offset', 'value': '12 mm'})
        assert not edit.get('errors')
        await check_capture(session, 2, (10, 10, 10), 1000)
        after = await session.tool('inspect_design')
        assert after['bodies'][0]['bbox']['min'][2] == pytest.approx(12, abs=0.001)


@pytest.mark.asyncio
@pytest.mark.parametrize('curved', [False, True], ids=['straight', 'quarter-bend'])
async def test_native_hollow_pipe_and_parameter_edit(tmp_path, native_engine, curved):
    async with SolidCraftSession(tmp_path, executable=native_engine) as session:
        path = ({'command': 'sketch.arc.center_point', 'params': {
            'center': [0, 0], 'start': ['size', 0], 'end': [0, 'size']}} if curved else
            {'command': 'sketch.line', 'params': {'points': [[0, 0], ['size', 0]]}})
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'size', 'expression': '30 mm'}},
            {'command': 'sketch.create', 'params': {'plane': 'XY', 'name': 'Path'}}, path,
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'solid.pipe', 'params': {'path_sketch': 'Path', 'path': ['a1' if curved else 'l1'],
                                                'diameter': 10, 'wall': 1, 'body_name': 'Pipe'}},
        ])
        for revision, size in [(1, 30), (2, 36)]:
            if revision == 2:
                edit = await session.tool('set_parameter', {'name': 'size', 'value': '36 mm'})
                assert not edit.get('errors')
            length = math.pi * size / 2 if curved else size
            dimensions = (size + 5, size + 5, 10) if curved else (size, 10, 10)
            await check_capture(session, revision, dimensions, math.pi * (25 - 16) * length)


@pytest.mark.asyncio
async def test_native_revolution_and_parameter_edit(tmp_path, native_engine):
    async with SolidCraftSession(tmp_path, executable=native_engine) as session:
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'size', 'expression': '10 mm'}},
            {'command': 'sketch.create', 'params': {'plane': 'XZ', 'name': 'Profile'}},
            {'command': 'sketch.draw.dimensioned', 'params': {
                'command': 'sketch.rectangle.two_point', 'params': {'p0': [0, 0], 'p1': [10, 20]},
                'dimensions': {'width': 'size', 'height': 20}, 'locate': True}},
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'solid.revolve', 'params': {'sketch': 'Profile', 'axis': 'Z', 'angle': '360 deg'}},
        ])
        await check_capture(session, 1, (20, 20, 20), math.pi * 100 * 20)
        edit = await session.tool('set_parameter', {'name': 'size', 'value': '12 mm'})
        assert not edit.get('errors')
        await check_capture(session, 2, (24, 24, 20), math.pi * 144 * 20)


@pytest.mark.asyncio
async def test_native_shell_and_parameter_edit(tmp_path, native_engine):
    async with SolidCraftSession(tmp_path, executable=native_engine) as session:
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'wall', 'expression': '1 mm'}},
            {'command': 'solid.box', 'params': {'length': 20, 'width': 20, 'height': 20,
                                               'corner': [0, 0, 0], 'body_name': 'Shell'}},
            {'command': 'solid.shell', 'params': {'body': 'Shell', 'faces': [[10, 10, 20]],
                                                 'thickness': 'wall', 'direction': 'inside'}},
        ])
        for revision, wall in [(1, 1), (2, 2)]:
            if revision == 2:
                edit = await session.tool('set_parameter', {'name': 'wall', 'value': '2 mm'})
                assert not edit.get('errors')
            await check_capture(session, revision, (20, 20, 20), 8000 - (20 - 2 * wall)**2 * (20 - wall))


@pytest.mark.asyncio
@pytest.mark.parametrize('curved', [False, True], ids=['straight', 'quarter-bend'])
async def test_native_pipe_flange_union_and_parameter_edit(tmp_path, native_engine, curved):
    # Give the isolated curved Boolean enough time to distinguish a slow result
    # from the normal 30-second transport ceiling; production limits stay intact.
    async with SolidCraftSession(tmp_path, executable=native_engine, timeout=120) as session:
        path = ([
            {'command': 'sketch.line', 'params': {'points': [['size', -10], ['size', 0]]}},
            {'command': 'sketch.arc.center_point', 'params': {'center': [0, 0], 'start': ['size', 0],
                                                             'end': [0, 'size']}},
        ] if curved else [{'command': 'sketch.line', 'params': {'points': [[0, 0], ['size', 0]]}}])
        base = ['size', -10, 0] if curved else [0, 0, 0]
        axis = 'Y' if curved else 'X'
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'size', 'expression': '30 mm'}},
            {'command': 'sketch.create', 'params': {'plane': 'XY', 'name': 'Path'}}, *path,
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'solid.pipe', 'params': {'path_sketch': 'Path', 'path': ['l1', 'a1'] if curved else ['l1'],
                                                'diameter': 10, 'wall': 1, 'body_name': 'Pipe'}},
            {'command': 'solid.cylinder', 'params': {'base': base, 'axis': axis, 'radius': 8, 'height': 3,
                                                    'operation': 'new', 'body_name': 'Flange'}},
            {'command': 'solid.cylinder', 'params': {'base': base, 'axis': axis, 'radius': 4, 'height': 3,
                                                    'operation': 'cut', 'targets': ['Flange']}},
        ])
        # Preserve the exact pre-union state even when the native Boolean fails.
        await session.tool('save', {'path': str(tmp_path / 'pre-union.sc')})
        inspection = await session.tool('inspect_design')
        (tmp_path / 'pre-union.json').write_text(json.dumps(inspection, indent=2))
        pre_union = await session.capture('a' * 32, 'a' * 32, 1)
        assert pre_union.geometry.body_count == 2
        assert pre_union.geometry.closed_solid
        try:
            await session.batch([{'command': 'solid.combine', 'params': {
                'target': 'Pipe', 'tools': ['Flange'], 'operation': 'join'}}])
        finally:
            (tmp_path / 'union-trace.json').write_text(json.dumps(session.observations, indent=2))
        for revision, size in [(2, 30), (3, 36)]:
            if revision == 3:
                edit = await session.tool('set_parameter', {'name': 'size', 'value': '36 mm'})
                assert not edit.get('errors')
            length = math.pi * size / 2 + 10 if curved else size
            dimensions = (size + 8, size + 15, 16) if curved else (size, 16, 16)
            await check_capture(session, revision, dimensions, math.pi * (9 * length + 117))


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['fillet', 'chamfer'])
async def test_native_edge_finish_and_parameter_edit(tmp_path, native_engine, operation):
    async with SolidCraftSession(tmp_path, executable=native_engine) as session:
        field = 'radius' if operation == 'fillet' else 'distance'
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'size', 'expression': '1 mm'}},
            {'command': 'solid.box', 'params': {'length': 20, 'width': 20, 'height': 20,
                                               'corner': [0, 0, 0], 'body_name': 'Block'}},
            {'command': 'solid.' + operation, 'params': {'body': 'Block', 'edges': [[0, 0, 10]], field: 'size'}},
        ])
        for revision, size in [(1, 1), (2, 2)]:
            if revision == 2:
                edit = await session.tool('set_parameter', {'name': 'size', 'value': '2 mm'})
                assert not edit.get('errors')
            removed = size**2 * 20 * ((1 - math.pi / 4) if operation == 'fillet' else 0.5)
            await check_capture(session, revision, (20, 20, 20), 8000 - removed)


@pytest.mark.asyncio
async def test_native_rectangular_pattern_and_parameter_edit(tmp_path, native_engine):
    async with SolidCraftSession(tmp_path, executable=native_engine) as session:
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'spacing', 'expression': '20 mm'}},
            {'command': 'solid.box', 'params': {'length': 5, 'width': 5, 'height': 5,
                                               'corner': [0, 0, 0], 'body_name': 'Seed'}},
            {'command': 'solid.pattern.rectangular', 'params': {'bodies': ['Seed'], 'dir1': [1, 0, 0],
                                                                'count1': 3, 'spacing1': 'spacing'}},
        ])
        await check_capture(session, 1, (45, 5, 5), 375, body_count=3)
        edit = await session.tool('set_parameter', {'name': 'spacing', 'value': '24 mm'})
        assert not edit.get('errors')
        await check_capture(session, 2, (53, 5, 5), 375, body_count=3)


@pytest.mark.asyncio
async def test_native_loft_and_parameter_edit(tmp_path, native_engine):
    async with SolidCraftSession(tmp_path, executable=native_engine) as session:
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'height', 'expression': '20 mm'}},
            {'command': 'sketch.create', 'params': {'plane': 'XY', 'name': 'Lower'}},
            {'command': 'sketch.circle.center', 'params': {'center': [0, 0], 'radius': 5}},
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'construct.plane.offset', 'params': {'base': 'XY', 'offset': 'height', 'name': 'UpperDatum'}},
            {'command': 'sketch.create', 'params': {'plane': 'UpperDatum', 'name': 'Upper'}},
            {'command': 'sketch.circle.center', 'params': {'center': [0, 0], 'radius': 8}},
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'solid.loft', 'params': {'sections': [{'sketch': 'Lower'}, {'sketch': 'Upper'}]}},
        ])
        await check_capture(session, 1, (16, 16, 20), math.pi * 20 / 3 * (25 + 40 + 64))
        edit = await session.tool('set_parameter', {'name': 'height', 'value': '24 mm'})
        assert not edit.get('errors')
        await check_capture(session, 2, (16, 16, 24), math.pi * 24 / 3 * (25 + 40 + 64))


@pytest.mark.asyncio
async def test_native_sweep_and_parameter_edit(tmp_path, native_engine):
    async with SolidCraftSession(tmp_path, executable=native_engine) as session:
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'length', 'expression': '20 mm'}},
            {'command': 'sketch.create', 'params': {'plane': 'XY', 'name': 'Path'}},
            {'command': 'sketch.line', 'params': {'points': [[0, 0], ['length', 0]]}},
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'sketch.create', 'params': {'plane': 'YZ', 'name': 'Section'}},
            {'command': 'sketch.draw.dimensioned', 'params': {
                'command': 'sketch.rectangle.two_point', 'params': {'p0': [0, 0], 'p1': [2, 3]},
                'dimensions': {'width': 2, 'height': 3}, 'locate': True}},
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'solid.sweep', 'params': {'sketch': 'Section', 'path_sketch': 'Path', 'path': ['l1']}},
        ])
        await check_capture(session, 1, (20, 2, 3), 120)
        edit = await session.tool('set_parameter', {'name': 'length', 'value': '24 mm'})
        assert not edit.get('errors')
        await check_capture(session, 2, (24, 2, 3), 144)


@pytest.mark.asyncio
async def test_native_mirror_and_parameter_edit(tmp_path, native_engine):
    async with SolidCraftSession(tmp_path, executable=native_engine) as session:
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'offset', 'expression': '10 mm'}},
            {'command': 'solid.box', 'params': {'length': 5, 'width': 5, 'height': 5,
                                               'corner': ['offset', 0, 0], 'body_name': 'Seed'}},
            {'command': 'solid.mirror', 'params': {'bodies': ['Seed'], 'plane': 'YZ', 'combine': False}},
        ])
        await check_capture(session, 1, (30, 5, 5), 250, body_count=2)
        edit = await session.tool('set_parameter', {'name': 'offset', 'value': '12 mm'})
        assert not edit.get('errors')
        await check_capture(session, 2, (34, 5, 5), 250, body_count=2)


@pytest.mark.asyncio
async def test_native_coil_and_parameter_edit(tmp_path, native_engine):
    """Measure the native screw sweep independently using its axial section."""
    async with SolidCraftSession(tmp_path, executable=native_engine, timeout=120) as session:
        observations = []
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'pitch', 'expression': '10 mm'}},
            {'command': 'solid.coil', 'params': {'diameter': 20, 'revolutions': 2,
                'pitch': 'pitch', 'section_size': 2, 'section': 'circular',
                'section_position': 'center', 'body_name': 'Helix'}},
        ])
        for revision, pitch in [(1, 10), (2, 12)]:
            if revision == 2:
                result = await session.tool('set_parameter', {'name': 'pitch', 'value': '12 mm'})
                assert not result.get('errors')
            capture = await session.capture('c' * 32, 'c' * 32, revision)
            assert capture.geometry.body_count == 1
            assert capture.geometry.closed_solid
            # Native 0.28.0 preserves the section in an axial plane during the
            # screw motion (kernel/helix.rs), rather than normal to its path.
            # The Jacobian integrates to area * angular travel * centroid radius.
            expected = math.pi * (2 * math.pi * 10) * 2
            observations.append({'pitch_mm': pitch, 'revision': revision,
                'source_sha256': capture.document.native.sha256,
                'volume_mm3': capture.geometry.volume_mm3, 'expected_volume_mm3': expected,
                'relative_error': abs(capture.geometry.volume_mm3 - expected) / expected})
            (tmp_path / 'coil-measurements.json').write_text(json.dumps({
                'engine_version': session.version, 'observations': observations}, indent=2))
        for observation in observations:
            assert observation['volume_mm3'] == pytest.approx(expected, rel=1e-5)


@pytest.mark.asyncio
async def test_native_bore_mouth_chamfer_and_parameter_edit(tmp_path, native_engine):
    """Qualify an editable native alternative to an explicit cone-mouth cut."""
    async with SolidCraftSession(tmp_path, executable=native_engine, timeout=120) as session:
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'chamfer', 'expression': '1 mm'}},
            {'command': 'solid.cylinder', 'params': {'radius': 8, 'height': 10, 'body_name': 'Sleeve'}},
            {'command': 'solid.cylinder', 'params': {'radius': 4, 'height': 10,
                'operation': 'cut', 'targets': ['Sleeve']}},
        ])
        # Observe the actual operand before selecting its bore mouth.
        topology = await session.tool('body_topology', {'body': 'Sleeve'})
        (tmp_path / 'mouth-operand.json').write_text(json.dumps(topology, indent=2))
        await session.batch([{'command': 'solid.chamfer', 'params': {
            'body': 'Sleeve', 'edges': [[4, 0, 10]], 'distance': 'chamfer'}}])
        for revision, distance in [(1, 1), (2, 1.5)]:
            if revision == 2:
                result = await session.tool('set_parameter', {'name': 'chamfer', 'value': '1.5 mm'})
                assert not result.get('errors')
            removed = math.pi * (4 * distance**2 + distance**3 / 3)
            await check_capture(session, revision, (16, 16, 10), math.pi * 48 * 10 - removed)


@pytest.mark.asyncio
async def test_native_rectangular_bend_sweep_and_parameter_edit(tmp_path, native_engine):
    """Exercise the curved rectangular-section family used by the supplied duct."""
    async with SolidCraftSession(tmp_path, executable=native_engine, timeout=120) as session:
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'bend', 'expression': '40 mm'}},
            {'command': 'sketch.create', 'params': {'plane': 'XY', 'name': 'BendPath'}},
            {'command': 'sketch.arc.center_point', 'params': {
                'center': ['-bend', 0], 'start': [0, 0], 'end': ['-bend', 'bend']}},
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'sketch.create', 'params': {'plane': 'XZ', 'name': 'DuctSection'}},
            {'command': 'sketch.rectangle.two_point', 'params': {
                'p0': [-3, -2], 'p1': [3, 2]}},
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'solid.sweep', 'params': {'sketch': 'DuctSection',
                'path_sketch': 'BendPath', 'path': ['a1'], 'body_name': 'BentSection'}},
        ])
        for revision, bend in [(1, 40), (2, 48)]:
            if revision == 2:
                result = await session.tool('set_parameter', {'name': 'bend', 'value': '48 mm'})
                assert not result.get('errors')
            await check_capture(session, revision, (bend + 3, bend + 3, 4), 24 * math.pi * bend / 2)


@pytest.mark.asyncio
@pytest.mark.parametrize('bend', [30, 60])
@pytest.mark.parametrize('extended', [False, True, 'aligned'], ids=['flush-tool', 'extended-tool', 'aligned-tool'])
async def test_native_outer_union_before_bore_and_parameter_edit(tmp_path, native_engine, bend, extended):
    """Keep the exact hollow geometry using an editable exterior-first feature order."""
    async with SolidCraftSession(tmp_path, executable=native_engine, timeout=120) as session:
        commands = [
            {'command': 'parameters.change', 'params': {'name': 'bend', 'expression': f'{bend} mm'}},
            {'command': 'sketch.create', 'params': {'plane': 'XY', 'name': 'Path'}},
            {'command': 'sketch.line', 'params': {'points': [['bend', -10], ['bend', 0]]}},
            {'command': 'sketch.arc.center_point', 'params': {'center': [0, 0], 'start': ['bend', 0],
                                                             'end': [0, 'bend']}},
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'solid.pipe', 'params': {'path_sketch': 'Path', 'path': ['l1', 'a1'],
                                                'diameter': 10, 'body_name': 'Exterior', 'name': 'OuterPipe'}},
            {'command': 'solid.cylinder', 'params': {'base': ['bend', -10, 0], 'axis': 'Y',
                                                    'radius': 8, 'height': 3, 'operation': 'new',
                                                    'body_name': 'Flange', 'name': 'OuterFlange'}},
            {'command': 'solid.combine', 'params': {'target': 'Exterior', 'tools': ['Flange'], 'operation': 'join'}},
        ]
        if extended:
            # Cutting beyond the part clears coincident end caps while leaving
            # the final part's material and dimensions unchanged.
            commands += [
                {'command': 'sketch.create', 'params': {'plane': 'XY', 'name': 'BorePath'}},
                {'command': 'sketch.line', 'params': {'points': [['bend', -12], ['bend', 0]]}},
                {'command': 'sketch.arc.center_point', 'params': {'center': [0, 0], 'start': ['bend', 0],
                                                                 'end': [0, 'bend']}},
                {'command': 'sketch.line', 'params': {'points': [[0, 'bend'], [-2, 'bend']]}},
                {'command': 'sketch.finish', 'params': {}},
            ]
        commands.append({'command': 'solid.pipe', 'params': {
            'path_sketch': 'BorePath' if extended else 'Path',
            'path': ['l1', 'a1', 'l2'] if extended else ['l1', 'a1'],
            'diameter': 8, 'operation': 'cut', 'targets': ['Exterior'], 'name': 'ContinuousBore'}})
        try:
            if extended:
                from bigbrain.cad_cut_contracts import CutIntent
                from bigbrain.cad_cut_safety import guarded_cut

                await session.batch(commands[:-1])
                intent = CutIntent.model_validate({
                    'id': 'continuous-bore', 'command_index': len(commands) - 1,
                    'feature_id': 'passage', 'dimension_ids': ['bore'],
                    'kind': 'through', 'targets': ['Exterior'],
                    'boundaries': [
                        {'label': 'inlet', 'origin_mm': ['bend', -10, 2],
                         'outward_normal': [0, -1, 0], 'role': 'opening',
                         'alignment_tolerance_mm': 0.05 if extended == 'aligned' else 0},
                        {'label': 'outlet', 'origin_mm': [0, 'bend', 2],
                         'outward_normal': [-1, 0, 0], 'role': 'opening',
                         'alignment_tolerance_mm': 0.05 if extended == 'aligned' else 0},
                    ],
                })
                await guarded_cut(session, commands[-1], intent, parameter_names=['bend'])
            else:
                await session.batch(commands)
        finally:
            (tmp_path / 'construction-trace.json').write_text(json.dumps(session.observations, indent=2))
        for revision, radius in [(1, bend), (2, bend + 6)]:
            if revision == 2:
                edit = await session.tool('set_parameter', {'name': 'bend', 'value': f'{radius} mm'})
                assert not edit.get('errors')
            capture = await check_capture(session, revision, (radius + 8, radius + 15, 16),
                                          math.pi * (9 * (math.pi * radius / 2 + 10) + 117))
            step = next(item for item in capture.document.exports if item.format == 'step')
            material = check_bore_material(session.scratch / step.path, radius)
            (tmp_path / f'revision-{revision}' / 'local-material-checks.json').write_text(json.dumps(material, indent=2))
            # The final bore is a native feature retained through the parameter edit.
            design = await session.tool('inspect_design', {'sketches': False})
            (tmp_path / f'revision-{revision}' / 'native-design.json').write_text(json.dumps(design, indent=2))
            assert any(feature.get('name') == 'ContinuousBore' for feature in design['timeline'])
            assert not any(feature.get('error') for feature in design['timeline'])
@pytest.mark.asyncio
async def test_native_rounded_profile_constraints_and_parameter_edit(tmp_path, native_engine):
    """Numeric placement and functional dimensions remain editable and solved."""
    async with SolidCraftSession(tmp_path, executable=native_engine, timeout=120) as session:
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'width', 'expression': '360 mm'}},
            {'command': 'parameters.change', 'params': {'name': 'corner', 'expression': '20 mm'}},
            {'command': 'sketch.create', 'params': {'plane': 'XY', 'name': 'RoundedProfile'}},
            {'command': 'sketch.draw.dimensioned', 'params': {
                'command': 'sketch.rectangle.rounded',
                'params': {'p0': [-180, -180], 'p1': [180, 180], 'radius': 'corner'},
                'dimensions': {'width': 'width', 'height': 'width'}, 'locate': True}},
            {'command': 'sketch.finish', 'params': {}},
        ])
        state = await session.tool('inspect_design')
        assert state['sketches'][0]['fully_constrained']
        await session.batch([{'command': 'solid.extrude', 'params': {
            'sketch': 'RoundedProfile', 'distance': 50, 'body_name': 'RoundedPlate'}}])
        for revision, width, radius in [(1, 360, 20), (2, 380, 20), (3, 380, 25)]:
            if revision > 1:
                changed = await session.tool('set_parameter', {
                    'name': 'width' if revision == 2 else 'corner',
                    'value': '380 mm' if revision == 2 else '25 mm'})
                assert not changed.get('errors')
            await check_capture(session, revision, (width, width, 50),
                                (width**2 - (4 - math.pi) * radius**2) * 50)

@pytest.mark.asyncio
async def test_native_revolve_with_parametric_datum_axis(tmp_path, native_engine):
    """A named native datum axis follows both radius and axial-plane edits."""
    async with SolidCraftSession(tmp_path, executable=native_engine, timeout=120) as session:
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'major', 'expression': '260 mm'}},
            {'command': 'parameters.change', 'params': {'name': 'height', 'expression': '150 mm'}},
            {'command': 'parameters.change', 'params': {'name': 'diameter', 'expression': '290 mm'}},
            {'command': 'construct.plane.offset', 'params': {'base': 'YZ', 'offset': 'major', 'name': 'RadialDatum'}},
            {'command': 'construct.plane.offset', 'params': {'base': 'XY', 'offset': 'height', 'name': 'AxialDatum'}},
            {'command': 'construct.axis.two_planes', 'params': {'a': 'AxialDatum', 'b': 'RadialDatum', 'name': 'SweepAxis'}},
            {'command': 'sketch.create', 'params': {'plane': 'AxialDatum', 'name': 'TubeProfile'}},
            {'command': 'sketch.draw.dimensioned', 'params': {'command': 'sketch.circle.center',
                'params': {'center': [0, 0], 'diameter': 290},
                'dimensions': {'diameter': 'diameter'}, 'locate': True}},
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'solid.revolve', 'params': {'sketch': 'TubeProfile', 'axis': 'SweepAxis',
                'angle': '90 deg', 'body_name': 'QuarterBend'}},
        ])
        previous = None
        for revision, major, height in [(1, 260, 150), (2, 280, 150), (3, 280, 170)]:
            if revision > 1:
                changed = await session.tool('set_parameter', {
                    'name': 'major' if revision == 2 else 'height',
                    'value': '280 mm' if revision == 2 else '170 mm'})
                assert not changed.get('errors')
            state = await session.tool('inspect_design')
            assert state['sketches'][0]['fully_constrained']
            assert state['sketches'][0]['plane']['origin'][2] == pytest.approx(height)
            capture = await check_capture(session, revision, (major + 145, 290, major + 145),
                                         math.pi * 145**2 * math.pi * major / 2)
            if revision == 3:
                assert capture.geometry.bounds_min_mm[2] - previous.geometry.bounds_min_mm[2] == pytest.approx(20)
            previous = capture
