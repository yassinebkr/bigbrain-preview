"""Tests for BigBrain orchestrator system."""

import asyncio
import time
from unittest.mock import AsyncMock, Mock

import pytest

from bigbrain.bus.message import BusMessage, MessageType, Priority
from bigbrain.bus.bus import MessageBus
from bigbrain.orchestrator.orchestrator import (
    WorkspaceOrchestrator, TaskStatus, SubTask, TaskPlan
)


class TestSubTask:
    """Test SubTask functionality."""
    
    def test_create_subtask(self):
        """Test creating a SubTask."""
        subtask = SubTask(
            id="test_subtask",
            description="Test subtask",
            brain_target="python_brain",
            payload={"action": "test"}
        )
        
        assert subtask.id == "test_subtask"
        assert subtask.description == "Test subtask"
        assert subtask.brain_target == "python_brain"
        assert subtask.payload == {"action": "test"}
        assert subtask.status == TaskStatus.PENDING
        assert subtask.dependencies == set()
        assert subtask.result is None
        assert subtask.error is None
    
    def test_subtask_with_dependencies(self):
        """Test SubTask with dependencies."""
        subtask = SubTask(
            id="dependent_task",
            description="Depends on others",
            brain_target="worker",
            payload={},
            dependencies={"task1", "task2"}
        )
        
        assert subtask.dependencies == {"task1", "task2"}


class TestTaskPlan:
    """Test TaskPlan functionality."""
    
    def test_create_empty_plan(self):
        """Test creating an empty TaskPlan."""
        original_msg = BusMessage(
            type=MessageType.TASK,
            source="user",
            target="orchestrator"
        )
        
        plan = TaskPlan(id="test_plan", original_task=original_msg)
        
        assert plan.id == "test_plan"
        assert plan.original_task == original_msg
        assert plan.subtasks == []
        assert plan.status == TaskStatus.PENDING
        assert plan.result is None
        assert plan.error is None
    
    def test_get_ready_subtasks(self):
        """Test getting ready subtasks based on dependencies."""
        original_msg = BusMessage(type=MessageType.TASK, source="user", target="orch")
        plan = TaskPlan(id="plan", original_task=original_msg)
        
        # Create subtasks with dependencies
        task1 = SubTask(id="task1", description="First", brain_target="brain1", payload={})
        task2 = SubTask(id="task2", description="Second", brain_target="brain2", 
                       payload={}, dependencies={"task1"})
        task3 = SubTask(id="task3", description="Third", brain_target="brain3",
                       payload={}, dependencies={"task1", "task2"})
        task4 = SubTask(id="task4", description="Independent", brain_target="brain4",
                       payload={})
        
        plan.subtasks = [task1, task2, task3, task4]
        
        # Initially, only tasks without dependencies are ready
        ready = plan.get_ready_subtasks()
        ready_ids = {task.id for task in ready}
        assert ready_ids == {"task1", "task4"}
        
        # Simulate dispatching task4 and completing task1
        task4.status = TaskStatus.RUNNING  # task4 was dispatched
        task1.status = TaskStatus.COMPLETE
        ready = plan.get_ready_subtasks()
        ready_ids = {task.id for task in ready}
        assert ready_ids == {"task2"}  # Only task2 is newly ready
        
        # Complete task2
        task2.status = TaskStatus.COMPLETE
        ready = plan.get_ready_subtasks()
        ready_ids = {task.id for task in ready}
        assert ready_ids == {"task3"}  # Only task3 is ready
    
    def test_is_complete(self):
        """Test checking if plan is complete."""
        original_msg = BusMessage(type=MessageType.TASK, source="user", target="orch")
        plan = TaskPlan(id="plan", original_task=original_msg)
        
        task1 = SubTask(id="task1", description="First", brain_target="brain", payload={})
        task2 = SubTask(id="task2", description="Second", brain_target="brain", payload={})
        plan.subtasks = [task1, task2]
        
        # Not complete initially
        assert not plan.is_complete()
        
        # Not complete with only one done
        task1.status = TaskStatus.COMPLETE
        assert not plan.is_complete()
        
        # Complete when all are done
        task2.status = TaskStatus.COMPLETE
        assert plan.is_complete()
        
        # Also complete if some are cancelled
        task2.status = TaskStatus.CANCELLED
        assert plan.is_complete()
    
    def test_is_failed(self):
        """Test checking if plan failed."""
        original_msg = BusMessage(type=MessageType.TASK, source="user", target="orch")
        plan = TaskPlan(id="plan", original_task=original_msg)
        
        task1 = SubTask(id="task1", description="First", brain_target="brain", payload={})
        task2 = SubTask(id="task2", description="Second", brain_target="brain", payload={})
        plan.subtasks = [task1, task2]
        
        # Not failed initially
        assert not plan.is_failed()
        
        # Not failed with completed tasks
        task1.status = TaskStatus.COMPLETE
        assert not plan.is_failed()
        
        # Failed when any task fails
        task2.status = TaskStatus.FAILED
        assert plan.is_failed()
    
    def test_get_subtask(self):
        """Test finding subtask by ID."""
        original_msg = BusMessage(type=MessageType.TASK, source="user", target="orch")
        plan = TaskPlan(id="plan", original_task=original_msg)
        
        task1 = SubTask(id="find_me", description="Target", brain_target="brain", payload={})
        task2 = SubTask(id="other", description="Other", brain_target="brain", payload={})
        plan.subtasks = [task1, task2]
        
        found = plan.get_subtask("find_me")
        assert found == task1
        
        not_found = plan.get_subtask("nonexistent")
        assert not_found is None
    
    def test_get_results(self):
        """Test getting results from completed subtasks."""
        original_msg = BusMessage(type=MessageType.TASK, source="user", target="orch")
        plan = TaskPlan(id="plan", original_task=original_msg)
        
        task1 = SubTask(id="task1", description="First", brain_target="brain", payload={})
        task2 = SubTask(id="task2", description="Second", brain_target="brain", payload={})
        task3 = SubTask(id="task3", description="Third", brain_target="brain", payload={})
        
        # Set up results
        task1.status = TaskStatus.COMPLETE
        task1.result = {"output": "result1"}
        
        task2.status = TaskStatus.COMPLETE
        task2.result = {"output": "result2"}
        
        task3.status = TaskStatus.FAILED
        # No result for failed task
        
        plan.subtasks = [task1, task2, task3]
        
        results = plan.get_results()
        assert results == {
            "task1": {"output": "result1"},
            "task2": {"output": "result2"}
        }
        assert "task3" not in results


class TestWorkspaceOrchestrator:
    """Test WorkspaceOrchestrator functionality."""
    
    @pytest.fixture
    def mock_bus(self):
        """Create a mock message bus."""
        bus = Mock()
        bus.send = AsyncMock()
        bus.send_result = AsyncMock()
        bus.broadcast_event = AsyncMock()
        bus.subscribe = Mock()
        bus.unsubscribe = Mock()
        return bus
    
    @pytest.fixture
    async def orchestrator(self, mock_bus):
        """Create a WorkspaceOrchestrator for testing."""
        orch = WorkspaceOrchestrator("test_workspace", mock_bus)
        yield orch
        if orch._running:
            await orch.stop()
    
    @pytest.mark.asyncio
    async def test_orchestrator_lifecycle(self, orchestrator, mock_bus):
        """Test orchestrator start/stop lifecycle."""
        # Initial state
        assert not orchestrator._running
        assert orchestrator.workspace == "test_workspace"
        assert orchestrator.name == "orchestrator_test_workspace"
        
        # Start orchestrator
        await orchestrator.start()
        assert orchestrator._running
        
        # Check bus subscription
        mock_bus.subscribe.assert_called_once_with(
            "orchestrator_test_workspace",
            orchestrator.handle_message
        )
        
        # Check startup event
        mock_bus.broadcast_event.assert_called_with(
            source="orchestrator_test_workspace",
            event_type="orchestrator.started",
            payload={"workspace": "test_workspace"},
            workspace="test_workspace",
            priority=Priority.LOW
        )
        
        # Stop orchestrator
        await orchestrator.stop()
        assert not orchestrator._running
    
    @pytest.mark.asyncio
    async def test_brain_registration(self, orchestrator):
        """Test registering and unregistering brains."""
        # Register brains
        orchestrator.register_brain("python_brain", {"type": "PythonBrain"})
        orchestrator.register_brain("researcher", {"type": "ResearchBrain"})
        
        assert "python_brain" in orchestrator.registered_brains
        assert "researcher" in orchestrator.registered_brains
        assert orchestrator.brain_load["python_brain"] == 0
        assert orchestrator.brain_load["researcher"] == 0
        
        # Unregister brain
        orchestrator.unregister_brain("python_brain")
        assert "python_brain" not in orchestrator.registered_brains
        assert "python_brain" not in orchestrator.brain_load
    
    @pytest.mark.asyncio
    async def test_simple_task_creation(self, orchestrator, mock_bus):
        """Test creating task plan for simple code execution."""
        await orchestrator.start()
        orchestrator.register_brain("python_brain", {"type": "PythonBrain"})
        
        task_message = BusMessage(
            type=MessageType.TASK,
            source="front_brain",
            target="orchestrator_test_workspace",
            payload={
                "type": "execute_code",
                "code": "print('hello world')"
            }
        )
        
        plan = await orchestrator._create_task_plan(task_message)
        
        assert plan.original_task == task_message
        assert len(plan.subtasks) == 1
        
        subtask = plan.subtasks[0]
        assert subtask.brain_target == "python_brain"
        assert subtask.payload == task_message.payload
        assert subtask.dependencies == set()
    
    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_simple_fallback_decomposition(self, orchestrator, mock_bus):
        """Test fallback decomposition without LLM (single subtask routing)."""
        await orchestrator.start()
        orchestrator.register_brain("researcher", {"type": "ResearchBrain"})
        
        task_message = BusMessage(
            type=MessageType.TASK,
            source="front_brain",
            target="orchestrator_test_workspace",
            payload={
                "type": "research",
                "query": "quantum computing basics",
                "scope": "educational"
            }
        )
        
        # No LLM provider — falls back to simple decompose
        plan = await orchestrator._create_task_plan(task_message)
        
        # Simple fallback returns exactly 1 subtask
        assert len(plan.subtasks) == 1
        assert plan.subtasks[0].brain_target == "researcher"
        assert plan.subtasks[0].dependencies == set()
    
    @pytest.mark.asyncio
    async def test_llm_powered_decomposition(self, mock_bus):
        """Test LLM-powered task decomposition with dependencies."""
        # Create a mock LLM that returns different responses for each call:
        # Call 1: complexity assessment (returns script mode with research)
        # Call 2: simple planner (returns 2-step plan)
        mock_llm = AsyncMock()
        mock_llm.chat_complete = AsyncMock(side_effect=[
            '{"mode": "script", "needs_research": true, "research_queries": ["quantum computing basics"], "reason": "research then code"}',
            '[{"id": "s1", "description": "Research quantum computing", "brain_target": "researcher", "payload": {"type": "research", "query": "quantum computing"}, "dependencies": []}, {"id": "s2", "description": "Write summary code", "brain_target": "python_brain", "payload": {"type": "generate_and_execute", "user_request": "summarize findings"}, "dependencies": ["s1"]}]',
        ])
        
        orch = WorkspaceOrchestrator("test_workspace", mock_bus, llm_provider=mock_llm)
        await orch.start()
        orch.register_brain("researcher", {"type": "ResearchBrain", "description": "Research topics"})
        orch.register_brain("python_brain", {"type": "PythonBrain", "description": "Execute Python code"})
        
        task_message = BusMessage(
            type=MessageType.TASK,
            source="front_brain",
            target="orchestrator_test_workspace",
            payload={
                "type": "research",
                "query": "quantum computing basics",
                "user_request": "research quantum computing and write a summary"
            }
        )
        
        plan = await orch._create_task_plan(task_message)
        
        assert len(plan.subtasks) == 2
        assert plan.subtasks[0].brain_target == "researcher"
        assert plan.subtasks[1].brain_target == "python_brain"
        
        # Check dependency: s2 depends on s1
        assert plan.subtasks[0].dependencies == set()
        s1_id = plan.subtasks[0].id
        assert s1_id in plan.subtasks[1].dependencies
        
        # Verify LLM was called (twice: assessment + planning)
        assert mock_llm.chat_complete.call_count == 2
        # Check second call (planner) has the right system prompt
        planner_call = mock_llm.chat_complete.call_args_list[1]
        messages = planner_call.kwargs.get("messages", [])
        assert any("task planner" in m["content"].lower() for m in messages if m["role"] == "system")
        
        await orch.stop()
    
    @pytest.mark.asyncio
    async def test_llm_decompose_fallback_on_error(self, mock_bus):
        """Test that LLM planning failure falls back to simple decompose."""
        mock_llm = AsyncMock()
        mock_llm.chat_complete = AsyncMock(side_effect=RuntimeError("API error"))
        
        orch = WorkspaceOrchestrator("test_workspace", mock_bus, llm_provider=mock_llm)
        await orch.start()
        orch.register_brain("python_brain", {"type": "PythonBrain"})
        
        task_message = BusMessage(
            type=MessageType.TASK,
            source="front_brain",
            target="orchestrator_test_workspace",
            payload={"type": "execute_code", "user_request": "print hello"}
        )
        
        plan = await orch._create_task_plan(task_message)
        
        # Should fall back to simple decompose (1 subtask)
        assert len(plan.subtasks) == 1
        assert plan.subtasks[0].brain_target == "python_brain"
        
        await orch.stop()
    
    @pytest.mark.asyncio
    async def test_parse_plan_json_variants(self, orchestrator):
        """Test JSON parsing handles various LLM output formats."""
        # Clean JSON
        result = orchestrator._parse_plan_json('[{"id": "s1", "description": "test"}]')
        assert len(result) == 1
        assert result[0]["id"] == "s1"
        
        # JSON in markdown code fence
        result = orchestrator._parse_plan_json('```json\n[{"id": "s1"}]\n```')
        assert len(result) == 1
        
        # JSON with trailing text
        result = orchestrator._parse_plan_json('[{"id": "s1"}]\n\nThis plan will...')
        assert len(result) == 1
        
        # Invalid JSON raises
        with pytest.raises(ValueError, match="Could not parse"):
            orchestrator._parse_plan_json("not json at all")

    @pytest.mark.asyncio
    async def test_choose_brain_for_task(self, orchestrator):
        """Test brain selection picks least loaded brain."""
        # Register multiple brains
        orchestrator.register_brain("python_brain", {"type": "PythonBrain"})
        orchestrator.register_brain("researcher", {"type": "ResearchBrain"})
        
        # Both at load 0 — picks alphabetically first (dict order)
        brain = orchestrator._choose_brain_for_task("anything")
        assert brain in ["python_brain", "researcher"]
        
        # Load python_brain higher — should pick researcher (least loaded)
        orchestrator.brain_load["python_brain"] = 5
        brain = orchestrator._choose_brain_for_task("anything")
        assert brain == "researcher"
        
        # Load researcher higher — should pick python_brain
        orchestrator.brain_load["researcher"] = 10
        brain = orchestrator._choose_brain_for_task("anything")
        assert brain == "python_brain"
    
    @pytest.mark.asyncio
    async def test_simple_decompose_routes_by_type(self, orchestrator):
        """Test simple fallback decomposition routes known types correctly."""
        orchestrator.register_brain("python_brain", {"type": "PythonBrain"})
        orchestrator.register_brain("researcher", {"type": "ResearchBrain"})
        
        # Code tasks → python_brain
        plan_id = "test"
        subtasks = orchestrator._simple_decompose(plan_id, {"type": "execute_code"})
        assert subtasks[0].brain_target == "python_brain"
        
        subtasks = orchestrator._simple_decompose(plan_id, {"type": "generate_and_execute"})
        assert subtasks[0].brain_target == "python_brain"
        
        # Research tasks → researcher
        subtasks = orchestrator._simple_decompose(plan_id, {"type": "research"})
        assert subtasks[0].brain_target == "researcher"
    
    @pytest.mark.asyncio
    async def test_task_request_handling(self, orchestrator, mock_bus):
        """Test handling incoming task requests."""
        await orchestrator.start()
        orchestrator.register_brain("python_brain", {"type": "PythonBrain"})
        
        task_message = BusMessage(
            type=MessageType.TASK,
            source="front_brain",
            target="orchestrator_test_workspace",
            payload={
                "type": "execute_code",
                "code": "print('test')"
            }
        )
        
        await orchestrator._handle_task_request(task_message)
        
        # Check that task plan was created
        assert len(orchestrator.task_plans) == 1
        plan = list(orchestrator.task_plans.values())[0]
        
        # Check task received event was broadcast
        received_calls = [call for call in mock_bus.broadcast_event.call_args_list
                         if call[1]["event_type"] == "task.received"]
        assert len(received_calls) == 1
        
        # Check subtask was dispatched
        dispatched_calls = [call for call in mock_bus.send.call_args_list
                           if call[0][0].type == MessageType.TASK]
        assert len(dispatched_calls) == 1
        
        subtask_msg = dispatched_calls[0][0][0]
        assert subtask_msg.target == "python_brain"
        assert subtask_msg.source == "orchestrator_test_workspace"
    
    @pytest.mark.asyncio
    async def test_task_result_handling(self, orchestrator, mock_bus):
        """Test handling task results from brains."""
        await orchestrator.start()
        orchestrator.register_brain("python_brain", {"type": "PythonBrain"})
        
        # Create a task plan manually for testing
        original_task = BusMessage(type=MessageType.TASK, source="user", target="orch")
        plan = TaskPlan(id="test_plan", original_task=original_task)
        
        subtask = SubTask(
            id="test_subtask",
            description="Test",
            brain_target="python_brain",
            payload={}
        )
        subtask.status = TaskStatus.RUNNING
        subtask.assigned_brain = "python_brain"
        subtask._dispatch_msg_id = "dispatch_msg_id"
        
        plan.subtasks = [subtask]
        orchestrator.task_plans[plan.id] = plan
        orchestrator.active_subtasks["dispatch_msg_id"] = plan.id
        orchestrator.brain_load["python_brain"] = 1
        
        # Send result message
        result_message = BusMessage(
            type=MessageType.RESULT,
            source="python_brain",
            target="orchestrator_test_workspace",
            reply_to="dispatch_msg_id",
            payload={
                "success": True,
                "output": "task completed"
            }
        )
        
        await orchestrator._handle_task_result(result_message)
        
        # Check subtask was updated
        assert subtask.status == TaskStatus.COMPLETE
        assert subtask.result == {"success": True, "output": "task completed"}
        assert orchestrator.brain_load["python_brain"] == 0
        assert subtask.id not in orchestrator.active_subtasks
        
        # Check completion event was broadcast
        complete_calls = [call for call in mock_bus.broadcast_event.call_args_list
                         if call[1]["event_type"] == "subtask.complete"]
        assert len(complete_calls) >= 1
    
    @pytest.mark.asyncio
    async def test_plan_completion(self, orchestrator, mock_bus):
        """Test complete task plan finishing."""
        await orchestrator.start()
        
        # Create completed task plan
        original_task = BusMessage(
            id="original_task_id",
            type=MessageType.TASK, 
            source="user", 
            target="orch"
        )
        plan = TaskPlan(id="test_plan", original_task=original_task)
        
        subtask = SubTask(
            id="test_subtask",
            description="Test",
            brain_target="python_brain", 
            payload={}
        )
        subtask.status = TaskStatus.COMPLETE
        subtask.result = {"success": True, "data": "result"}
        
        plan.subtasks = [subtask]
        orchestrator.task_plans[plan.id] = plan
        
        await orchestrator._check_plan_completion(plan)
        
        # Check final result was sent
        mock_bus.send_result.assert_called_once()
        call_args = mock_bus.send_result.call_args
        
        assert call_args[1]["source"] == "orchestrator_test_workspace"
        assert call_args[1]["reply_to"] == "original_task_id"
        
        result_data = call_args[1]["result_data"]
        assert result_data["success"] is True
        assert "results" in result_data
    
    def test_project_metadata_falls_back_to_selected_project_manifest(
            self, orchestrator, tmp_path, monkeypatch):
        import json

        monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path))
        project = tmp_path / "sandbox" / "existing-project"
        project.mkdir(parents=True)
        (project / ".project.json").write_text(json.dumps({
            "name": "existing-project",
            "entry_point": "main.py",
            "run": ["python", "main.py"],
        }))
        original_task = BusMessage(
            id="original", type=MessageType.TASK, source="user", target="orch",
            payload={"project_path": "sandbox/existing-project"},
        )
        plan = TaskPlan(id="plan", original_task=original_task)
        subtask = SubTask(id="edit", description="edit one file",
                          brain_target="python_brain", payload={})
        subtask.status = TaskStatus.COMPLETE
        subtask.result = {"success": True, "file_path": "programme.py"}
        plan.subtasks = [subtask]

        assert orchestrator._project_result_metadata(plan) == {
            "project_name": "existing-project",
            "project_path": "sandbox/existing-project",
            "entry_point": "main.py",
            "runnable": True,
        }

    def test_project_metadata_preserves_web_preview(self, orchestrator):
        plan = TaskPlan(id="web-plan", original_task=None)
        subtask = SubTask(id="preview", description="preview web app",
                          brain_target="web_app_brain", payload={})
        subtask.status = TaskStatus.COMPLETE
        subtask.result = {"success": True, "data": {
            "success": True,
            "project_name": "zbrush-course",
            "project_path": "sandbox/zbrush-course",
            "entry_point": "index.html",
            "deliverable_type": "web_app",
            "preview_url": "http://127.0.0.1:3200",
            "server_running": True,
        }}
        plan.subtasks = [subtask]

        assert orchestrator._project_result_metadata(plan) == {
            "project_name": "zbrush-course",
            "project_path": "sandbox/zbrush-course",
            "entry_point": "index.html",
            "deliverable_type": "web_app",
            "preview_url": "http://127.0.0.1:3200",
            "runnable": True,
        }

    def test_project_metadata_prefers_verified_assembly(self, orchestrator):
        plan = TaskPlan(id="web-plan", original_task=None)
        assembled = SubTask(id="assemble", description="preview web app", brain_target="web_app_brain", payload={})
        assembled.status = TaskStatus.COMPLETE
        assembled.result = {"success": True, "data": {
            "success": True, "project_name": "course", "project_path": "sandbox/course",
            "entry_point": "index.html", "deliverable_type": "web_app",
            "preview_url": "http://127.0.0.1:3200", "server_running": True,
            "verification": {"passed": True},
        }}
        intermediate = SubTask(id="write", description="write file", brain_target="web_app_brain", payload={})
        intermediate.status = TaskStatus.COMPLETE
        intermediate.result = {"success": True, "data": {"project_name": "course", "entry_point": "index.html"}}
        plan.subtasks = [assembled, intermediate]
        metadata = orchestrator._project_result_metadata(plan)
        assert metadata["runnable"] is True
        assert metadata["preview_url"] == "http://127.0.0.1:3200"

    @pytest.mark.asyncio
    async def test_plan_failure(self, orchestrator, mock_bus):
        """Test handling task plan with failed subtask."""
        await orchestrator.start()
        
        # Create failed task plan
        original_task = BusMessage(id="original", type=MessageType.TASK, source="user", target="orch")
        plan = TaskPlan(id="test_plan", original_task=original_task)
        
        failed_subtask = SubTask(
            id="failed_subtask",
            description="This fails",
            brain_target="python_brain",
            payload={}
        )
        failed_subtask.status = TaskStatus.FAILED
        failed_subtask.error = "Something went wrong"
        
        successful_subtask = SubTask(
            id="success_subtask", 
            description="This works",
            brain_target="python_brain",
            payload={}
        )
        successful_subtask.status = TaskStatus.COMPLETE
        
        plan.subtasks = [failed_subtask, successful_subtask]
        orchestrator.task_plans[plan.id] = plan
        
        await orchestrator._check_plan_completion(plan)
        
        # Check failure result was sent
        mock_bus.send_result.assert_called_once()
        result_data = mock_bus.send_result.call_args[1]["result_data"]
        
        assert result_data["success"] is False
        assert "failed_subtasks" in result_data
        assert len(result_data["failed_subtasks"]) == 1
    
    @pytest.mark.asyncio
    async def test_cancellation(self, orchestrator, mock_bus):
        """Test task cancellation."""
        await orchestrator.start()
        
        # Create running task plan
        original_task = BusMessage(type=MessageType.TASK, source="user", target="orch")
        plan = TaskPlan(id="cancel_plan", original_task=original_task)
        plan.status = TaskStatus.RUNNING
        
        subtask = SubTask(
            id="cancel_subtask",
            description="To be cancelled",
            brain_target="python_brain",
            payload={}
        )
        subtask.status = TaskStatus.RUNNING
        subtask.assigned_brain = "python_brain"
        subtask._dispatch_msg_id = "dispatch_msg_id"
        
        plan.subtasks = [subtask]
        orchestrator.task_plans[plan.id] = plan
        orchestrator.active_subtasks["dispatch_msg_id"] = plan.id
        
        # Send cancellation
        cancel_message = BusMessage(
            type=MessageType.CANCEL,
            source="user",
            target="orchestrator_test_workspace", 
            payload={
                "task_id": plan.id,
                "mode": "soft"
            }
        )
        
        await orchestrator._handle_cancel_request(cancel_message)
        
        # Check cancellation was sent to brain
        cancel_calls = [call for call in mock_bus.send.call_args_list
                       if call[0][0].type == MessageType.CANCEL]
        assert len(cancel_calls) >= 1
        
        cancel_msg = cancel_calls[0][0][0]
        assert cancel_msg.target == "python_brain"
        assert cancel_msg.payload["mode"] == "soft"
    
    @pytest.mark.asyncio
    async def test_status_query(self, orchestrator, mock_bus):
        """Test handling status queries."""
        await orchestrator.start()
        orchestrator.register_brain("python_brain", {"type": "PythonBrain"})
        
        query_message = BusMessage(
            type=MessageType.QUERY,
            source="requester",
            target="orchestrator_test_workspace",
            payload={"type": "status"}
        )
        
        await orchestrator._handle_query(query_message)
        
        # Check status response was sent
        mock_bus.send_result.assert_called_once()
        result_data = mock_bus.send_result.call_args[1]["result_data"]
        
        assert "workspace" in result_data
        assert "running" in result_data
        assert "registered_brains" in result_data
        assert result_data["workspace"] == "test_workspace"
        assert result_data["running"] is True
    
    def test_get_status(self, orchestrator):
        """Test getting orchestrator status."""
        orchestrator.register_brain("brain1", {})
        orchestrator.register_brain("brain2", {})
        
        status = orchestrator.get_status()
        
        assert status["workspace"] == "test_workspace"
        assert status["name"] == "orchestrator_test_workspace"
        assert status["running"] is False
        assert status["active_tasks"] == 0
        assert status["total_tasks"] == 0
        assert set(status["registered_brains"]) == {"brain1", "brain2"}
    
    @pytest.mark.asyncio
    async def test_resolve_payload_references(self, orchestrator):
        """Test resolving ReWOO-style variable references."""
        original_task = BusMessage(type=MessageType.TASK, source="user", target="orch")
        plan = TaskPlan(id="ref_plan", original_task=original_task)
        
        # Create subtasks with results
        task1 = SubTask(id="E1", description="First", brain_target="brain", payload={})
        task1.status = TaskStatus.COMPLETE
        task1.result = {"search_results": ["result1", "result2"]}
        
        task2 = SubTask(id="E2", description="Second", brain_target="brain", payload={})
        task2.status = TaskStatus.COMPLETE
        task2.result = {"analysis": "important findings"}
        
        plan.subtasks = [task1, task2]
        
        # Test payload with references
        payload_with_refs = {
            "action": "summarize",
            "data_source": "#E1",
            "context": "#E2",
            "static_param": "no_reference"
        }
        
        resolved = await orchestrator._resolve_payload_references(payload_with_refs, plan)
        
        assert resolved["action"] == "summarize"
        assert resolved["data_source"] == {"search_results": ["result1", "result2"]}
        assert resolved["context"] == {"analysis": "important findings"}
        assert resolved["static_param"] == "no_reference"
        
        # Test unresolved reference
        payload_unresolved = {"data": "#E3"}  # E3 doesn't exist
        resolved_unresolved = await orchestrator._resolve_payload_references(
            payload_unresolved, plan
        )
        assert resolved_unresolved["data"] == "#E3"  # Should remain unchanged
