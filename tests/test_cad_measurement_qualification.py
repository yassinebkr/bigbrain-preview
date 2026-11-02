"""Qualify local measurements against analytic reference solids and defects."""

import json
import math

import pytest

from bigbrain.cad_sections import CadSection, observe_section, read_triangles
from bigbrain.cad_surfaces import CadCylinder
from bigbrain.solidcraft import CadError, SolidCraftSession, solidcraft_executable


@pytest.fixture
def executable():
    try:
        return solidcraft_executable()
    except CadError:
        pytest.skip('Native SolidCraft installation required for qualification')


def box(length, width, height):
    return {'command': 'solid.box', 'params': {
        'length': length, 'width': width, 'height': height, 'body_name': 'reference'}}


def bore(radius, depth, base):
    return {'command': 'solid.cylinder', 'params': {
        'radius': radius, 'height': depth, 'base': base,
        'operation': 'cut', 'targets': ['reference']}}


CASES = {
    'through': {
        'commands': [box(60, 40, 12), bore(5, 12, [20, 20, 0])],
        'sections': [(0, [0, 20, 4], [(0, 15), (25, 60)]),
                     (2, [20, 20, 0], []), (2, [10, 10, 0], [(0, 12)])],
        'volume': 60 * 40 * 12 - math.pi * 25 * 12,
        'radius': 5, 'center': [20, 20, 0],
    },
    'counterbore': {
        'commands': [box(60, 40, 12), bore(5, 12, [20, 20, 0]), bore(9, 4, [20, 20, 8])],
        'sections': [(0, [0, 20, 4], [(0, 15), (25, 60)]),
                     (0, [0, 20, 10], [(0, 11), (29, 60)]),
                     (2, [27, 20, 0], [(0, 8)]), (2, [20, 20, 0], [])],
        'volume': 60 * 40 * 12 - math.pi * (25 * 12 + (81 - 25) * 4),
        'radius': 9, 'center': [20, 20, 0],
    },
    'partial80': {
        'commands': [box(170, 66, 35), bore(40, 18, [110, 33, 0])],
        'sections': [(0, [0, y, 9], [(0, 110 - math.sqrt(1600 - (y - 33)**2)),
                                    (110 + math.sqrt(1600 - (y - 33)**2), 170)])
                     for y in (5, 17, 33, 49, 61)] +
                    [(2, [110, 33, 0], [(18, 35)]), (2, [60, 33, 0], [(0, 35)])],
        # Integral of the clipped circular strip over y = -33 .. 33.
        'volume': 170 * 66 * 35 - 18 * (66 * math.sqrt(1600 - 33**2) + 3200 * math.asin(33 / 40)),
        'radius': 40, 'center': [110, 33, 0],
    },
}


@pytest.mark.asyncio
@pytest.mark.parametrize('case', CASES)
async def test_native_measurement_reference_and_wrong_targets(tmp_path, case, executable):
    reference = CASES[case]
    async with SolidCraftSession(tmp_path, executable=executable) as engine:
        await engine.batch(reference['commands'])
        topology = await engine.tool('body_topology', {'body': 'reference'})
        capture = await engine.capture('qualification', case, 1)
    source = capture.document.native.sha256
    triangles = read_triangles(tmp_path / next(a.path for a in capture.document.exports if a.format == 'stl'))
    report = {'case': case, 'engine': capture.document.engine_version,
              'source_sha256': source, 'topology': topology, 'sections': []}
    errors = []
    for index, (axis, point, expected) in enumerate(reference['sections']):
        section = CadSection(id=f'probe{index}', label=f'{case} reference {index}',
            axis=axis, point_mm=point, intervals_mm=expected, absolute_tolerance_mm=0.05)
        check, actual = observe_section(section, triangles, source_sha256=source, evidence_ref='qualification.json')
        assert check.status == 'passed', check
        error = max((abs(a-b) for measured, target in zip(actual, expected)
                     for a, b in zip(measured, target)), default=0)
        errors.append(error)
        # A one-millimetre error must fail, including an unwanted floor in a bore.
        wrong = [(a, b + 1) for a, b in expected] if expected else [(0, 1)]
        bad = section.model_copy(update={'intervals_mm': tuple(wrong)})
        rejected, _ = observe_section(bad, triangles, source_sha256=source, evidence_ref='qualification.json')
        assert rejected.status == 'failed'
        report['sections'].append({'observed': actual, 'expected': expected, 'max_error_mm': error,
                                   'wrong_target_status': rejected.status})
    cylinder = CadCylinder(id='radius', label='Native radius and axis', body='reference',
        axis=2, radius_mm=reference['radius'], center_mm=reference['center'])
    observed = cylinder.observe(topology, source_sha256=source, evidence_ref='qualification.json')
    # Approximate native topology retains its uncertainty even when sections pass.
    assert observed.status in {'passed', 'inconclusive'}, observed
    if observed.status == 'passed':
        wrong = cylinder.model_copy(update={'radius_mm': reference['radius'] + 1})
        assert wrong.observe(topology, source_sha256=source, evidence_ref='qualification.json').status == 'failed'
    volume_error = abs(capture.geometry.volume_mm3 - reference['volume'])
    assert volume_error < 1e-6
    precise = cylinder.observe(capture.measurements['bodies']['reference'],
        source_sha256=source, evidence_ref='measurement-inspection.json')
    assert precise.status == 'passed'
    assert precise.observed == pytest.approx(cylinder.target(), abs=1e-9)
    from bigbrain.cad_step import inspect_step
    native_measure = json.loads((tmp_path / capture.document.native.path).with_name('measure.json').read_text())
    step = tmp_path / next(a.path for a in capture.document.exports if a.format == 'step')
    with pytest.raises(ValueError, match='solid count'):
        inspect_step(step, native_measure['bodies'] * 2)
    # Tangent and boundary lines carry no stable material-thickness evidence.
    boundary = CadSection(id='boundary', label='Boundary', axis=0,
        point_mm=[0, 0, 0], intervals_mm=[])
    ambiguous, _ = observe_section(boundary, triangles, source_sha256=source, evidence_ref='qualification.json')
    assert ambiguous.status == 'inconclusive'
    report.update(max_section_error_mm=max(errors), volume_error_mm3=volume_error,
                  native_volume_error_mm3=abs(native_measure['total']['volume_mm3'] - reference['volume']),
                  volume_within_0_01_mm3=volume_error <= 0.01,
                  step_cylinder=precise.model_dump(mode='json'),
                  cylinder=observed.model_dump(mode='json'), boundary_status=ambiguous.status)
    (tmp_path / 'qualification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')

    # Exercise each section axis and translated coordinates on the same mesh.
    # This qualifies coordinate handling in the section algorithm.
    axis, point, expected = reference['sections'][0]
    for order in ((0, 1, 2), (2, 0, 1), (1, 2, 0)):
        translation = (123.25, -57.5, 11.75)
        transformed = [tuple(tuple(vertex[order[i]] + translation[i] for i in range(3))
                             for vertex in triangle) for triangle in triangles]
        new_axis = order.index(axis)
        new_point = [point[order[i]] + translation[i] for i in range(3)]
        offset = translation[new_axis]
        target = [(a + offset, b + offset) for a, b in expected]
        probe = CadSection(id='transformed', label='Transformed mesh section', axis=new_axis,
                           point_mm=new_point, intervals_mm=target)
        result, _ = observe_section(probe, transformed, source_sha256=source, evidence_ref='qualification.json')
        assert result.status == 'passed', result


@pytest.mark.asyncio
async def test_blind_bore_fails_through_requirement(tmp_path, executable):
    async with SolidCraftSession(tmp_path, executable=executable) as engine:
        await engine.batch([box(60, 40, 12), bore(5, 11, [20, 20, 1])])
        capture = await engine.capture('qualification', 'blind-defect', 1)
    triangles = read_triangles(tmp_path / next(a.path for a in capture.document.exports if a.format == 'stl'))
    check, actual = observe_section(CadSection(id='through', label='Through required',
        axis=2, point_mm=[20, 20, 0], intervals_mm=[]), triangles,
        source_sha256=capture.document.native.sha256, evidence_ref='qualification.json')
    assert check.status == 'failed'
    assert actual == pytest.approx([(0, 1)])


def test_step_reader_rejects_invalid_artifact(tmp_path):
    pytest.importorskip('OCP')
    from bigbrain.cad_step import inspect_step
    path = tmp_path / 'invalid.step'
    path.write_text('invalid STEP', encoding='utf-8')
    with pytest.raises(ValueError, match='rejected'):
        inspect_step(path, [])
