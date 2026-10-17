"""Tests for adaptive complexity mode selection and related orchestrator features."""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, MagicMock, patch

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType, Priority
from bigbrain.orchestrator.orchestrator import (
    WorkspaceOrchestrator, TaskPlan, SubTask, TaskStatus
)
from bigbrain.orchestrator.risk import classify_risk, RiskLevel, get_risk_description, should_require_approval, get_recommended_timeout


# ─── Adaptive Complexity ───────────────────────────────────────────────────

class TestAdaptiveComplexity:
    """Test _analyze_execution_mode() — plan first, analyze second."""

    @pytest.fixture
    def orchestrator(self):
        bus = MessageBus()
        orch = WorkspaceOrchestrator("test", bus)
        orch._running = True
        return orch

    def _make_subtask(self, id, deps=None):
        return SubTask(id=id, description=f"Task {id}",
                       brain_target="python_brain", payload={},
                       dependencies=set(deps or []))

    def test_empty_subtasks_returns_todo(self, orchestrator):
        assert orchestrator._analyze_execution_mode([], "") == "todo"

    def test_single_task_returns_todo(self, orchestrator):
        tasks = [self._make_subtask("s1")]
        assert orchestrator._analyze_execution_mode(tasks, "simple") == "todo"

    def test_two_independent_returns_todo(self, orchestrator):
        """≤2 independent → todo"""
        tasks = [self._make_subtask("s1"), self._make_subtask("s2")]
        assert orchestrator._analyze_execution_mode(tasks, "two things") == "todo"

    def test_four_total_returns_todo(self, orchestrator):
        """≤4 total → todo even with >2 independent"""
        tasks = [self._make_subtask("s1"), self._make_subtask("s2"),
                 self._make_subtask("s3"), self._make_subtask("s4")]
        assert orchestrator._analyze_execution_mode(tasks, "four tasks") == "todo"

    def test_chain_returns_dag(self, orchestrator):
        """A linear chain has dependency structure → dag (the engine
        still runs one task at a time, but the plan is a real DAG and
        never gets serialized by size)."""
        tasks = [
            self._make_subtask("s1"),
            self._make_subtask("s2", ["s1"]),
            self._make_subtask("s3", ["s2"]),
            self._make_subtask("s4", ["s3"]),
            self._make_subtask("s5", ["s4"]),
        ]
        assert orchestrator._analyze_execution_mode(tasks, "chain") == "dag"

    def test_wide_graph_returns_dag(self, orchestrator):
        """>2 independent AND >4 total → dag"""
        tasks = [
            self._make_subtask("s1"),
            self._make_subtask("s2"),
            self._make_subtask("s3"),
            self._make_subtask("s4"),
            self._make_subtask("s5", ["s1", "s2", "s3", "s4"]),
        ]
        mode = orchestrator._analyze_execution_mode(tasks, "wide project")
        assert mode == "dag"

    def test_mixed_deps_dag(self, orchestrator):
        """3 independent + 3 dependent = 6 total → dag"""
        tasks = [
            self._make_subtask("s1"),
            self._make_subtask("s2"),
            self._make_subtask("s3"),
            self._make_subtask("s4", ["s1"]),
            self._make_subtask("s5", ["s2"]),
            self._make_subtask("s6", ["s3"]),
        ]
        mode = orchestrator._analyze_execution_mode(tasks, "mixed")
        assert mode == "dag"

    def test_small_fan_in_project_returns_dag(self, orchestrator):
        """A small fan-in PROJECT plan (3 parallel writes + 1 assembler)
        must run in dag: the 3 writes dispatch to the worker pool in
        PARALLEL — the ≤4-total rule used to serialize real projects."""
        tasks = [
            self._make_subtask("s1"),
            self._make_subtask("s2"),
            self._make_subtask("s3"),
            self._make_subtask("s4", ["s1", "s2", "s3"]),
        ]
        assert orchestrator._analyze_execution_mode(tasks, "small fan-in") == "dag"


# ─── Todo mode sequential execution ───────────────────────────────────────

class TestTodoModeExecution:
    """Test that todo mode dispatches one subtask at a time."""

    @pytest.fixture
    def orchestrator(self):
        bus = MessageBus()
        orch = WorkspaceOrchestrator("test", bus)
        orch._running = True
        orch.register_brain("python_brain", {"description": "Python"})
        return orch

    @pytest.mark.asyncio
    async def test_todo_mode_limits_to_one(self, orchestrator):
        """In todo mode, only 1 ready subtask should be dispatched at a time."""
        plan = TaskPlan(
            id="plan1",
            original_task=BusMessage(type=MessageType.TASK, source="user",
                                     target=orchestrator.name)
        )
        plan.execution_mode = "todo"
        plan.status = TaskStatus.RUNNING

        s1 = SubTask(id="s1", description="Task 1", brain_target="python_brain",
                     payload={"type": "execute_code"})
        s2 = SubTask(id="s2", description="Task 2", brain_target="python_brain",
                     payload={"type": "execute_code"})

        plan.subtasks = [s1, s2]
        orchestrator.task_plans[plan.id] = plan

        await orchestrator._execute_ready_subtasks(plan)

        # In todo mode, at most 1 task should be dispatched
        running = [st for st in plan.subtasks if st.status == TaskStatus.RUNNING]
        assert len(running) <= 1


# ─── Risk Classification ──────────────────────────────────────────────────

class TestRiskClassification:
    """Test risk.py classify_risk() function."""

    def test_empty_payload_is_low(self):
        assert classify_risk({}) == RiskLevel.LOW
        assert classify_risk(None) == RiskLevel.LOW

    def test_code_execution_is_high(self):
        # "execute" matches high-risk patterns (exec, system commands)
        assert classify_risk({"type": "execute_code"}) == RiskLevel.HIGH

    def test_file_write_is_medium(self):
        assert classify_risk({"type": "write_project_file"}) == RiskLevel.MEDIUM

    def test_network_is_high(self):
        assert classify_risk({"type": "http_request"}) == RiskLevel.HIGH

    def test_system_command_is_high(self):
        assert classify_risk({"description": "run subprocess shell command"}) == RiskLevel.HIGH

    def test_delete_is_high(self):
        assert classify_risk({"action": "delete files from disk"}) == RiskLevel.HIGH

    def test_read_only_is_low(self):
        assert classify_risk({"type": "read_file", "path": "/tmp/x"}) == RiskLevel.LOW

    def test_research_is_low(self):
        assert classify_risk({"type": "research", "query": "python best practices"}) == RiskLevel.LOW

    def test_nested_high_risk(self):
        """Nested dict with high-risk content should bubble up."""
        payload = {"inner": {"action": "sudo rm -rf"}}
        assert classify_risk(payload) == RiskLevel.HIGH

    def test_risk_description(self):
        assert "Read-only" in get_risk_description(RiskLevel.LOW)
        assert "File writes" in get_risk_description(RiskLevel.MEDIUM)
        assert "Network" in get_risk_description(RiskLevel.HIGH)

    def test_should_require_approval(self):
        assert should_require_approval(RiskLevel.HIGH) is True
        assert should_require_approval(RiskLevel.MEDIUM) is False
        assert should_require_approval(RiskLevel.LOW) is False

    def test_recommended_timeout(self):
        assert get_recommended_timeout(RiskLevel.LOW) == 30
        assert get_recommended_timeout(RiskLevel.MEDIUM) == 60
        assert get_recommended_timeout(RiskLevel.HIGH) == 120


# ─── User Interjection ────────────────────────────────────────────────────

class TestUserInterjection:
    """Test inject_user_message() mid-task."""

    @pytest.fixture
    def orchestrator(self):
        bus = MessageBus()
        orch = WorkspaceOrchestrator("test", bus)
        orch._running = True
        return orch

    def test_inject_into_running_plan(self, orchestrator):
        plan = TaskPlan(
            id="plan1",
            original_task=BusMessage(type=MessageType.TASK, source="user",
                                     target=orchestrator.name)
        )
        plan.status = TaskStatus.RUNNING
        orchestrator.task_plans["plan1"] = plan

        result = orchestrator.inject_user_message("plan1", "change to blue")
        assert result is True
        assert hasattr(plan, "user_interjections")
        assert len(plan.user_interjections) == 1
        assert plan.user_interjections[0]["message"] == "change to blue"

    def test_inject_into_nonexistent_plan(self, orchestrator):
        assert orchestrator.inject_user_message("nope", "hi") is False

    def test_inject_into_completed_plan(self, orchestrator):
        plan = TaskPlan(
            id="plan2",
            original_task=BusMessage(type=MessageType.TASK, source="user",
                                     target=orchestrator.name)
        )
        plan.status = TaskStatus.COMPLETE
        orchestrator.task_plans["plan2"] = plan
        assert orchestrator.inject_user_message("plan2", "too late") is False

    def test_multiple_interjections(self, orchestrator):
        plan = TaskPlan(
            id="plan3",
            original_task=BusMessage(type=MessageType.TASK, source="user",
                                     target=orchestrator.name)
        )
        plan.status = TaskStatus.RUNNING
        orchestrator.task_plans["plan3"] = plan

        orchestrator.inject_user_message("plan3", "first")
        orchestrator.inject_user_message("plan3", "second")
        assert len(plan.user_interjections) == 2


# ─── Context Compaction ───────────────────────────────────────────────────

class TestContextCompaction:
    """Test _check_context_limits and _compact_plan_context."""

    @pytest.fixture
    def orchestrator(self):
        bus = MessageBus()
        orch = WorkspaceOrchestrator("test", bus)
        orch._running = True
        return orch

    def test_compact_truncates_verbose_results(self, orchestrator):
        plan = TaskPlan(
            id="p1",
            original_task=BusMessage(type=MessageType.TASK, source="u", target="o")
        )
        s1 = SubTask(id="s1", description="write", brain_target="python_brain",
                     payload={"type": "write_project_file"})
        s1.status = TaskStatus.COMPLETE
        s1.result = {
            "success": True,
            "file_path": "models.py",
            "stdout": "x" * 500,
            "lines": 42,
            "file_content": "huge content " * 1000,
        }
        plan.subtasks = [s1]
        orchestrator.task_plans[plan.id] = plan

        orchestrator._compact_plan_context(plan)

        r = s1.result
        assert r["_compacted"] is True
        assert r["file_path"] == "models.py"
        assert r["lines"] == 42
        # stdout truncated to ~100 chars
        assert len(r["stdout"]) < 200
        # file_content should be gone (not in compact keys)
        assert "file_content" not in r

    def test_compact_skips_already_compacted(self, orchestrator):
        plan = TaskPlan(
            id="p2",
            original_task=BusMessage(type=MessageType.TASK, source="u", target="o")
        )
        s1 = SubTask(id="s1", description="done", brain_target="pb",
                     payload={"type": "test"})
        s1.status = TaskStatus.COMPLETE
        original = {"success": True, "_compacted": True, "data": "already compact"}
        s1.result = dict(original)
        plan.subtasks = [s1]

        orchestrator._compact_plan_context(plan)
        # Should not modify already-compacted results
        assert s1.result == original

    def test_compact_ignores_pending_tasks(self, orchestrator):
        plan = TaskPlan(
            id="p3",
            original_task=BusMessage(type=MessageType.TASK, source="u", target="o")
        )
        s1 = SubTask(id="s1", description="waiting", brain_target="pb",
                     payload={"type": "test"})
        s1.status = TaskStatus.PENDING
        s1.result = None
        plan.subtasks = [s1]

        orchestrator._compact_plan_context(plan)
        assert s1.result is None


# ─── Auto-Learning ────────────────────────────────────────────────────────

class TestAutoLearning:
    """Test _extract_learnings and _classify_error_type."""

    @pytest.fixture
    def orchestrator(self):
        bus = MessageBus()
        orch = WorkspaceOrchestrator("test", bus)
        orch._running = True
        return orch

    def test_classify_syntax_error(self, orchestrator):
        assert orchestrator._classify_error_type("SyntaxError: invalid syntax") == "syntax_error"

    def test_classify_import_error(self, orchestrator):
        assert orchestrator._classify_error_type("ModuleNotFoundError: No module named 'xyz'") == "import_error"

    def test_classify_timeout(self, orchestrator):
        assert orchestrator._classify_error_type("Execution timed out after 60 seconds") == "timeout_error"

    def test_classify_permission(self, orchestrator):
        assert orchestrator._classify_error_type("Permission denied: /etc/shadow") == "permission_error"

    def test_classify_file_not_found(self, orchestrator):
        assert orchestrator._classify_error_type("No such file or directory") == "file_not_found"

    def test_classify_other(self, orchestrator):
        assert orchestrator._classify_error_type("Something weird happened") == "other_error"

    @pytest.mark.asyncio
    async def test_extract_learnings_saves_failures(self, orchestrator):
        """Learnings should capture failure patterns."""
        plan = TaskPlan(
            id="lp1",
            original_task=BusMessage(type=MessageType.TASK, source="u", target="o")
        )
        s1 = SubTask(id="s1", description="broken", brain_target="pb", payload={})
        s1.status = TaskStatus.FAILED
        s1.error = "ModuleNotFoundError: No module named 'pandas'"
        plan.subtasks = [s1]

        with patch.object(orchestrator, '_save_learnings', new_callable=AsyncMock) as mock_save:
            await orchestrator._extract_learnings(plan)
            mock_save.assert_called_once()
            learnings = mock_save.call_args[0][0]
            assert len(learnings) >= 1
            assert learnings[0]["pattern"] == "import_error"

    @pytest.mark.asyncio
    async def test_extract_learnings_skips_empty_plans(self, orchestrator):
        plan = TaskPlan(
            id="lp2",
            original_task=BusMessage(type=MessageType.TASK, source="u", target="o")
        )
        plan.subtasks = []
        with patch.object(orchestrator, '_save_learnings', new_callable=AsyncMock) as mock_save:
            await orchestrator._extract_learnings(plan)
            mock_save.assert_not_called()

    def test_load_learnings_returns_empty_on_no_file(self, orchestrator, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # No learnings.json here
        assert orchestrator.load_learnings() == []
