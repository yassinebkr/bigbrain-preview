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
