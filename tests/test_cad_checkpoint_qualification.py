"""Native save/reopen and dependency checks for progressive CAD recovery."""

import pytest

from bigbrain.solidcraft import SolidCraftSession


@pytest.mark.asyncio
async def test_native_checkpoint_reopens_parameters_sketch_and_downstream_edit(tmp_path, cad_native_engine):
    commands = [
        {'command': 'parameters.change', 'params': {'name': 'width', 'expression': '20 mm'}},
        {'command': 'sketch.create', 'params': {'plane': 'XY', 'name': 'BaseProfile'}},
        {'command': 'sketch.draw.dimensioned', 'params': {
            'command': 'sketch.rectangle.two_point', 'params': {'p0': [0, 0], 'p1': [20, 10]},
            'dimensions': {'width': 'width', 'height': 10}, 'locate': True}},
        {'command': 'sketch.finish', 'params': {}},
        {'command': 'solid.extrude', 'params': {'sketch': 'BaseProfile', 'distance': 5,
                                              'body_name': 'Base'}},
    ]
    async with SolidCraftSession(tmp_path) as session:
        await session.batch(commands)
        before = await session.capture('a' * 32, 'a' * 32, 1)
        design = await session.tool('inspect_design')
    async with SolidCraftSession(tmp_path) as recovered:
        await recovered.reopen(before.document.native)
        reopened = await recovered.tool('inspect_design')
        assert reopened['sketches'] == design['sketches']
        assert reopened['params'] == design['params']
        capture = await recovered.capture('a' * 32, 'a' * 32, 2)
        assert capture.geometry.volume_mm3 == pytest.approx(1000, abs=0.001)
        result = await recovered.tool('set_parameter', {'name': 'width', 'value': '24 mm'})
        assert not result.get('errors')
        edited = await recovered.capture('a' * 32, 'a' * 32, 3)
        assert edited.geometry.volume_mm3 == pytest.approx(1200, abs=0.001)
        assert edited.geometry.bounds_max_mm == pytest.approx((24, 10, 5), abs=0.001)
        # The original saved revision remains usable after later edits.
        await recovered.reopen(before.document.native)
        restored = await recovered.capture('a' * 32, 'a' * 32, 4)
        assert restored.geometry.volume_mm3 == pytest.approx(1000, abs=0.001)


@pytest.mark.asyncio
async def test_native_checkpoint_rejects_changed_bytes(tmp_path, cad_native_engine):
    async with SolidCraftSession(tmp_path) as session:
        await session.batch([{'command': 'solid.box', 'params': {'length': 10, 'width': 10, 'height': 5}}])
        capture = await session.capture('b' * 32, 'b' * 32, 1)
    path = tmp_path / capture.document.native.path
    path.write_bytes(path.read_bytes() + b'\n')
    from bigbrain.solidcraft import CadError
    async with SolidCraftSession(tmp_path) as recovered:
        with pytest.raises(CadError, match='changed before reopening'):
            await recovered.reopen(capture.document.native)
