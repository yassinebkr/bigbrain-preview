"""Tests for Execution Modes and orchestrator integration."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType, Priority
from bigbrain.orchestrator.execution_modes import BrainExecutionConfig, ExecutionMode
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, TaskPlan, SubTask, TaskStatus
from bigbrain.verification.pipeline import VerificationLevel


class TestExecutionMode:
    """Test ExecutionMode enum."""

    def test_lightning_value(self):
        assert ExecutionMode.LIGHTNING == "lightning"
        assert ExecutionMode.LIGHTNING.value == "lightning"

    def test_control_value(self):
        assert ExecutionMode.CONTROL == "control"
        assert ExecutionMode.CONTROL.value == "control"

    def test_custom_value(self):
        assert ExecutionMode.CUSTOM == "custom"
        assert ExecutionMode.CUSTOM.value == "custom"

    def test_is_string_enum(self):
        assert isinstance(ExecutionMode.LIGHTNING, str)


class TestBrainExecutionConfig:
    """Test BrainExecutionConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BrainExecutionConfig(brain_name="test_brain")

        assert config.brain_name == "test_brain"
        assert config.mode == ExecutionMode.LIGHTNING
        assert config.requires_approval is False
        assert config.max_retries == 3
        assert config.verification_levels is None

    def test_custom_config(self):
        """Test fully customized config."""
        levels = [VerificationLevel.V4_DETERMINISTIC, VerificationLevel.V3_CROSS_CHECK]
        config = BrainExecutionConfig(
            brain_name="custom_brain",
            mode=ExecutionMode.CUSTOM,
            requires_approval=True,
            max_retries=5,
            verification_levels=levels,
        )

        assert config.brain_name == "custom_brain"
        assert config.mode == ExecutionMode.CUSTOM
        assert config.requires_approval is True
        assert config.max_retries == 5
        assert config.verification_levels == levels

    def test_should_run_v3_lightning(self):
        """Lightning mode should NOT run V3."""
        config = BrainExecutionConfig(brain_name="b", mode=ExecutionMode.LIGHTNING)
        assert config.should_run_v3() is False

    def test_should_run_v3_control(self):
        """Control mode should run V3 (all checks)."""
        config = BrainExecutionConfig(brain_name="b", mode=ExecutionMode.CONTROL)
        assert config.should_run_v3() is True

    def test_should_run_v3_custom_with_v3_in_levels(self):
        """Custom mode with V3 in levels should run V3."""
        config = BrainExecutionConfig(
            brain_name="b",
            mode=ExecutionMode.CUSTOM,
            verification_levels=[VerificationLevel.V3_CROSS_CHECK],
        )
        assert config.should_run_v3() is True

    def test_should_run_v3_custom_without_v3(self):
        """Custom mode without V3 in levels should NOT run V3."""
        config = BrainExecutionConfig(
            brain_name="b",
            mode=ExecutionMode.CUSTOM,
            verification_levels=[VerificationLevel.V4_DETERMINISTIC],
        )
        assert config.should_run_v3() is False

    def test_should_run_v3_custom_no_explicit_levels(self):
        """Custom mode without explicit levels should run all (including V3)."""
        config = BrainExecutionConfig(brain_name="b", mode=ExecutionMode.CUSTOM)
        assert config.should_run_v3() is True

    def test_should_run_v5_lightning(self):
        """Lightning mode should NOT run V5."""
        config = BrainExecutionConfig(brain_name="b", mode=ExecutionMode.LIGHTNING)
        assert config.should_run_v5() is False

    def test_should_run_v5_control(self):
        """Control mode should always run V5."""
        config = BrainExecutionConfig(brain_name="b", mode=ExecutionMode.CONTROL)
        assert config.should_run_v5() is True

    def test_should_run_v5_custom_requires_approval(self):
        """Custom mode with requires_approval should run V5."""
        config = BrainExecutionConfig(
            brain_name="b",
            mode=ExecutionMode.CUSTOM,
            requires_approval=True,
        )
        assert config.should_run_v5() is True

    def test_should_run_v5_custom_in_levels(self):
        """Custom mode with V5 in levels should run V5."""
        config = BrainExecutionConfig(
            brain_name="b",
            mode=ExecutionMode.CUSTOM,
            verification_levels=[VerificationLevel.V5_HUMAN_GATE],
        )
        assert config.should_run_v5() is True

    def test_should_run_v5_custom_not_in_levels(self):
        """Custom mode without V5 in levels and no approval should NOT run V5."""
        config = BrainExecutionConfig(
            brain_name="b",
            mode=ExecutionMode.CUSTOM,
            requires_approval=False,
            verification_levels=[VerificationLevel.V4_DETERMINISTIC],
        )
        assert config.should_run_v5() is False

    def test_get_effective_levels_lightning(self):
        """Lightning mode: only V4 + V1."""
        config = BrainExecutionConfig(brain_name="b", mode=ExecutionMode.LIGHTNING)
        levels = config.get_effective_levels()
        assert levels == [VerificationLevel.V4_DETERMINISTIC, VerificationLevel.V1_SCHEMA]

    def test_get_effective_levels_control(self):
        """Control mode: all four levels."""
        config = BrainExecutionConfig(brain_name="b", mode=ExecutionMode.CONTROL)
        levels = config.get_effective_levels()
        assert VerificationLevel.V4_DETERMINISTIC in levels
        assert VerificationLevel.V1_SCHEMA in levels
        assert VerificationLevel.V3_CROSS_CHECK in levels
        assert VerificationLevel.V5_HUMAN_GATE in levels

    def test_get_effective_levels_custom_explicit(self):
        """Custom mode with explicit levels uses those levels."""
        custom_levels = [VerificationLevel.V4_DETERMINISTIC, VerificationLevel.V3_CROSS_CHECK]
        config = BrainExecutionConfig(
            brain_name="b",
            mode=ExecutionMode.CUSTOM,
            verification_levels=custom_levels,
        )
        assert config.get_effective_levels() == custom_levels

    def test_get_effective_levels_custom_default(self):
        """Custom mode without explicit levels defaults to all."""
        config = BrainExecutionConfig(brain_name="b", mode=ExecutionMode.CUSTOM)
        levels = config.get_effective_levels()
        assert len(levels) == 4


class TestOrchestratorExecutionModes:
    """Test execution mode integration with WorkspaceOrchestrator."""

    @pytest.fixture
    def mock_bus(self):
        bus = Mock()
        bus.send = AsyncMock()
        bus.send_result = AsyncMock()
        bus.broadcast_event = AsyncMock()
        bus.subscribe = Mock()
        bus.unsubscribe = Mock()
        return bus

    @pytest.fixture
    async def orchestrator(self, mock_bus):
        orch = WorkspaceOrchestrator("test_workspace", mock_bus)
        yield orch
        if orch._running:
            await orch.stop()

    def test_execution_configs_init(self, orchestrator):
        """Test that execution_configs is initialized empty."""
        assert orchestrator.execution_configs == {}

    def test_set_execution_mode(self, orchestrator):
        """Test setting execution mode for a brain."""
        config = orchestrator.set_execution_mode("python_brain", ExecutionMode.CONTROL)

        assert config.brain_name == "python_brain"
        assert config.mode == ExecutionMode.CONTROL
        assert config.requires_approval is True  # Default for CONTROL
        assert "python_brain" in orchestrator.execution_configs

    def test_set_execution_mode_lightning(self, orchestrator):
        """Test setting lightning mode."""
        config = orchestrator.set_execution_mode("fast_brain", ExecutionMode.LIGHTNING)

        assert config.mode == ExecutionMode.LIGHTNING
        assert config.requires_approval is False

    def test_set_execution_mode_custom_kwargs(self, orchestrator):
        """Test setting custom mode with kwargs."""
        levels = [VerificationLevel.V4_DETERMINISTIC, VerificationLevel.V3_CROSS_CHECK]
        config = orchestrator.set_execution_mode(
            "custom_brain",
            ExecutionMode.CUSTOM,
            requires_approval=True,
            max_retries=5,
            verification_levels=levels,
        )

        assert config.mode == ExecutionMode.CUSTOM
        assert config.requires_approval is True
        assert config.max_retries == 5
        assert config.verification_levels == levels

    def test_get_execution_config_existing(self, orchestrator):
        """Test getting config for a configured brain."""
        orchestrator.set_execution_mode("brain1", ExecutionMode.CONTROL)
        config = orchestrator.get_execution_config("brain1")
        assert config.mode == ExecutionMode.CONTROL

    def test_get_execution_config_default(self, orchestrator):
        """Test getting config for an unconfigured brain defaults to LIGHTNING."""
        config = orchestrator.get_execution_config("unknown_brain")
        assert config.brain_name == "unknown_brain"
        assert config.mode == ExecutionMode.LIGHTNING

    def test_status_includes_execution_configs(self, orchestrator):
        """Test that get_status includes execution configs."""
        orchestrator.set_execution_mode("brain1", ExecutionMode.CONTROL)
        orchestrator.set_execution_mode("brain2", ExecutionMode.LIGHTNING)

        status = orchestrator.get_status()

        assert "execution_configs" in status
        assert "brain1" in status["execution_configs"]
        assert status["execution_configs"]["brain1"]["mode"] == "control"
        assert status["execution_configs"]["brain1"]["requires_approval"] is True
        assert status["execution_configs"]["brain2"]["mode"] == "lightning"

    @pytest.mark.asyncio
    async def test_handle_result_lightning_no_verification_events(self, orchestrator, mock_bus):
        """Test that lightning mode doesn't emit V3/V5 verification events."""
        await orchestrator.start()
        orchestrator.register_brain("python_brain", {})
        orchestrator.set_execution_mode("python_brain", ExecutionMode.LIGHTNING)

        # Set up a task plan with an active subtask
        original_task = BusMessage(type=MessageType.TASK, source="user", target="orch")
        plan = TaskPlan(id="plan1", original_task=original_task)
        subtask = SubTask(
            id="st1", description="Test", brain_target="python_brain", payload={}
        )
        subtask.status = TaskStatus.RUNNING
        subtask.assigned_brain = "python_brain"
        subtask._dispatch_msg_id = "dispatch_msg_id"
        plan.subtasks = [subtask]
        orchestrator.task_plans[plan.id] = plan
        orchestrator.active_subtasks["dispatch_msg_id"] = plan.id
        orchestrator.brain_load["python_brain"] = 1

        # Send successful result
        result_msg = BusMessage(
            type=MessageType.RESULT,
            source="python_brain",
            target="orchestrator_test_workspace",
            reply_to="dispatch_msg_id",
            payload={"success": True, "output": "done"},
        )
        mock_bus.broadcast_event.reset_mock()
        await orchestrator._handle_task_result(result_msg)

        # Verify no v3/v5 events were broadcast
        for call in mock_bus.broadcast_event.call_args_list:
            event_type = call[1]["event_type"]
            assert "v3_required" not in event_type
            assert "v5_required" not in event_type

    @pytest.mark.asyncio
    async def test_handle_result_control_emits_v3_and_v5(self, orchestrator, mock_bus):
        """Test that control mode emits V3 and V5 verification events."""
        await orchestrator.start()
        orchestrator.register_brain("python_brain", {})
        orchestrator.set_execution_mode("python_brain", ExecutionMode.CONTROL)

        original_task = BusMessage(type=MessageType.TASK, source="user", target="orch")
        plan = TaskPlan(id="plan2", original_task=original_task)
        subtask = SubTask(
            id="st2", description="Test", brain_target="python_brain", payload={}
        )
        subtask.status = TaskStatus.RUNNING
        subtask.assigned_brain = "python_brain"
        subtask._dispatch_msg_id = "dispatch_msg_id"
        plan.subtasks = [subtask]
        orchestrator.task_plans[plan.id] = plan
        orchestrator.active_subtasks["dispatch_msg_id"] = plan.id
        orchestrator.brain_load["python_brain"] = 1

        result_msg = BusMessage(
            type=MessageType.RESULT,
            source="python_brain",
            target="orchestrator_test_workspace",
            reply_to="dispatch_msg_id",
            payload={"success": True, "output": "done"},
        )
        mock_bus.broadcast_event.reset_mock()
        await orchestrator._handle_task_result(result_msg)

        event_types = [call[1]["event_type"] for call in mock_bus.broadcast_event.call_args_list]
        assert "verification.v3_required" in event_types
        assert "verification.v5_required" in event_types

    @pytest.mark.asyncio
    async def test_handle_result_failed_no_verification(self, orchestrator, mock_bus):
        """Test that failed results don't trigger V3/V5 even in control mode."""
        await orchestrator.start()
        orchestrator.register_brain("python_brain", {})
        orchestrator.set_execution_mode("python_brain", ExecutionMode.CONTROL)

        original_task = BusMessage(type=MessageType.TASK, source="user", target="orch")
        plan = TaskPlan(id="plan3", original_task=original_task)
        subtask = SubTask(
            id="st3", description="Test", brain_target="python_brain", payload={}
        )
        subtask.status = TaskStatus.RUNNING
        subtask.assigned_brain = "python_brain"
        subtask._dispatch_msg_id = "dispatch_msg_id"
        plan.subtasks = [subtask]
        orchestrator.task_plans[plan.id] = plan
        orchestrator.active_subtasks["dispatch_msg_id"] = plan.id
        orchestrator.brain_load["python_brain"] = 1

        result_msg = BusMessage(
            type=MessageType.RESULT,
            source="python_brain",
            target="orchestrator_test_workspace",
            reply_to="dispatch_msg_id",
            payload={"success": False, "error": "kaboom"},
        )
        mock_bus.broadcast_event.reset_mock()
        await orchestrator._handle_task_result(result_msg)

        event_types = [call[1]["event_type"] for call in mock_bus.broadcast_event.call_args_list]
        assert "verification.v3_required" not in event_types
        assert "verification.v5_required" not in event_types

    @pytest.mark.asyncio
    async def test_handle_result_custom_v3_only(self, orchestrator, mock_bus):
        """Test custom mode with only V3 emits v3 but not v5."""
        await orchestrator.start()
        orchestrator.register_brain("python_brain", {})
        orchestrator.set_execution_mode(
            "python_brain",
            ExecutionMode.CUSTOM,
            requires_approval=False,
            verification_levels=[VerificationLevel.V3_CROSS_CHECK],
        )

        original_task = BusMessage(type=MessageType.TASK, source="user", target="orch")
        plan = TaskPlan(id="plan4", original_task=original_task)
        subtask = SubTask(
            id="st4", description="Test", brain_target="python_brain", payload={}
        )
        subtask.status = TaskStatus.RUNNING
        subtask.assigned_brain = "python_brain"
        subtask._dispatch_msg_id = "dispatch_msg_id"
        plan.subtasks = [subtask]
        orchestrator.task_plans[plan.id] = plan
        orchestrator.active_subtasks["dispatch_msg_id"] = plan.id
        orchestrator.brain_load["python_brain"] = 1

        result_msg = BusMessage(
            type=MessageType.RESULT,
            source="python_brain",
            target="orchestrator_test_workspace",
            reply_to="dispatch_msg_id",
            payload={"success": True, "output": "done"},
        )
        mock_bus.broadcast_event.reset_mock()
        await orchestrator._handle_task_result(result_msg)

        event_types = [call[1]["event_type"] for call in mock_bus.broadcast_event.call_args_list]
        assert "verification.v3_required" in event_types
        assert "verification.v5_required" not in event_types

    def test_set_execution_mode_overwrites(self, orchestrator):
        """Test that setting mode again overwrites the previous config."""
        orchestrator.set_execution_mode("brain1", ExecutionMode.LIGHTNING)
        assert orchestrator.get_execution_config("brain1").mode == ExecutionMode.LIGHTNING

        orchestrator.set_execution_mode("brain1", ExecutionMode.CONTROL)
        assert orchestrator.get_execution_config("brain1").mode == ExecutionMode.CONTROL

    @pytest.mark.asyncio
    async def test_v5_event_has_high_priority(self, orchestrator, mock_bus):
        """Test that V5 verification required events have HIGH priority."""
        await orchestrator.start()
        orchestrator.register_brain("python_brain", {})
        orchestrator.set_execution_mode("python_brain", ExecutionMode.CONTROL)

        original_task = BusMessage(type=MessageType.TASK, source="user", target="orch")
        plan = TaskPlan(id="plan5", original_task=original_task)
        subtask = SubTask(
            id="st5", description="Test", brain_target="python_brain", payload={}
        )
        subtask.status = TaskStatus.RUNNING
        subtask.assigned_brain = "python_brain"
        subtask._dispatch_msg_id = "dispatch_msg_id"
        plan.subtasks = [subtask]
        orchestrator.task_plans[plan.id] = plan
        orchestrator.active_subtasks["dispatch_msg_id"] = plan.id
        orchestrator.brain_load["python_brain"] = 1

        result_msg = BusMessage(
            type=MessageType.RESULT,
            source="python_brain",
            target="orchestrator_test_workspace",
            reply_to="dispatch_msg_id",
            payload={"success": True},
        )
        mock_bus.broadcast_event.reset_mock()
        await orchestrator._handle_task_result(result_msg)

        v5_calls = [
            call for call in mock_bus.broadcast_event.call_args_list
            if call[1]["event_type"] == "verification.v5_required"
        ]
        assert len(v5_calls) == 1
        assert v5_calls[0][1]["priority"] == Priority.HIGH
