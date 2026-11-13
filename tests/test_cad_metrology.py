"""Provider replacement preserves revision, units and acceptance evidence."""

from pathlib import Path

import pytest

from bigbrain.cad_metrology import MeasurementRouter, MeasurementSource, NativeMeasurements


def source():
    return MeasurementSource('a'*64, Path('folder with spaces/part.step'), 'b'*64, [{'name': 'part'}])


class Provider:
    name = 'future-native'
    capabilities = frozenset({'cylinders', 'volume', 'bounds', 'vertices', 'solid_validity'})
    def __init__(self, **changes):
        self.calls = 0
        self.changes = changes
    async def inspect(self, source, session):
        self.calls += 1
        return {'units': 'mm', 'source_sha256': source.native_sha256, 'bodies': {
            'part': {'faces': [], 'edges': [], 'bounds_min_mm': [0,0,0],
                     'bounds_max_mm': [1,2,3], 'volume_mm3': 6}}, **self.changes}


@pytest.mark.asyncio
async def test_qualified_future_native_provider_replaces_step_without_worker_changes():
    native, unused = Provider(), Provider()
    unused.name = 'unused-step'
    result = await MeasurementRouter([native, unused]).inspect(source(), None)
    assert result['volume_mm3'] == 6
    assert set(result['capabilities'].values()) == {'future-native'}
    assert native.calls == 1 and unused.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [{'units': 'inch'}, {'source_sha256': 'c'*64}, {'bodies': {}}])
async def test_provider_cannot_change_units_revision_or_body_inventory(change):
    with pytest.raises(ValueError, match='inconsistent'):
        await MeasurementRouter([Provider(**change)]).inspect(source(), None)


@pytest.mark.asyncio
async def test_missing_capability_stops_before_any_measurement():
    native = Provider()
    native.capabilities = frozenset({'cylinders'})
    with pytest.raises(ValueError, match='volume'):
        await MeasurementRouter([native]).inspect(source(), None)
    assert native.calls == 0


@pytest.mark.asyncio
async def test_native_cylinder_geometry_is_independent_of_face_name_history():
    class Session:
        async def tool(self, name, arguments):
            assert name == 'body_topology'
            return {'body': 'part', 'faces': [{'exact': False,
                'cylinder': {'radius': 40, 'axis': [0,0,1], 'origin': [0,0,0]}}]}
    result = await NativeMeasurements().inspect(source(), Session())
    assert result['bodies']['part']['faces'][0]['analytic_surface'] is True


def test_configured_executable_accepts_spaces_and_windows_extension(tmp_path, monkeypatch):
    from bigbrain.solidcraft import solidcraft_executable
    folder = tmp_path / 'Program Files' / 'SolidCraft'
    folder.mkdir(parents=True)
    executable = folder / 'solidcraft-cli.exe'
    executable.touch()
    monkeypatch.setenv('BIGBRAIN_SOLIDCRAFT_CLI', str(executable))
    assert solidcraft_executable() == executable.resolve()


def test_missing_step_dependency_returns_an_actionable_diagnostic(monkeypatch):
    import builtins
    from bigbrain.cad_step import inspect_step
    original = builtins.__import__
    def unavailable(name, *args, **kwargs):
        if name.startswith('OCP'):
            raise ImportError('qualification dependency unavailable')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', unavailable)
    with pytest.raises(ValueError, match='cadquery-ocp-novtk'):
        inspect_step(Path('part.step'), [])


@pytest.mark.asyncio
async def test_section_provider_replacement_retains_revision_and_probe_identity():
    from bigbrain.cad_sections import CadSection
    probe = CadSection(id='wall', label='Wall', axis=2, point_mm=(0, 0, 0))
    class Sections:
        name = 'future-native-sections'
        capabilities = frozenset({'sections'})
        async def sections(self, source, sections):
            assert sections == [probe]
            return {'method': self.name, 'units': 'mm',
                    'source_sha256': source.native_sha256, 'step_sha256': source.step_sha256,
                    'probes': {'wall': {'intervals_mm': ((0, 5),)}}}
    result = await MeasurementRouter([Sections()]).sections(source(), [probe])
    assert result['method'] == 'future-native-sections'
    assert result['probes']['wall']['intervals_mm'] == ((0, 5),)
    with pytest.raises(ValueError, match='No qualified.*sections'):
        await MeasurementRouter([Provider()]).sections(source(), [probe])
