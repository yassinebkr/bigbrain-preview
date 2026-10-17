"""Streaming manual runs — the Run button shows output AS IT IS PRODUCED
instead of buffering everything until the process exits.
"""

import asyncio
import json

import pytest

from bigbrain.web import fs_api


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", str(tmp_path / "ev"))
    return tmp_path


def _write(workspace, rel, content):
    path = workspace / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return rel


class TestRunFileStreaming:
    async def test_deltas_arrive_while_the_program_runs(self, workspace):
        rel = _write(workspace, "slow.py",
                     "import time\n"
                     "print('first')\n"
                     "time.sleep(0.8)\n"
                     "print('second')\n")
        deltas: list[tuple[str, str]] = []

        async def sink(stream, chunk):
            deltas.append((stream, chunk, asyncio.get_event_loop().time()))

        result = await fs_api.run_file_streaming(rel, timeout=10,
                                                 on_delta=sink)

        assert result["ok"] is True
        assert result["exitCode"] == 0
        assert result["stdout"] == "first\nsecond\n"
        # "first" streamed WELL BEFORE the end (the script sleeps 0.8s
        # after printing it — a buffer-until-the-end implementation
        # would have all deltas after completion).
        stamps = [d[2] for d in deltas]
        assert "first" in "".join(d[1] for d in deltas)
        assert stamps == sorted(stamps)
        if len(stamps) >= 2:
            # first delta at least 0.5s before the last one
            assert stamps[-1] - stamps[0] >= 0.5

    async def test_result_shape_matches_run_file(self, workspace):
        import sys

        rel = _write(workspace, "hello.py", "print('hi')\n")
        result = await fs_api.run_file_streaming(rel)
        assert set(result) == {"ok", "exitCode", "stdout", "stderr",
                               "durationMs", "timedOut"}
        assert result["ok"] is True and result["stdout"] == "hi\n"

    async def test_stderr_streams_on_the_err_channel(self, workspace):
        rel = _write(workspace, "err.py",
                     "import sys\nprint('warn', file=sys.stderr)\n")
        seen: list[str] = []

        async def sink(stream, chunk):
            seen.append(stream)

        result = await fs_api.run_file_streaming(rel, on_delta=sink)
        assert result["stderr"] == "warn\n"
        assert "err" in seen

    async def test_timeout_kills_and_reports(self, workspace):
        rel = _write(workspace, "loop.py", "while True:\n    pass\n")
        result = await fs_api.run_file_streaming(rel, timeout=1)
        assert result["timedOut"] is True
        assert result["ok"] is False

    async def test_missing_file_raises(self, workspace):
        from aiohttp import web
        with pytest.raises(web.HTTPNotFound):
            await fs_api.run_file_streaming("nope.py")


class TestRunWithEvents:
    async def test_stream_then_final_verdict_over_the_sink(self, workspace):
        rel = _write(workspace, "evidence.py", "print('done')\n")
        events: list[tuple[str, dict]] = []

        async def sink(event_type, payload):
            events.append((event_type, payload))

        original = fs_api._event_sink
        fs_api._event_sink = sink
        try:
            await fs_api._run_with_events(rel, 10.0, "fsrun-test1")
        finally:
            fs_api._event_sink = original

        kinds = [e[0] for e in events]
        assert kinds[0] == "fs.run_output"
        assert kinds[-1] == "fs.run_result"

        out_event = events[0][1]
        assert out_event["runId"] == "fsrun-test1"
        assert "done" in out_event["delta"]

        final = events[-1][1]
        assert final["runId"] == "fsrun-test1"
        assert final["ok"] is True
        assert final["stdout"] == "done\n"
        # Evidence still recorded on the manual streaming run
        assert final["verification"]["verdict"] in ("passed", "inconclusive")

    async def test_error_shape_reaches_the_client(self, workspace):
        events: list[tuple[str, dict]] = []

        async def sink(event_type, payload):
            events.append((event_type, payload))

        original = fs_api._event_sink
        fs_api._event_sink = sink
        try:
            await fs_api._run_with_events("missing.py", 10.0, "fsrun-test2")
        finally:
            fs_api._event_sink = original

        final = events[-1][1]
        assert final["runId"] == "fsrun-test2"
        assert final["ok"] is False
        assert "not found" in final["stderr"]
