"""Durable audit writes preserve event-loop responsiveness and cancellation safety."""

import asyncio
import json
import threading
import time

import pytest

from bigbrain.bus.logger import BusLogger
from bigbrain.bus.message import BusMessage, MessageType


@pytest.mark.asyncio
async def test_slow_fsync_keeps_the_event_loop_responsive(tmp_path, monkeypatch):
    import bigbrain.bus.logger as module
    entered, release = threading.Event(), threading.Event()
    original = module.os.fsync
    def slow_sync(fd):
        entered.set()
        release.wait(0.5)
        original(fd)
    monkeypatch.setattr(module.os, 'fsync', slow_sync)
    logger = BusLogger(tmp_path)
    message = BusMessage(type=MessageType.EVENT, source='test', target='*', payload={})
    started = time.monotonic()
    task = asyncio.create_task(logger.log_message(message))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        assert time.monotonic() - started < 0.25
    finally:
        release.set()
        await task
        await logger.close()
    assert json.loads(next(tmp_path.glob('*.jsonl')).read_text())['id'] == message.id


@pytest.mark.asyncio
async def test_cancelled_write_finishes_before_close(tmp_path, monkeypatch):
    import bigbrain.bus.logger as module
    entered, release = threading.Event(), threading.Event()
    original = module.os.fsync
    def gated_sync(fd):
        entered.set()
        assert release.wait(2)
        original(fd)
    monkeypatch.setattr(module.os, 'fsync', gated_sync)
    logger = BusLogger(tmp_path)
    message = BusMessage(type=MessageType.EVENT, source='test', target='*', payload={})
    writing = asyncio.create_task(logger.log_message(message))
    closing = None
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        writing.cancel()
        closing = asyncio.create_task(logger.close())
        await asyncio.sleep(0.02)
        assert not closing.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await writing
        if closing is not None:
            await closing
        else:
            await logger.close()
    assert logger._file_handle is None
    assert json.loads(next(tmp_path.glob('*.jsonl')).read_text())['id'] == message.id
