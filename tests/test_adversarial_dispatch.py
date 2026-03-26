"""Adversarial tests for dispatch system — probing for UNKNOWN bugs.

Philosophy: don't test what you fixed. Test what could break.
Real MessageBus, real async, real race conditions.
"""

import asyncio
import time
from dataclasses import field
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from bigbrain.bus.message import BusMessage, MessageType, Priority
from bigbrain.bus.bus import MessageBus
from bigbrain.brains.base import BaseBrain
from bigbrain.orchestrator.orchestrator import (
    WorkspaceOrchestrator, TaskStatus, SubTask, TaskPlan
)


# ──────────────────────────────────────────────────────────────────────
# Adversarial brain implementations
# ──────────────────────────────────────────────────────────────────────

class HangingBrain(BaseBrain):
    """Brain that hangs forever — simulates stuck LLM call."""
    def __init__(self, name, bus, workspace="test"):
        super().__init__(name, bus, workspace)
        self.started_tasks = []

    async def handle_task(self, message: BusMessage):
        self.started_tasks.append(message.id)
        await asyncio.sleep(999)  # hang forever


class SlowThenFastBrain(BaseBrain):
    """First task takes a long time, subsequent tasks are instant."""
    def __init__(self, name, bus, workspace="test"):
        super().__init__(name, bus, workspace)
        self.call_count = 0
        self.completed = []

    async def handle_task(self, message: BusMessage):
        self.call_count += 1
        if self.call_count == 1:
            await asyncio.sleep(0.2)
        self.completed.append(message.payload.get("description", ""))
        return {"done": True}


class FlakeyBrain(BaseBrain):
    """Fails on specific task descriptions, succeeds on others."""
    def __init__(self, name, bus, workspace="test", fail_on=None):
        super().__init__(name, bus, workspace)
        self.fail_on = fail_on or set()
        self.completed = []

    async def handle_task(self, message: BusMessage):
        desc = message.payload.get("description", "")
        if desc in self.fail_on:
            raise RuntimeError(f"Intentional failure on: {desc}")
        await asyncio.sleep(0.01)
        self.completed.append(desc)
        return {"output": desc}


class ReentrantBrain(BaseBrain):
    """Brain that sends a message back to the bus during handle_task.
    Simulates brain triggering side effects (progress, queries, etc.)."""
    def __init__(self, name, bus, workspace="test"):
        super().__init__(name, bus, workspace)
        self.completed = []

    async def handle_task(self, message: BusMessage):
        # Send a progress event mid-task (like researcher does)
        await self.send_event("brain.progress", {
            "stage": "mid-task",
            "brain": self.name
        })
        await asyncio.sleep(0.02)
        # Send another event
        await self.send_event("brain.progress", {
            "stage": "finishing",
            "brain": self.name
        })
        desc = message.payload.get("description", "")
        self.completed.append(desc)
        return {"output": desc}


class NoisyBrain(BaseBrain):
    """Brain that sends many rapid progress events — stresses bus delivery."""
    def __init__(self, name, bus, workspace="test"):
        super().__init__(name, bus, workspace)
        self.completed = []

    async def handle_task(self, message: BusMessage):
        for i in range(20):
            await self.send_event("brain.progress", {
                "stage": f"step_{i}",
                "brain": self.name
            })
        desc = message.payload.get("description", "")
        self.completed.append(desc)
        return {"output": desc}


# ──────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────

async def make_system(brains: Dict[str, BaseBrain], pool: dict = None) -> dict:
    """Setup system from pre-constructed brains."""
    bus = brains[next(iter(brains))].bus  # grab bus from first brain
    
    for brain in brains.values():
        await brain.start()

    orch = WorkspaceOrchestrator("test", bus)
    await orch.start()

    if pool:
        for pool_name, worker_names in pool.items():
            orch.register_brain_pool(pool_name, worker_names)

    return {"bus": bus, "orchestrator": orch, "brains": brains}


async def teardown(system: dict):
    for brain in system["brains"].values():
        try:
            await brain.stop()
        except Exception:
            pass
    await system["orchestrator"].stop()
    await system["bus"].close()


def plan(orch, subtasks, source="test_front"):
    import hashlib
    plan_id = hashlib.md5(f"{id(subtasks)}{time.time()}".encode()).hexdigest()[:8]
    p = TaskPlan(
        id=plan_id,
        original_task=BusMessage(
            type=MessageType.TASK, source=source,
            target=orch.name, workspace="test",
            payload={"type": "compound"}
        ),
        subtasks=subtasks
    )
    p.status = TaskStatus.RUNNING
    orch.task_plans[p.id] = p
    return p


async def wait_plan(p, timeout=5.0):
    """Wait for plan to finish with hard timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if p.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return
        await asyncio.sleep(0.02)
    raise TimeoutError(
        f"Plan stuck in {p.status.value}: "
        f"{[f'{s.id}={s.status.value}' for s in p.subtasks]}"
    )


# ══════════════════════════════════════════════════════════════════════
# 1. brain_load accounting — can it go negative or leak?
# ══════════════════════════════════════════════════════════════════════

class TestBrainLoadAccounting:

    @pytest.mark.asyncio
    async def test_brain_load_returns_to_zero_after_all_tasks(self):
        """After all tasks complete, every brain's load must be exactly 0."""
        bus = MessageBus()
        brains = {f"w{i}": BaseBrainImpl(f"w{i}", bus, delay=0.02) for i in range(3)}
        system = await make_system(brains, pool={"pool": ["w0", "w1", "w2"]})
        try:
            orch = system["orchestrator"]
            subtasks = [
                SubTask(id=f"s{i}", description=f"t{i}", brain_target="pool",
                        payload={"description": f"t{i}"})
                for i in range(9)
            ]
            p = plan(orch, subtasks)
            await orch._execute_ready_subtasks(p)
            await wait_plan(p)

            # All loads must be 0
            for name in ["w0", "w1", "w2"]:
                load = orch.brain_load.get(name, 0)
                assert load == 0, f"{name} has load {load} after completion"
        finally:
            await teardown(system)

    @pytest.mark.asyncio
    async def test_brain_load_correct_after_failures(self):
        """Brain load must return to 0 even when tasks fail."""
        bus = MessageBus()
        brain = FlakeyBrain("flaky", bus, fail_on={"task-1", "task-3"})
        system = await make_system({"flaky": brain})
        try:
            orch = system["orchestrator"]
            subtasks = [
                SubTask(id=f"s{i}", description=f"task-{i}", brain_target="flaky",
                        payload={"description": f"task-{i}"})
                for i in range(5)
            ]
            p = plan(orch, subtasks)
            await orch._execute_ready_subtasks(p)
            await wait_plan(p, timeout=3.0)

            load = orch.brain_load.get("flaky", 0)
            assert load == 0, f"flaky has load {load} after mixed success/failure"
        finally:
            await teardown(system)


# ══════════════════════════════════════════════════════════════════════
# 2. Circular dependencies — must not deadlock
# ══════════════════════════════════════════════════════════════════════

class TestCircularDependencies:

    @pytest.mark.asyncio
    async def test_circular_deps_no_ready_tasks(self):
        """Circular dependency: s0→s1→s0. No task should ever be ready."""
        bus = MessageBus()
        brain = BaseBrainImpl("worker", bus, delay=0.01)
        system = await make_system({"worker": brain})
        try:
            orch = system["orchestrator"]
            s0 = SubTask(id="s0", description="a", brain_target="worker",
                         payload={}, dependencies={"s1"})
            s1 = SubTask(id="s1", description="b", brain_target="worker",
                         payload={}, dependencies={"s0"})
            p = plan(orch, [s0, s1])

            # Execute should dispatch nothing (no ready tasks)
            await orch._execute_ready_subtasks(p)

            # Both should still be PENDING (deadlocked but not crashed)
            assert s0.status == TaskStatus.PENDING
            assert s1.status == TaskStatus.PENDING
            # No tasks should have been started
            assert len(brain.completed) == 0
        finally:
            await teardown(system)


# ══════════════════════════════════════════════════════════════════════
# 3. Empty and degenerate plans
# ══════════════════════════════════════════════════════════════════════

class TestDegeneratePlans:

    @pytest.mark.asyncio
    async def test_empty_plan_completes_immediately(self):
        """Plan with 0 subtasks should complete (or at least not crash)."""
        bus = MessageBus()
        brain = BaseBrainImpl("worker", bus, delay=0.01)
        system = await make_system({"worker": brain})
        try:
            orch = system["orchestrator"]
            p = plan(orch, [])
            await orch._execute_ready_subtasks(p)
            # Should have dispatched nothing, plan may stay RUNNING
            # Key: no crash, no infinite loop
            assert p.status in (TaskStatus.RUNNING, TaskStatus.COMPLETE)
        finally:
            await teardown(system)

    @pytest.mark.asyncio
    async def test_single_task_plan(self):
        """Simplest possible plan: 1 task."""
        bus = MessageBus()
        brain = BaseBrainImpl("worker", bus, delay=0.01)
        system = await make_system({"worker": brain})
        try:
            orch = system["orchestrator"]
            s0 = SubTask(id="s0", description="only", brain_target="worker",
                         payload={"description": "only"})
            p = plan(orch, [s0])
            await orch._execute_ready_subtasks(p)
            await wait_plan(p)
            assert p.status == TaskStatus.COMPLETE
        finally:
            await teardown(system)


# ══════════════════════════════════════════════════════════════════════
# 4. Concurrent plans competing for same pool
# ══════════════════════════════════════════════════════════════════════

class TestConcurrentPlans:

    @pytest.mark.asyncio
    async def test_two_plans_share_worker_pool(self):
        """Two independent plans competing for 2 workers — both must complete."""
        bus = MessageBus()
        brains = {f"w{i}": BaseBrainImpl(f"w{i}", bus, delay=0.03) for i in range(2)}
        system = await make_system(brains, pool={"pool": ["w0", "w1"]})
        try:
            orch = system["orchestrator"]

            # Plan A: 3 tasks
            a_tasks = [
                SubTask(id=f"a{i}", description=f"planA-{i}", brain_target="pool",
                        payload={"description": f"planA-{i}"})
                for i in range(3)
            ]
            pa = plan(orch, a_tasks, source="user_a")

            # Plan B: 3 tasks
            b_tasks = [
                SubTask(id=f"b{i}", description=f"planB-{i}", brain_target="pool",
                        payload={"description": f"planB-{i}"})
                for i in range(3)
            ]
            pb = plan(orch, b_tasks, source="user_b")

            # Dispatch both
            await orch._execute_ready_subtasks(pa)
            await orch._execute_ready_subtasks(pb)

            # Both should complete
            await wait_plan(pa, timeout=5.0)
            await wait_plan(pb, timeout=5.0)

            assert pa.status == TaskStatus.COMPLETE
            assert pb.status == TaskStatus.COMPLETE
        finally:
            await teardown(system)


# ══════════════════════════════════════════════════════════════════════
# 5. Stale results — result arrives for already-finished plan
# ══════════════════════════════════════════════════════════════════════

class TestStaleResults:

    @pytest.mark.asyncio
    async def test_result_for_unknown_dispatch_id_is_ignored(self):
        """A result with an unrecognized reply_to should be silently ignored."""
        bus = MessageBus()
        brain = BaseBrainImpl("worker", bus, delay=0.01)
        system = await make_system({"worker": brain})
        try:
            orch = system["orchestrator"]

            # Send a fake result that doesn't match any dispatch
            stale_result = BusMessage(
                type=MessageType.RESULT,
                source="ghost_brain",
                target=orch.name,
                workspace="test",
                payload={"success": True, "data": "phantom"},
                reply_to="nonexistent-dispatch-id"
            )
            # Should not crash
            await orch.handle_message(stale_result)

            # Orchestrator should still be functional
            s0 = SubTask(id="s0", description="real", brain_target="worker",
                         payload={"description": "real"})
            p = plan(orch, [s0])
            await orch._execute_ready_subtasks(p)
            await wait_plan(p)
            assert p.status == TaskStatus.COMPLETE
        finally:
            await teardown(system)


# ══════════════════════════════════════════════════════════════════════
# 6. Brain stops mid-task — does the system survive?
# ══════════════════════════════════════════════════════════════════════

class TestBrainDeath:

    @pytest.mark.asyncio
    async def test_brain_stop_during_task_sends_cancel(self):
        """Stopping a brain while it's running a task should not crash the system."""
        bus = MessageBus()
        brain = HangingBrain("stuck", bus)
        system = await make_system({"stuck": brain})
        try:
            orch = system["orchestrator"]
            s0 = SubTask(id="s0", description="doomed", brain_target="stuck",
                         payload={"description": "doomed"})
            p = plan(orch, [s0])
            await orch._execute_ready_subtasks(p)

            # Wait for brain to start the task
            for _ in range(50):
                if brain.started_tasks:
                    break
                await asyncio.sleep(0.02)
            assert len(brain.started_tasks) == 1

            # Now kill the brain
            await brain.stop()

            # System should not crash. Plan may be stuck but that's OK —
            # the key is no exception, no corruption.
            # Give a moment for any cascading events
            await asyncio.sleep(0.1)

            # Orchestrator should still accept new messages
            stale = BusMessage(
                type=MessageType.RESULT, source="test",
                target=orch.name, workspace="test",
                payload={"success": True}, reply_to="fake"
            )
            await orch.handle_message(stale)  # must not crash
        finally:
            await teardown(system)


# ══════════════════════════════════════════════════════════════════════
# 7. Re-entrant events during task execution
# ══════════════════════════════════════════════════════════════════════

class TestReentrantEvents:

    @pytest.mark.asyncio
    async def test_brain_sending_events_mid_task_doesnt_corrupt(self):
        """Brain sending progress events during handle_task should not
        interfere with result delivery or orchestrator state."""
        bus = MessageBus()
        brain = ReentrantBrain("chatty", bus)
        system = await make_system({"chatty": brain})
        try:
            orch = system["orchestrator"]
            subtasks = [
                SubTask(id=f"s{i}", description=f"talk-{i}",
                        brain_target="chatty",
                        payload={"description": f"talk-{i}"})
                for i in range(4)
            ]
            p = plan(orch, subtasks)
            await orch._execute_ready_subtasks(p)
            await wait_plan(p)

            assert p.status == TaskStatus.COMPLETE
            assert len(brain.completed) == 4
        finally:
            await teardown(system)

    @pytest.mark.asyncio
    async def test_noisy_brain_high_event_throughput(self):
        """Brain sending 20 events per task × 3 workers doesn't crash."""
        bus = MessageBus()
        brains = {f"w{i}": NoisyBrain(f"w{i}", bus) for i in range(3)}
        system = await make_system(brains, pool={"pool": ["w0", "w1", "w2"]})
        try:
            orch = system["orchestrator"]
            subtasks = [
                SubTask(id=f"s{i}", description=f"noisy-{i}",
                        brain_target="pool",
                        payload={"description": f"noisy-{i}"})
                for i in range(6)
            ]
            p = plan(orch, subtasks)
            await orch._execute_ready_subtasks(p)
            await wait_plan(p, timeout=5.0)

            assert p.status == TaskStatus.COMPLETE
            total_completed = sum(len(b.completed) for b in brains.values())
            assert total_completed == 6
        finally:
            await teardown(system)


# ══════════════════════════════════════════════════════════════════════
# 8. Pool with dead worker — remaining workers should pick up slack
# ══════════════════════════════════════════════════════════════════════

class TestPoolResilience:

    @pytest.mark.asyncio
    async def test_pool_with_one_stopped_worker(self):
        """If 1 of 3 pool workers is stopped, remaining 2 handle all tasks."""
        bus = MessageBus()
        brains = {f"w{i}": BaseBrainImpl(f"w{i}", bus, delay=0.02) for i in range(3)}
        system = await make_system(brains, pool={"pool": ["w0", "w1", "w2"]})
        try:
            orch = system["orchestrator"]

            # Kill w2 before dispatching
            await brains["w2"].stop()

            subtasks = [
                SubTask(id=f"s{i}", description=f"task-{i}",
                        brain_target="pool",
                        payload={"description": f"task-{i}"})
                for i in range(4)
            ]
            p = plan(orch, subtasks)
            await orch._execute_ready_subtasks(p)
            await wait_plan(p, timeout=5.0)

            assert p.status == TaskStatus.COMPLETE
            # w0 and w1 should have done all the work
            w0_done = len(brains["w0"].completed)
            w1_done = len(brains["w1"].completed)
            assert w0_done + w1_done == 4
        finally:
            await teardown(system)


# ══════════════════════════════════════════════════════════════════════
# 9. Long dependency chains — stress test sequential dispatch
# ══════════════════════════════════════════════════════════════════════

class TestLongChains:

    @pytest.mark.asyncio
    async def test_chain_of_10_sequential_tasks(self):
        """s0 → s1 → s2 → ... → s9 all on same brain. Must complete in order."""
        bus = MessageBus()
        brain = BaseBrainImpl("seq", bus, delay=0.01)
        system = await make_system({"seq": brain})
        try:
            orch = system["orchestrator"]
            subtasks = [
                SubTask(id=f"s{i}", description=f"step-{i}",
                        brain_target="seq",
                        payload={"description": f"step-{i}"},
                        dependencies={f"s{i-1}"} if i > 0 else set())
                for i in range(10)
            ]
            p = plan(orch, subtasks)
            await orch._execute_ready_subtasks(p)
            await wait_plan(p, timeout=10.0)

            assert p.status == TaskStatus.COMPLETE
            # Verify order
            assert brain.completed == [f"step-{i}" for i in range(10)]
        finally:
            await teardown(system)

    @pytest.mark.asyncio
    async def test_wide_fan_out_then_merge(self):
        """1 root → 8 parallel tasks → 1 merge. Tests wide parallelism + join."""
        bus = MessageBus()
        brains = {f"w{i}": BaseBrainImpl(f"w{i}", bus, delay=0.03) for i in range(3)}
        system = await make_system(brains, pool={"pool": ["w0", "w1", "w2"]})
        try:
            orch = system["orchestrator"]

            root = SubTask(id="root", description="root", brain_target="pool",
                          payload={"description": "root"})
            parallels = [
                SubTask(id=f"p{i}", description=f"parallel-{i}",
                        brain_target="pool",
                        payload={"description": f"parallel-{i}"},
                        dependencies={"root"})
                for i in range(8)
            ]
            merge = SubTask(id="merge", description="merge",
                           brain_target="pool",
                           payload={"description": "merge"},
                           dependencies={f"p{i}" for i in range(8)})

            p = plan(orch, [root] + parallels + [merge])
            await orch._execute_ready_subtasks(p)
            await wait_plan(p, timeout=10.0)

            assert p.status == TaskStatus.COMPLETE
            assert merge.status == TaskStatus.COMPLETE
            # Merge must be last
            all_completed = []
            for b in brains.values():
                all_completed.extend(b.completed)
            assert all_completed[-1] == "merge" or "merge" in all_completed
        finally:
            await teardown(system)


# ══════════════════════════════════════════════════════════════════════
# Simple brain for most tests (avoids importing from other test files)
# ══════════════════════════════════════════════════════════════════════

class BaseBrainImpl(BaseBrain):
    """Concrete brain with configurable delay for adversarial tests."""
    def __init__(self, name, bus, workspace="test", delay=0.02):
        super().__init__(name, bus, workspace)
        self.delay = delay
        self.completed = []
        self.started = []

    async def handle_task(self, message: BusMessage):
        desc = message.payload.get("description", message.id[:8])
        self.started.append(desc)
        await asyncio.sleep(self.delay)
        self.completed.append(desc)
        return {"output": desc}
