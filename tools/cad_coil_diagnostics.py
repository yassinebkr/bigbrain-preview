"""Native coil experiments, invoked explicitly with pytest on this file.

These diagnostic cases retain unsuccessful native alternatives. Their strict
analytic-volume assertions expose the remaining defect. The application test
suite retains the original coil qualification case separately.
"""

import json
import math
import os

import pytest

from bigbrain.solidcraft import SolidCraftSession


@pytest.mark.asyncio
async def test_native_checkpoint_rejects_different_executable(tmp_path):
    """Exercise same-version build separation with two real native binaries."""
    from bigbrain.cad_execution import CadExecutionStore
    from bigbrain.solidcraft import CadError
    from tests.test_cad_execution import accept, group

    baseline = os.environ.get('BIGBRAIN_SOLIDCRAFT_BASELINE_CLI')
    if not baseline:
        pytest.skip('Explicit baseline executable required for build comparison')
    store = CadExecutionStore(tmp_path, 'a' * 64)
    async with SolidCraftSession(tmp_path, executable=baseline) as original:
        record = await store.execute(original, group(), validate=accept)
    before = store.head.read_bytes()
    async with SolidCraftSession(tmp_path) as candidate:
        assert candidate.version == record.engine_version
        assert candidate.engine_sha256 != record.engine_sha256
        with pytest.raises(CadError, match='executable changed'):
            await CadExecutionStore(tmp_path, 'a' * 64).recover(candidate)
        assert not candidate.observations
    assert store.head.read_bytes() == before
    async with SolidCraftSession(tmp_path, executable=baseline) as original:
        restored = await CadExecutionStore(tmp_path, 'a' * 64).recover(original)
        assert restored.id == record.id


@pytest.mark.asyncio
@pytest.mark.parametrize('diameter,section,turns,pitch', [
    (20, 2, 2, 10), (40, 4, 3, 8), (12, 1, 0.5, 6),
    (30, 3, 1.25, 9), (20, 2, 2, -10), (20, 2, 0.25, 10),
    (20, 2, 7, 10),
])
async def test_native_coil_precision_matrix(tmp_path, diameter, section, turns, pitch):
    """Compare exported geometry after construction, parameter edit and reopen.

    BIGBRAIN_SOLIDCRAFT_CLI selects an isolated candidate explicitly. Keeping
    this outside automatic collection permits baseline/candidate comparisons
    while the installed engine retains its known precision limitation.
    """
    reports = []
    async with SolidCraftSession(tmp_path, timeout=120) as session:
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'pitch', 'expression': f'{pitch} mm'}},
            {'command': 'solid.coil', 'params': {'diameter': diameter, 'revolutions': turns,
                'pitch': 'pitch', 'section_size': section, 'section': 'circular',
                'section_position': 'center', 'body_name': 'Helix'}},
        ])
        for revision, value in [(1, pitch), (2, pitch * 1.2)]:
            if revision == 2:
                result = await session.tool('set_parameter', {'name': 'pitch', 'value': f'{value} mm'})
                assert not result.get('errors')
            capture = await session.capture('f' * 32, 'f' * 32, revision)
            expected = math.pi * (section / 2)**2 * math.pi * diameter * turns
            reports.append({'revision': revision, 'pitch_mm': value,
                'volume_mm3': capture.geometry.volume_mm3, 'expected_volume_mm3': expected,
                'relative_error': abs(capture.geometry.volume_mm3 - expected) / expected,
                'closed_solid': capture.geometry.closed_solid,
                'body_count': capture.geometry.body_count})
    async with SolidCraftSession(tmp_path, timeout=120) as session:
        await session.reopen(capture.document.native)
        reopened = await session.capture('f' * 32, 'f' * 32, 3)
        reports.append({'revision': 3, 'volume_mm3': reopened.geometry.volume_mm3,
            'expected_volume_mm3': expected,
            'relative_error': abs(reopened.geometry.volume_mm3 - expected) / expected,
            'closed_solid': reopened.geometry.closed_solid,
            'body_count': reopened.geometry.body_count})
    (tmp_path / 'precision-matrix.json').write_text(json.dumps(reports, indent=2))
    for report in reports:
        assert report['closed_solid'] and report['body_count'] == 1
        assert report['volume_mm3'] == pytest.approx(expected, rel=1e-5)


@pytest.mark.asyncio
@pytest.mark.parametrize('segments', [1, 8])
async def test_native_quarter_coil_precision(tmp_path, segments):
    """Smaller native sweeps increase the kernel's minimum station density."""
    async with SolidCraftSession(tmp_path, timeout=120) as session:
        await session.batch([{'command': 'parameters.change', 'params': {
            'name': 'pitch', 'expression': '10 mm'}}])
        reports = []
        for index in range(segments):
            await session.batch([{'command': 'solid.coil', 'params': {
                'diameter': 20, 'revolutions': 0.25, 'pitch': 'pitch', 'section_size': 2,
                'section': 'circular', 'section_position': 'center', 'start_angle': index * 90,
                'base': [0, 0, f'pitch*{index}/4'], 'body_name': 'Helix',
                'operation': 'new' if index == 0 else 'join',
                **({'targets': ['Helix']} if index else {})}}])
            await session.tool('save', {'path': str(tmp_path / f'quarter-{index}.sc')})
        for revision, pitch in [(1, 10), (2, 12)]:
            if revision == 2:
                result = await session.tool('set_parameter', {'name': 'pitch', 'value': '12 mm'})
                assert not result.get('errors')
            capture = await session.capture('d' * 32, 'd' * 32, revision)
            expected = math.pi * (2 * math.pi * 10) * segments / 4
            reports.append({'pitch_mm': pitch, 'expected_volume_mm3': expected,
                'geometry': capture.geometry.model_dump(mode='json')})
            (tmp_path / 'quarter-coil-measurements.json').write_text(json.dumps(reports, indent=2))
            assert capture.geometry.body_count == 1
            assert capture.geometry.closed_solid
            assert capture.geometry.volume_mm3 == pytest.approx(expected, rel=1e-5)


@pytest.mark.asyncio
@pytest.mark.parametrize('arcs', [4, 8])
async def test_native_coil_with_subdivided_circular_profile(tmp_path, arcs):
    """Separate section interpolation error from helical station interpolation."""
    async with SolidCraftSession(tmp_path, timeout=120) as session:
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'pitch', 'expression': '10 mm'}},
            {'command': 'sketch.create', 'params': {'plane': 'XZ', 'name': 'AxialSection'}},
        ])
        points = [[10 + math.cos(2 * math.pi * i / arcs), math.sin(2 * math.pi * i / arcs)]
                  for i in range(arcs)]
        await session.batch([{'command': 'sketch.arc.center_point', 'params': {
            'center': [10, 0], 'start': points[i], 'end': points[(i + 1) % arcs]}}
            for i in range(arcs)] + [
            {'command': 'sketch.finish', 'params': {}},
            {'command': 'solid.coil', 'params': {'sketch': 'AxialSection',
                'revolutions': 2, 'pitch': 'pitch', 'body_name': 'Helix'}},
        ])
        for revision, pitch in [(1, 10), (2, 12)]:
            if revision == 2:
                result = await session.tool('set_parameter', {'name': 'pitch', 'value': '12 mm'})
                assert not result.get('errors')
            capture = await session.capture('e' * 32, 'e' * 32, revision)
            expected = 40 * math.pi**2
            (tmp_path / f'profile-coil-measurements-{revision}.json').write_text(json.dumps({
                'arcs': arcs, 'pitch_mm': pitch, 'expected_volume_mm3': expected,
                'geometry': capture.geometry.model_dump(mode='json')}, indent=2))
            assert capture.geometry.body_count == 1
            assert capture.geometry.closed_solid
            assert capture.geometry.volume_mm3 == pytest.approx(expected, rel=1e-5)
