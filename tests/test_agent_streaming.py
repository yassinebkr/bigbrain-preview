"""Agent-run streaming + parallel sub-brains.

The user was blind while PythonBrain worked: output arrived only at the
end. The brain now streams every stdout/stderr line as `execution.output`
events (brain + subtask_id + stream + delta), and project plans run in
dag mode so independent file writes hit the worker pool in parallel.
"""

import asyncio

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType


class RecordingBus(MessageBus):
    """MessageBus that records broadcast events."""

    def __init__(self):
        super().__init__(auth=None)
        self.events = []

    async def broadcast_event(self, source, event_type, payload,
                              workspace=None, priority=None):
        self.events.append((event_type, payload))


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", str(tmp_path / "ev"))
    return tmp_path


def _brain(workspace):
    from bigbrain.brains.python_brain import PythonBrain

    bus = RecordingBus()
    brain = PythonBrain("python_brain_0", bus, "default",
                       work_dir=workspace)
    return brain, bus


class TestExecutionStreaming:
    async def test_execute_code_streams_lines_while_running(self, workspace):
        brain, bus = _brain(workspace)
        code = ("import time\n"
                "print('line-one')\n"
                "time.sleep(0.6)\n"
                "print('line-two')\n")

        result = await brain._execute_code(code, timeout=10)

        assert result["success"] is True
        assert "line-one" in result["stdout"]
        outputs = [p for t, p in bus.events if t == "execution.output"]
        assert len(outputs) >= 2
        # The FIRST line streamed well before the run completed —
        # buffer-until-the-end would have all deltas after completion.
        first = next(p["delta"] for p in outputs if "line-one" in p["delta"])
        assert "line-one" in first

    async def test_streamed_events_carry_brain_and_stream(self, workspace):
        brain, bus = _brain(workspace)
        await brain._execute_code("print('x')\n", timeout=10)

        outputs = [p for t, p in bus.events if t == "execution.output"]
        assert outputs, "no execution.output events"
        assert outputs[0]["brain"] == "python_brain_0"
        assert outputs[0]["stream"] == "out"
        assert "x" in outputs[0]["delta"]

    async def test_run_file_task_streams_and_reports(self, workspace):
        brain, bus = _brain(workspace)
        (workspace / "hello.py").write_text("print('bonjour')\n")
        result = await brain._run_existing_file({"file": "hello.py"})

        assert result["success"] is True
        assert "bonjour" in result["stdout"]
        outputs = [p for t, p in bus.events if t == "execution.output"]
        assert any("bonjour" in p["delta"] for p in outputs)

    async def test_timeout_preserves_partial_output(self, workspace):
        brain, bus = _brain(workspace)
        result = await brain._execute_code(
            "print('before-hang')\n"
            "import time\n"
            "time.sleep(10)\n",
            timeout=1,
        )
        assert result["success"] is False
        assert result["timed_out"] is True
        # The line printed BEFORE the hang survived
        assert "before-hang" in result["stdout"]
        outputs = [p for t, p in bus.events if t == "execution.output"]
        assert any("before-hang" in p["delta"] for p in outputs)

    async def test_subtask_id_travels_with_the_stream(self, workspace):
        """The brain tags its stream with the subtask it works for —
        the RunPanel attaches the output to the right step."""
        brain, bus = _brain(workspace)
        brain._current_task = BusMessage(
            type=MessageType.TASK, source="orchestrator_default",
            target="python_brain_0",
            payload={"type": "generate_and_execute",
                     "_subtask_id": "plan1_s0"},
        )
        await brain._execute_code("print('tagged')\n", timeout=10)

        outputs = [p for t, p in bus.events if t == "execution.output"]
        assert outputs[0]["subtask_id"] == "plan1_s0"


class TestParallelProjectDispatch:
    async def test_independent_writes_run_concurrently(self, workspace):
        """A small project plan (2 independent writes + 1 assembler) runs
        in dag mode: the writes OVERLAP on the worker pool. Measured by
        the workers' own start/end timestamps — orchestration overhead
        does not pollute the assertion (sequential execution would give
        zero overlap)."""
        import time as _time

        from bigbrain.brains.base import BaseBrain
        from bigbrain.orchestrator.orchestrator import (
            SubTask, TaskStatus, WorkspaceOrchestrator)

        timeline = {}

        class SlowWorker(BaseBrain):
            async def handle_task(self, message):
                subtask_id = message.payload.get("_subtask_id")
                timeline[subtask_id] = {"start": _time.monotonic()}
                await asyncio.sleep(0.5)
                timeline[subtask_id]["end"] = _time.monotonic()
                return {"success": True}

        bus = MessageBus(auth=None)
        for name in ("python_brain_0", "python_brain_1"):
            brain = SlowWorker(name, bus, "default")
            await brain.start()

        orch = WorkspaceOrchestrator("default", bus)
        await orch.start()
        orch.register_brain("python_brain_0", {"description": "code"})
        orch.register_brain("python_brain_1", {"description": "code"})
        orch.brain_pools = {"python_brain": ["python_brain_0",
                                             "python_brain_1"]}

        original = BusMessage(
            type=MessageType.TASK, source="front_brain",
            target="orchestrator_default",
            payload={"type": "compound", "user_request": "project"},
        )
        subtasks = [
            SubTask(id="s1", description="write a", brain_target="python_brain",
                    payload={"type": "write_project_file", "file_path": "a.py"}),
            SubTask(id="s2", description="write b", brain_target="python_brain",
                    payload={"type": "write_project_file", "file_path": "b.py"}),
            SubTask(id="s3", description="assemble", brain_target="python_brain",
                    payload={"type": "assemble_and_run"},
                    dependencies={"s1", "s2"}),
        ]
        from bigbrain.orchestrator.orchestrator import TaskPlan
        plan = TaskPlan(id="p1", original_task=original, subtasks=subtasks,
                        status=TaskStatus.PENDING)
        plan.execution_mode = orch._analyze_execution_mode(subtasks, "project")
        assert plan.execution_mode == "dag"

        orch.task_plans[plan.id] = plan
        plan.status = TaskStatus.RUNNING
        await orch._execute_ready_subtasks(plan)
        for _ in range(80):
            if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED):
                break
            await asyncio.sleep(0.05)

        assert plan.status == TaskStatus.COMPLETE
        # The assembler started only after BOTH writes completed.
        assert timeline["s3"]["start"] >= max(timeline["s1"]["end"],
                                               timeline["s2"]["end"])
        # The two writes overlapped for most of their 0.5s duration —
        # sequential dispatch would leave no overlap at all.
        overlap = (min(timeline["s1"]["end"], timeline["s2"]["end"])
                   - max(timeline["s1"]["start"], timeline["s2"]["start"]))
        assert overlap > 0.3, (
            f"Independent writes overlapped for {overlap:.2f}s only — "
            "they were dispatched sequentially")

        await orch.stop()
        await bus.close()


class TestStdinEof:
    """Regression (live web-scraper project): main.py with no args did
    sys.stdin.read() and BLOCKED forever — the run inherited the server's
    never-closing stdin and died only on its 30s timeout. Every runner
    now gives stdin-reading programs an immediate EOF."""

    async def test_agent_execution_gives_stdin_eof(self, workspace):
        brain, bus = _brain(workspace)
        result = await brain._execute_code(
            "import sys\n"
            "print('before-read')\n"
            "data = sys.stdin.read()\n"
            "print(f'read: {data!r}')\n",
            timeout=5,
        )
        assert result["success"] is True, result
        assert "before-read" in result["stdout"]
        assert "read: ''" in result["stdout"]  # EOF, not a hang

    async def test_manual_run_gives_stdin_eof(self, workspace):
        from bigbrain.web import fs_api
        (workspace / "reads_stdin.py").write_text(
            "import sys\nprint('eof' if sys.stdin.read() == '' else 'data')\n")
        result = await fs_api.run_file_streaming("reads_stdin.py", timeout=5)
        assert result["ok"] is True, result
        assert result["stdout"].strip() == "eof"
        # and the blocking path
        blocking = fs_api.run_file("reads_stdin.py")
        assert blocking["ok"] is True
