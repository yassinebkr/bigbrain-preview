"""Independent material sections distinguish local geometry with equal volume."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from bigbrain.cad_planning import CadPlan
from bigbrain.cad_sections import CadSection, observe_section, read_triangles
from bigbrain.solidcraft import CadError, SolidCraftSession, solidcraft_executable


def section(**changes):
    return CadSection.model_validate({'id': 'hole', 'label': 'Hole diameter and position',
        'axis': 0, 'point_mm': [0, 20, 3], 'intervals_mm': [[0, 12], [18, 60]], **changes})


@pytest.mark.parametrize('intervals', [[[0, 10], [5, 20]], [[5, 5]], [[10, 0]], [[0, float('inf')]]])
def test_invalid_sections(intervals):
    with pytest.raises(ValidationError):
        section(intervals_mm=intervals)


@pytest.mark.parametrize('axis', [True, False, -1, 3, 1.0, '1'])
def test_section_axis_requires_an_explicit_world_axis(axis):
    with pytest.raises(ValidationError):
        section(axis=axis)


@pytest.mark.asyncio
async def test_real_hole_sections_distinguish_equal_volume_relocation(tmp_path):
    try:
        executable = solidcraft_executable()
    except CadError:
        pytest.skip('SolidCraft 0.28.0 is required')
    volumes = []
    for revision, x in enumerate((15, 30), start=1):
        async with SolidCraftSession(tmp_path, executable=executable) as engine:
            await engine.batch([
                {'command': 'solid.box', 'params': {'length': 60, 'width': 40, 'height': 6, 'body_name': 'plate'}},
                {'command': 'solid.cylinder', 'params': {'radius': 3, 'height': 6,
                    'base': [x, 20, 0], 'operation': 'cut', 'targets': ['plate']}}])
            capture = await engine.capture('project', 'piece', revision)
        volumes.append(capture.geometry.volume_mm3)
        stl = next(item for item in capture.document.exports if item.format == 'stl')
        triangles = read_triangles(tmp_path / stl.path)
        observation, intervals = observe_section(section(), triangles,
            source_sha256=capture.document.native.sha256, evidence_ref='sections.json')
        assert observation.status == ('passed' if x == 15 else 'failed')
        assert len(intervals) == 2
        # A second direction verifies through depth at the hole axis.
        through, intervals = observe_section(section(axis=2, point_mm=[15, 20, 0], intervals_mm=[]),
            triangles, source_sha256=capture.document.native.sha256, evidence_ref='sections.json')
        assert through.status == ('passed' if x == 15 else 'failed')
    assert volumes[0] == pytest.approx(volumes[1], abs=0.1)


def test_drawing_targets_require_coverage_and_exact_unit_conversion():
    from tests.test_cad_drawings import drawing
    from tests.test_cad_integration import recipe
    data = recipe()
    data['drawing'] = drawing()
    with pytest.raises(ValidationError, match='measurement binding'):
        CadPlan.model_validate(data)
    data['criteria'][0]['dimension_bindings'] = {'width': 0}
    assert CadPlan.model_validate(data).drawing
    bad = deepcopy(data)
    bad['drawing']['dimensions'][0]['unit'] = 'inch'
    with pytest.raises(ValidationError, match='differs'):
        CadPlan.model_validate(bad)
    data['drawing']['dimensions'][0].update(value=60 / 25.4, unit='inch')
    assert CadPlan.model_validate(data).drawing


def test_section_gap_binds_a_hole_diameter():
    from tests.test_cad_drawings import drawing
    from tests.test_cad_integration import recipe
    data = recipe()
    data['drawing'] = drawing()
    data['drawing']['dimensions'][0].update(id='diameter', kind='diameter', value=6)
    data['sections'] = [section(bindings=[{'dimension_id': 'diameter', 'quantity': 'gap', 'interval': 0}]).model_dump()]
    assert CadPlan.model_validate(data).sections[0].quantity(CadPlan.model_validate(data).sections[0].bindings[0]) == 6
    data['sections'][0]['intervals_mm'] = [[0, 12], [20, 60]]
    with pytest.raises(ValidationError, match='differs'):
        CadPlan.model_validate(data)


@pytest.mark.asyncio
async def test_rounded_profile_and_ambiguous_boundary(tmp_path):
    try:
        executable = solidcraft_executable()
    except CadError:
        pytest.skip('SolidCraft 0.28.0 is required')
    async with SolidCraftSession(tmp_path, executable=executable) as engine:
        await engine.batch([
            {'command': 'sketch.create', 'params': {'plane': 'XY'}},
            {'command': 'sketch.rectangle.rounded', 'params': {'p0': [0, 0], 'p1': [60, 40], 'radius': 5}},
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'solid.extrude', 'params': {'distance': 6}}])
        capture = await engine.capture('project', 'rounded', 1)
    stl = next(item for item in capture.document.exports if item.format == 'stl')
    triangles = read_triangles(tmp_path / stl.path)
    observed, actual = observe_section(section(point_mm=[0, 1, 3], intervals_mm=[[2, 58]]), triangles,
        source_sha256=capture.document.native.sha256, evidence_ref='sections.json')
    assert observed.status == 'passed', (observed, actual)
    observed, _ = observe_section(section(point_mm=[0, 20, 6], intervals_mm=[[0, 60]]), triangles,
        source_sha256=capture.document.native.sha256, evidence_ref='sections.json')
    assert observed.status == 'inconclusive'


@pytest.mark.parametrize('packet', [b'', b'x' * 84, b'x' * 100])
def test_invalid_stl_stops_measurement(tmp_path, packet):
    path = tmp_path / 'invalid.stl'
    path.write_bytes(packet)
    with pytest.raises(ValueError, match='STL'):
        read_triangles(path)


def test_step_rise_binds_the_difference_of_two_measured_sections():
    from tests.test_cad_drawings import drawing
    from tests.test_cad_integration import recipe
    data = recipe()
    spec = drawing()
    rise = deepcopy(spec['dimensions'][0])
    rise.update(id='rise', value=12, origin='derived', dependencies=['total_height', 'base_thickness'],
                derivation='total_height - base_thickness')
    height = {**deepcopy(spec['dimensions'][0]), 'id': 'total_height', 'value': 20}
    base = {**deepcopy(spec['dimensions'][0]), 'id': 'base_thickness', 'kind': 'depth', 'value': 8}
    spec['dimensions'].extend([height, base, rise])
    data['drawing'] = spec
    data['criteria'][0]['expected'] = [60, 40, 20]
    data['criteria'][0]['dimension_bindings'] = {'width': 0, 'total_height': 2}
    data['sections'] = [
        section(id='top', axis=2, point_mm=[10, 10, 0], intervals_mm=[[0, 20]],
            bindings=[{'dimension_id': 'rise', 'quantity': 'length', 'interval': 0,
                       'subtract': {'section_id': 'base', 'quantity': 'length', 'interval': 0}}]).model_dump(),
        section(id='base', axis=2, point_mm=[30, 10, 0], intervals_mm=[[0, 8]],
            bindings=[{'dimension_id': 'base_thickness', 'quantity': 'length', 'interval': 0}]).model_dump()]
    assert CadPlan.model_validate(data).sections[0].bindings[0].subtract.section_id == 'base'
    data['sections'][1]['intervals_mm'] = [[0, 9]]
    with pytest.raises(ValidationError, match='differs'):
        CadPlan.model_validate(data)
