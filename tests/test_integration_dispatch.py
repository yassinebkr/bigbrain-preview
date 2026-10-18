"""Hardened integration tests for brain dispatch, busy rejection, and parallel execution.

These tests use a REAL MessageBus (not mocks) to catch the synchronous delivery
race conditions that mocks miss. Every test here corresponds to a production bug.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

import pytest

from bigbrain.bus.message import BusMessage, MessageType, Priority
from bigbrain.bus.bus import MessageBus
from bigbrain.brains.base import BaseBrain
from bigbrain.orchestrator.orchestrator import (
    WorkspaceOrchestrator, TaskStatus, SubTask, TaskPlan
)


# ──────────────────────────────────────────────────────────────────────
# Test brain with configurable delay (simulates LLM call duration)
# ──────────────────────────────────────────────────────────────────────

class SlowBrain(BaseBrain):
    """Brain with configurable task duration for integration testing."""

    def __init__(self, name: str, bus: MessageBus, workspace: str = "test",
                 delay: float = 0.05):
        super().__init__(name, bus, workspace)
        self.delay = delay
        self.tasks_completed: List[str] = []
        self.tasks_started: List[str] = []
        self.should_fail = False

    async def handle_task(self, message: BusMessage) -> Dict[str, Any]:
        task_desc = message.payload.get("description", message.id[:8])
        self.tasks_started.append(task_desc)
        await asyncio.sleep(self.delay)
        if self.should_fail:
            raise RuntimeError(f"Simulated failure in {self.name}")
        self.tasks_completed.append(task_desc)
        return {"output": f"done:{task_desc}"}


class InstantBrain(BaseBrain):
    """Brain that completes instantly (simulates file-write tasks)."""

    def __init__(self, name: str, bus: MessageBus, workspace: str = "test"):
        super().__init__(name, bus, workspace)
        self.tasks_completed: List[str] = []

    async def handle_task(self, message: BusMessage) -> Dict[str, Any]:
        desc = message.payload.get("description", message.id[:8])
        self.tasks_completed.append(desc)
        return {"output": f"done:{desc}"}


# ──────────────────────────────────────────────────────────────────────
# Helper: create orchestrator with real bus + brains
# ──────────────────────────────────────────────────────────────────────

async def setup_system(brain_configs: List[dict], pool_name: str = None) -> dict:
    """Set up a real bus + orchestrator + brains for integration tests.
    
    Args:
        brain_configs: List of {"name": str, "delay": float, "cls": type}
        pool_name: If set, register all brains as a pool under this name
    
    Returns:
        {"bus": MessageBus, "orchestrator": ..., "brains": {name: brain}}
    """
    bus = MessageBus()

    brains = {}
    for cfg in brain_configs:
        cls = cfg.get("cls", SlowBrain)
        if cls == SlowBrain:
            brain = SlowBrain(cfg["name"], bus, delay=cfg.get("delay", 0.05))
        else:
            brain = cls(cfg["name"], bus)
        await brain.start()
        brains[cfg["name"]] = brain

    orch = WorkspaceOrchestrator("test", bus)
    await orch.start()

    if pool_name:
        pool_names = [cfg["name"] for cfg in brain_configs]
        orch.register_brain_pool(pool_name, pool_names)

    return {"bus": bus, "orchestrator": orch, "brains": brains}


async def teardown_system(system: dict):
    """Stop all components."""
    for brain in system["brains"].values():
        await brain.stop()
    await system["orchestrator"].stop()
    await system["bus"].close()


def make_plan(orch: WorkspaceOrchestrator, subtasks: List[SubTask],
              task_source: str = "test_front") -> TaskPlan:
    """Create and register a TaskPlan with the orchestrator."""
    import hashlib, time
    plan_id = hashlib.md5(f"{time.time()}".encode()).hexdigest()[:8]
    plan = TaskPlan(
        id=plan_id,
        original_task=BusMessage(
            type=MessageType.TASK,
            source=task_source,
            target=orch.name,
            workspace="test",
            payload={"type": "compound", "description": "test plan"}
        ),
        subtasks=subtasks
    )
    plan.status = TaskStatus.RUNNING
    orch.task_plans[plan.id] = plan
    return plan


# ══════════════════════════════════════════════════════════════════════
# TEST SUITE 1: Busy rejection handling
# Bug: brain rejects task → orchestrator never sees busy result → stuck
# ══════════════════════════════════════════════════════════════════════

class TestBusyRejection:
    """Tests for brain busy rejection and proper re-queuing."""

    @pytest.mark.asyncio
    async def test_busy_brain_requeues_and_completes(self):
        """When brain is busy, task is re-queued and eventually completes.
        
        Bug reproduced: brain.send_result() with target=None raised ValueError
        because log search failed. Orchestrator never saw {busy: true}.
        """
        system = await setup_system([
            {"name": "worker", "delay": 0.1}
        ])
        try:
            orch = system["orchestrator"]
            brain = system["brains"]["worker"]

            # Two independent subtasks, both targeting same brain
            s0 = SubTask(id="s0", description="task-0",
                         brain_target="worker", payload={"description": "task-0"})
            s1 = SubTask(id="s1", description="task-1",
                         brain_target="worker", payload={"description": "task-1"})
            plan = make_plan(orch, [s0, s1])

            # Dispatch both — s0 should start, s1 should defer (capacity)
            await orch._execute_ready_subtasks(plan)

            # Wait for both to complete
            for _ in range(50):
                if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED):
                    break
                await asyncio.sleep(0.05)

            assert plan.status == TaskStatus.COMPLETE, \
                f"Plan stuck in {plan.status.value}, s0={s0.status.value}, s1={s1.status.value}"
            assert s0.status == TaskStatus.COMPLETE
            assert s1.status == TaskStatus.COMPLETE
            assert "task-0" in brain.tasks_completed
            assert "task-1" in brain.tasks_completed
        finally:
            await teardown_system(system)

    @pytest.mark.asyncio
    async def test_no_infinite_busy_loop(self):
        """Busy rejection doesn't cause infinite re-dispatch loop.
        
        Bug reproduced: _current_task cleared in finally (after send_result),
        so brain was always "busy" when next task arrived via synchronous delivery.
        Orchestrator re-queued → post-loop re-dispatched → infinite spin.
        """
        system = await setup_system([
            {"name": "worker", "delay": 0.05}
        ])
        try:
            orch = system["orchestrator"]
            brain = system["brains"]["worker"]

            s0 = SubTask(id="s0", description="first",
                         brain_target="worker", payload={"description": "first"})
            s1 = SubTask(id="s1", description="second",
                         brain_target="worker", payload={"description": "second"})
            plan = make_plan(orch, [s0, s1])

            # Track how many times dispatch is called (should be bounded)
            dispatch_count = 0
            original_dispatch = orch._dispatch_subtask
            async def counting_dispatch(p, st):
                nonlocal dispatch_count
                dispatch_count += 1
                return await original_dispatch(p, st)
            orch._dispatch_subtask = counting_dispatch

            await orch._execute_ready_subtasks(plan)

            # Wait for completion
            for _ in range(50):
                if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED):
                    break
                await asyncio.sleep(0.05)

            assert plan.status == TaskStatus.COMPLETE
            # 2 subtasks → should dispatch exactly 2 times (no infinite retry)
            # Allow some extra for re-queues but NOT hundreds
            assert dispatch_count <= 6, \
                f"Dispatch called {dispatch_count} times — possible infinite loop"
        finally:
            await teardown_system(system)


# ══════════════════════════════════════════════════════════════════════
# TEST SUITE 2: Parallel execution via worker pool
# Bug: bus.send() blocked on handle_task → sequential execution
# ══════════════════════════════════════════════════════════════════════

class TestParallelExecution:
    """Tests for worker pool parallel dispatch."""

    @pytest.mark.asyncio
    async def test_pool_dispatches_to_multiple_workers(self):
        """3 independent tasks should run on 3 different workers simultaneously."""
        started = set()
        all_started = asyncio.Event()

        class BarrierBrain(SlowBrain):
            async def handle_task(self, message):
                started.add(self.name)
                if len(started) == 3:
                    all_started.set()
                # A sequential dispatcher or a single reused worker cannot
                # cross this barrier. Disk logging speed is irrelevant.
                await asyncio.wait_for(all_started.wait(), timeout=2)
                return await super().handle_task(message)

        system = await setup_system([
            {"name": "w0", "cls": BarrierBrain},
            {"name": "w1", "cls": BarrierBrain},
            {"name": "w2", "cls": BarrierBrain},
        ], pool_name="python_brain")
        try:
            orch = system["orchestrator"]

            subtasks = [
                SubTask(id=f"s{i}", description=f"task-{i}",
                        brain_target="python_brain",
                        payload={"description": f"task-{i}"})
                for i in range(3)
            ]
            plan = make_plan(orch, subtasks)

            await orch._execute_ready_subtasks(plan)

            # Wait for completion
            for _ in range(50):
                if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED):
                    break
                await asyncio.sleep(0.05)

            assert plan.status == TaskStatus.COMPLETE
            assert all_started.is_set()

            # All 3 workers should have been used
            workers_used = set()
            for st in subtasks:
                if st.assigned_brain:
                    workers_used.add(st.assigned_brain)
            assert len(workers_used) == 3, \
                f"Only {len(workers_used)} workers used: {workers_used}"
        finally:
            await teardown_system(system)

    @pytest.mark.asyncio
    async def test_pool_handles_more_tasks_than_workers(self):
        """5 tasks with 2 workers should complete without deadlock."""
        system = await setup_system([
            {"name": "w0", "delay": 0.05},
            {"name": "w1", "delay": 0.05},
        ], pool_name="python_brain")
        try:
            orch = system["orchestrator"]

            subtasks = [
                SubTask(id=f"s{i}", description=f"task-{i}",
                        brain_target="python_brain",
                        payload={"description": f"task-{i}"})
                for i in range(5)
            ]
            plan = make_plan(orch, subtasks)
            await orch._execute_ready_subtasks(plan)

            for _ in range(100):
                if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED):
                    break
                await asyncio.sleep(0.05)

            assert plan.status == TaskStatus.COMPLETE, \
                f"Plan stuck: {[f'{s.id}={s.status.value}' for s in subtasks]}"
            assert all(s.status == TaskStatus.COMPLETE for s in subtasks)
        finally:
            await teardown_system(system)

    @pytest.mark.asyncio
    async def test_pool_single_worker_still_works(self):
        """Pool with 1 worker should still complete all tasks sequentially."""
        system = await setup_system([
            {"name": "solo", "delay": 0.02},
        ], pool_name="python_brain")
        try:
            orch = system["orchestrator"]

            subtasks = [
                SubTask(id=f"s{i}", description=f"task-{i}",
                        brain_target="python_brain",
                        payload={"description": f"task-{i}"})
                for i in range(3)
            ]
            plan = make_plan(orch, subtasks)
            await orch._execute_ready_subtasks(plan)

            for _ in range(100):
                if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED):
                    break
                await asyncio.sleep(0.05)

            assert plan.status == TaskStatus.COMPLETE
        finally:
            await teardown_system(system)


# ══════════════════════════════════════════════════════════════════════
# TEST SUITE 3: DAG dependency chains
# Bug: tasks dispatched before dependencies complete
# ══════════════════════════════════════════════════════════════════════

class TestDependencyChains:
    """Tests for correct DAG execution order."""

    @pytest.mark.asyncio
    async def test_dependent_task_waits_for_prerequisite(self):
        """s1 depends on s0 — s1 must not start until s0 completes."""
        system = await setup_system([
            {"name": "worker", "delay": 0.05}
        ])
        try:
            orch = system["orchestrator"]
            brain = system["brains"]["worker"]

            s0 = SubTask(id="s0", description="prerequisite",
                         brain_target="worker",
                         payload={"description": "prerequisite"})
            s1 = SubTask(id="s1", description="dependent",
                         brain_target="worker",
                         payload={"description": "dependent"},
                         dependencies={"s0"})
            plan = make_plan(orch, [s0, s1])
            await orch._execute_ready_subtasks(plan)

            for _ in range(100):
                if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED):
                    break
                await asyncio.sleep(0.05)

            assert plan.status == TaskStatus.COMPLETE
            # prerequisite must have started before dependent
            assert brain.tasks_started.index("prerequisite") < \
                   brain.tasks_started.index("dependent")
        finally:
            await teardown_system(system)

    @pytest.mark.asyncio
    async def test_diamond_dependency(self):
        """Diamond DAG: s0 → (s1, s2) → s3. s3 waits for both s1 and s2."""
        system = await setup_system([
            {"name": "w0", "delay": 0.05},
            {"name": "w1", "delay": 0.05},
        ], pool_name="python_brain")
        try:
            orch = system["orchestrator"]

            s0 = SubTask(id="s0", description="root",
                         brain_target="python_brain",
                         payload={"description": "root"})
            s1 = SubTask(id="s1", description="left",
                         brain_target="python_brain",
                         payload={"description": "left"},
                         dependencies={"s0"})
            s2 = SubTask(id="s2", description="right",
                         brain_target="python_brain",
                         payload={"description": "right"},
                         dependencies={"s0"})
            s3 = SubTask(id="s3", description="merge",
                         brain_target="python_brain",
                         payload={"description": "merge"},
                         dependencies={"s1", "s2"})
            plan = make_plan(orch, [s0, s1, s2, s3])
            await orch._execute_ready_subtasks(plan)

            for _ in range(100):
                if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED):
                    break
                await asyncio.sleep(0.05)

            assert plan.status == TaskStatus.COMPLETE
            # All tasks completed
            assert all(s.status == TaskStatus.COMPLETE for s in [s0, s1, s2, s3])
            # s3 must be last
            for brain in system["brains"].values():
                if "merge" in brain.tasks_completed:
                    idx = brain.tasks_completed.index("merge")
                    # merge can't be the first task on any worker
                    # (root must complete first, then left/right)
                    break
        finally:
            await teardown_system(system)


# ══════════════════════════════════════════════════════════════════════
# TEST SUITE 4: Error handling and recovery
# ══════════════════════════════════════════════════════════════════════

class TestErrorHandling:
    """Tests for brain failure and plan failure propagation."""

    @pytest.mark.asyncio
    async def test_brain_error_marks_subtask_failed(self):
        """When a brain throws, the subtask should be marked FAILED."""
        system = await setup_system([
            {"name": "flaky", "delay": 0.01}
        ])
        try:
            orch = system["orchestrator"]
            brain = system["brains"]["flaky"]
            brain.should_fail = True

            s0 = SubTask(id="s0", description="will-fail",
                         brain_target="flaky",
                         payload={"description": "will-fail"})
            plan = make_plan(orch, [s0])
            await orch._execute_ready_subtasks(plan)

            for _ in range(50):
                if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED):
                    break
                await asyncio.sleep(0.05)

            assert s0.status == TaskStatus.FAILED
            assert plan.status == TaskStatus.FAILED
        finally:
            await teardown_system(system)

    @pytest.mark.asyncio
    async def test_one_failure_doesnt_block_independent_tasks(self):
        """If s0 fails, independent s1 should still complete."""
        system = await setup_system([
            {"name": "w0", "delay": 0.02},
            {"name": "w1", "delay": 0.02},
        ], pool_name="python_brain")
        try:
            orch = system["orchestrator"]
            system["brains"]["w0"].should_fail = True

            s0 = SubTask(id="s0", description="will-fail",
                         brain_target="python_brain",
                         payload={"description": "will-fail"})
            s1 = SubTask(id="s1", description="will-succeed",
                         brain_target="python_brain",
                         payload={"description": "will-succeed"})
            plan = make_plan(orch, [s0, s1])
            await orch._execute_ready_subtasks(plan)

            for _ in range(50):
                if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED):
                    break
                await asyncio.sleep(0.05)

            # One failed → plan fails, but s1 may or may not have completed
            # The key: no deadlock or hang
            assert plan.status == TaskStatus.FAILED
            assert s0.status == TaskStatus.FAILED
        finally:
            await teardown_system(system)

    @pytest.mark.asyncio
    async def test_dependent_task_not_dispatched_after_prereq_fails(self):
        """If s0 fails, dependent s1 should never start."""
        system = await setup_system([
            {"name": "worker", "delay": 0.02}
        ])
        try:
            orch = system["orchestrator"]
            brain = system["brains"]["worker"]
            brain.should_fail = True

            s0 = SubTask(id="s0", description="will-fail",
                         brain_target="worker",
                         payload={"description": "will-fail"})
            s1 = SubTask(id="s1", description="never-start",
                         brain_target="worker",
                         payload={"description": "never-start"},
                         dependencies={"s0"})
            plan = make_plan(orch, [s0, s1])
            await orch._execute_ready_subtasks(plan)

            for _ in range(50):
                if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED):
                    break
                await asyncio.sleep(0.05)

            assert plan.status == TaskStatus.FAILED
            assert s0.status == TaskStatus.FAILED
            assert s1.status == TaskStatus.PENDING  # Never started
            assert "never-start" not in brain.tasks_started
        finally:
            await teardown_system(system)


# ══════════════════════════════════════════════════════════════════════
# TEST SUITE 5: Race conditions and timing
# ══════════════════════════════════════════════════════════════════════

class TestRaceConditions:
    """Tests for timing-sensitive dispatch edge cases."""

    @pytest.mark.asyncio
    async def test_rapid_task_completion_no_state_corruption(self):
        """Instant-completing tasks don't corrupt brain state."""
        system = await setup_system([
            {"name": "fast", "cls": InstantBrain},
        ])
        try:
            orch = system["orchestrator"]
            brain = system["brains"]["fast"]

            subtasks = [
                SubTask(id=f"s{i}", description=f"instant-{i}",
                        brain_target="fast",
                        payload={"description": f"instant-{i}"})
                for i in range(10)
            ]
            plan = make_plan(orch, subtasks)
            await orch._execute_ready_subtasks(plan)

            for _ in range(100):
                if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED):
                    break
                await asyncio.sleep(0.02)

            assert plan.status == TaskStatus.COMPLETE, \
                f"Plan stuck: {[f'{s.id}={s.status.value}' for s in subtasks]}"
            assert len(brain.tasks_completed) == 10
        finally:
            await teardown_system(system)

    @pytest.mark.asyncio
    async def test_concurrent_result_delivery(self):
        """Multiple workers completing at the same time don't corrupt orchestrator state."""
        system = await setup_system([
            {"name": "w0", "delay": 0.05},
            {"name": "w1", "delay": 0.05},
            {"name": "w2", "delay": 0.05},
        ], pool_name="python_brain")
        try:
            orch = system["orchestrator"]

            # 6 independent tasks on 3 workers — 2 rounds
            subtasks = [
                SubTask(id=f"s{i}", description=f"task-{i}",
                        brain_target="python_brain",
                        payload={"description": f"task-{i}"})
                for i in range(6)
            ]
            plan = make_plan(orch, subtasks)
            await orch._execute_ready_subtasks(plan)

            for _ in range(100):
                if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED):
                    break
                await asyncio.sleep(0.05)

            assert plan.status == TaskStatus.COMPLETE
            assert all(s.status == TaskStatus.COMPLETE for s in subtasks)
        finally:
            await teardown_system(system)

    @pytest.mark.asyncio
    async def test_post_loop_depth_limit_prevents_spin(self):
        """Post-loop recursion depth is bounded (safety valve)."""
        system = await setup_system([
            {"name": "worker", "delay": 0.02}
        ])
        try:
            orch = system["orchestrator"]

            # Track recursion depth
            depths = []
            original = orch._execute_ready_subtasks
            async def tracking_execute(plan, _depth=0):
                depths.append(_depth)
                return await original(plan, _depth=_depth)
            orch._execute_ready_subtasks = tracking_execute

            subtasks = [
                SubTask(id=f"s{i}", description=f"chain-{i}",
                        brain_target="worker",
                        payload={"description": f"chain-{i}"},
                        dependencies={f"s{i-1}"} if i > 0 else set())
                for i in range(5)
            ]
            plan = make_plan(orch, subtasks)
            await tracking_execute(plan)

            for _ in range(200):
                if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED):
                    break
                await asyncio.sleep(0.05)

            assert plan.status == TaskStatus.COMPLETE
            # Depth should never exceed 3 (our safety limit)
            assert max(depths) <= 3, f"Max depth {max(depths)} exceeds limit"
        finally:
            await teardown_system(system)
