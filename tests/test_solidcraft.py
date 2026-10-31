"""Real headless geometry and bounded transport checks on disposable projects."""

import asyncio
import math
from pathlib import Path
import sys

import pytest

from bigbrain.solidcraft import CadError, SolidCraftSession, solidcraft_executable


@pytest.fixture
def engine():
    try:
        return solidcraft_executable()
    except CadError:
        pytest.skip('Native SolidCraft 0.28.0 installation is required')


def command(command_id, **params):
    return {'command': command_id, 'params': params}


@pytest.mark.asyncio
async def test_real_plate_edit_exports_and_failed_batch_preserve_revision(tmp_path, engine):
    async with SolidCraftSession(tmp_path, executable=engine) as session:
        await session.batch([
            command('parameters.change', name='width', expression='60 mm'),
            command('solid.box', length='width', width=40, height=6, body_name='Plate'),
            command('solid.cylinder', radius=3, height=6, base=[15, 20, 0], operation='cut', targets=['Plate']),
            command('solid.cylinder', radius=3, height=6, base=['width - 15 mm', 20, 0],
                    operation='cut', targets=['Plate']),
        ])
        first = await session.capture('synthetic', 'plate', 1)
        assert first.geometry.closed_solid and first.geometry.body_count == 1
        assert first.geometry.bounds_max_mm == pytest.approx((60, 40, 6))
        # Reuse the analytic-volume tolerance from the engine qualification.
        assert first.geometry.volume_mm3 == pytest.approx(60 * 40 * 6 - 2 * math.pi * 9 * 6, rel=1e-5)
        assert first.preview is not None, first.preview_error
        assert first.preview.is_current(first.document)
        original = (tmp_path / first.document.native.path).read_bytes()

        await session.batch([command('parameters.change', name='width', expression='80 mm')])
        changed = await session.capture('synthetic', 'plate', 2)
        assert changed.geometry.bounds_max_mm == pytest.approx((80, 40, 6))
        assert not first.preview.is_current(changed.document)
        assert (tmp_path / first.document.native.path).read_bytes() == original

        before = await session.tool('measure')
        with pytest.raises(CadError, match='CAD tool failed'):
            await session.batch([command('parameters.change', name='width', expression='100 mm'),
                                 command('solid.box', length=0, width=10, height=5)])
        assert await session.tool('measure') == before
        await session.reopen(changed.document.exports[0])
        reopened = await session.tool('measure')
        assert reopened['total']['volume_mm3'] == pytest.approx(changed.geometry.volume_mm3, rel=1e-5)
        await session.reopen(first.document.native)
        assert (await session.tool('measure'))['total']['volume_mm3'] == pytest.approx(first.geometry.volume_mm3, rel=1e-5)
        with pytest.raises(FileExistsError):
            await session.capture('synthetic', 'plate', 1)
    assert session.process is None


@pytest.mark.asyncio
async def test_real_enclosure_and_scope_guards(tmp_path, engine):
    async with SolidCraftSession(tmp_path, executable=engine) as session:
        await session.batch([
            command('solid.box', length=60, width=40, height=25, body_name='Enclosure'),
            command('solid.box', length=56, width=36, height=25, corner=[2, 2, 2],
                    operation='cut', targets=['Enclosure']),
        ])
        capture = await session.capture('synthetic', 'enclosure', 1)
        assert capture.geometry.volume_mm3 == pytest.approx(13632)
        assert capture.geometry.bounds_max_mm == pytest.approx((60, 40, 25))
        for unsafe in ('file.open', 'file.save', 'script.run', 'system.exec'):
            with pytest.raises(CadError, match='outside'):
                await session.batch([command(unsafe, path='/outside')])
        with pytest.raises(CadError):
            await session.batch([command('solid.box', length=2, width=2, height=2, unexpected=True)])
        assert (await session.tool('measure'))['total']['volume_mm3'] == pytest.approx(13632)
        native = tmp_path / capture.document.native.path
        native.write_bytes(b'changed revision')
        with pytest.raises(CadError, match='changed before reopening'):
            await session.reopen(capture.document.native)


@pytest.fixture
def stalled_engine(tmp_path):
    executable = tmp_path / 'engine'
    executable.write_text(f'#!{sys.executable}\n' + '''
import json, sys, time
for line in sys.stdin:
    packet = json.loads(line)
    if packet.get('method') == 'initialize':
        print(json.dumps({'jsonrpc':'2.0', 'id':packet['id'], 'result': {
            'serverInfo':{'name':'solidcraft', 'version':'0.28.0'}}}), flush=True)
    elif 'id' in packet:
        sys.stderr.write('x' * 100000)
        sys.stderr.flush()
        time.sleep(30)
''')
    executable.chmod(0o700)
    return executable


@pytest.mark.asyncio
async def test_timeout_retires_uncertain_session_and_drains_stderr(tmp_path, stalled_engine):
    async with SolidCraftSession(tmp_path, executable=stalled_engine, timeout=0.3) as session:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(session.tool('measure'), 3)
        assert session.process is None
        assert len(session.stderr) <= 32_000
        with pytest.raises(CadError, match='closed'):
            await session.tool('measure')


@pytest.mark.asyncio
async def test_cancellation_closes_owned_process(tmp_path, stalled_engine):
    async with SolidCraftSession(tmp_path, executable=stalled_engine) as session:
        task = asyncio.create_task(session.tool('measure'))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 3)
        assert session.process is None
