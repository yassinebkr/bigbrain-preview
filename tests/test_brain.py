"""Tests for BigBrain execution brains."""

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from bigbrain.bus.message import BusMessage, MessageType, Priority
from bigbrain.bus.bus import MessageBus
from bigbrain.brains.base import BaseBrain
from bigbrain.brains.python_brain import PythonBrain


class TestBaseBrain:
    """Test BaseBrain abstract functionality."""
    
    class TestBrain(BaseBrain):
        """Concrete test brain for testing BaseBrain."""
        
        def __init__(self, name="test_brain", bus=None, workspace=None):
            super().__init__(name, bus, workspace)
            self.handled_tasks = []
            self.should_fail = False
            self.processing_time = 0.01
        
        async def handle_task(self, message: BusMessage):
            """Test task handler."""
            self.handled_tasks.append(message)
            
            if self.should_fail:
                raise RuntimeError("Test failure")
            
            await asyncio.sleep(self.processing_time)
            
            if self._cancelled:
                return {"cancelled": True}
            
            return {
                "payload": message.payload,
                "success": True
            }
    
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
    async def test_brain(self, mock_bus):
        """Create a test brain instance."""
        brain = self.TestBrain("test_brain", mock_bus, "test_workspace")
        yield brain
        if brain.is_running():
            await brain.stop()
    
    @pytest.mark.asyncio
    async def test_brain_lifecycle(self, test_brain, mock_bus):
        """Test brain start/stop lifecycle."""
        # Initial state
        assert not test_brain.is_running()
        assert not test_brain.is_busy()
        
        # Start brain
        await test_brain.start()
        assert test_brain.is_running()
        
        # Check bus subscription
        mock_bus.subscribe.assert_called_once_with(
            "test_brain", 
            test_brain._message_handler
        )
        
        # Check startup event
        mock_bus.broadcast_event.assert_called_with(
            source="test_brain",
            event_type="brain.started",
            payload={
                "brain": "test_brain",
                "workspace": "test_workspace"
            },
            workspace="test_workspace",
            priority=Priority.LOW
        )
        
        # Stop brain
        await test_brain.stop()
        assert not test_brain.is_running()
        
        # Check bus unsubscription
        mock_bus.unsubscribe.assert_called_with(
            "test_brain",
            test_brain._message_handler
        )
    
    @pytest.mark.asyncio
    async def test_task_handling(self, test_brain, mock_bus):
        """Test basic task handling."""
        await test_brain.start()
        
        # Send a task message
        task_message = BusMessage(
            type=MessageType.TASK,
            source="orchestrator",
            target="test_brain",
            payload={"action": "test_action", "data": 123}
        )
        
        await test_brain._handle_message_wrapper(task_message)
        
        # Task execution is now in a background asyncio task — await it
        if test_brain._background_task:
            await test_brain._background_task
        
        # Check task was handled
        assert len(test_brain.handled_tasks) == 1
        assert test_brain.handled_tasks[0].id == task_message.id
        
        # Check result was sent
        mock_bus.send_result.assert_called_once()
        call_args = mock_bus.send_result.call_args
        
        assert call_args[1]["source"] == "test_brain"
        assert call_args[1]["reply_to"] == task_message.id
        assert call_args[1]["workspace"] == "test_workspace"
        
        result_data = call_args[1]["result_data"]
        assert result_data["success"] is True
        assert result_data["data"]["payload"] == {"action": "test_action", "data": 123}
    
    @pytest.mark.asyncio
    async def test_busy_rejection(self, test_brain, mock_bus):
        """Test that busy brain rejects new tasks."""
        await test_brain.start()
        
        # Make task processing slow
        test_brain.processing_time = 0.1
        
        # Send first task (will be processing)
        task1 = BusMessage(
            type=MessageType.TASK,
            source="orchestrator", 
            target="test_brain",
            payload={"task": "first"}
        )
        
        # Send second task quickly (should be rejected)
        task2 = BusMessage(
            type=MessageType.TASK,
            source="orchestrator",
            target="test_brain", 
            payload={"task": "second"}
        )
        
        # Start first task and immediately send second
        await test_brain._handle_message_wrapper(task1)
        await asyncio.sleep(0.01)  # Let background task start processing
        
        await test_brain._handle_message_wrapper(task2)
        
        # Wait for first task's background execution to finish
        if test_brain._background_task:
            await test_brain._background_task
        
        # Check that two results were sent
        assert mock_bus.send_result.call_count == 2
        
        # Second call should be busy rejection
        second_call = mock_bus.send_result.call_args_list[0]
        result_data = second_call[1]["result_data"]
        assert result_data["success"] is False
        assert result_data["busy"] is True
    
    @pytest.mark.asyncio
    async def test_task_error_handling(self, test_brain, mock_bus):
        """Test error handling in task processing."""
        await test_brain.start()
        test_brain.should_fail = True
        
        task_message = BusMessage(
            type=MessageType.TASK,
            source="orchestrator",
            target="test_brain",
            payload={"action": "fail"}
        )
        
        await test_brain._handle_message_wrapper(task_message)
        
        # Task execution is now in background — await it
        if test_brain._background_task:
            await test_brain._background_task
        
        # Should send error result from background task execution
        assert mock_bus.send_result.called
        result_call = mock_bus.send_result.call_args
        assert result_call[1]["result_data"]["success"] is False
        assert result_call[1]["result_data"]["error"] == "Test failure"
        assert result_call[1]["target"] == "orchestrator"
        assert result_call[1]["reply_to"] == task_message.id
        
        # Should also broadcast error event
        error_calls = [call for call in mock_bus.broadcast_event.call_args_list 
                      if call[1]["event_type"] == "brain.error"]
        assert len(error_calls) == 1
        
        error_call = error_calls[0]
        error_payload = error_call[1]["payload"]
        assert error_payload["brain"] == "test_brain"
        assert error_payload["error"] == "Test failure"
    
    @pytest.mark.asyncio
    async def test_cancellation(self, test_brain, mock_bus):
        """Test task cancellation."""
        await test_brain.start()
        test_brain.processing_time = 0.1
        
        # Start a task
        task_message = BusMessage(
            type=MessageType.TASK,
            source="orchestrator",
            target="test_brain",
            payload={"action": "long_task"}
        )
        
        # Start task and cancel it
        async def run_and_cancel():
            task_future = asyncio.create_task(
                test_brain._handle_message_wrapper(task_message)
            )
            await asyncio.sleep(0.01)  # Let task start
            
            # Send cancel message
            cancel_message = BusMessage(
                type=MessageType.CANCEL,
                source="orchestrator",
                target="test_brain",
                payload={"mode": "soft"}
            )
            await test_brain._handle_message_wrapper(cancel_message)
            await task_future
        
        await run_and_cancel()
        
        # Check cancellation event was sent
        cancel_calls = [call for call in mock_bus.broadcast_event.call_args_list
                       if call[1]["event_type"] == "brain.cancelling"]
        assert len(cancel_calls) >= 1
    
    @pytest.mark.asyncio
    async def test_convenience_methods(self, test_brain, mock_bus):
        """Test convenience methods for sending events and results."""
        await test_brain.start()
        
        # Test send_event
        await test_brain.send_event(
            "custom.event",
            {"data": "test"},
            Priority.HIGH
        )
        
        # Test send_progress
        test_brain._current_task = BusMessage(
            type=MessageType.TASK,
            source="test",
            target="test_brain"
        )
        
        await test_brain.send_progress({"progress": 0.5})
        
        # Check events were sent
        assert mock_bus.broadcast_event.call_count >= 2  # startup + custom event
    
    def test_get_status(self, test_brain):
        """Test getting brain status."""
        status = test_brain.get_status()
        
        assert status["name"] == "test_brain"
        assert status["workspace"] == "test_workspace"
        assert status["running"] is False
        assert status["busy"] is False
        assert status["current_task"] is None
        assert status["cancelled"] is False


class TestPythonBrain:
    """Test PythonBrain functionality."""
    
    @pytest.fixture
    def temp_work_dir(self):
        """Create temporary work directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
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
    async def python_brain(self, mock_bus, temp_work_dir):
        """Create a PythonBrain instance for testing."""
        brain = PythonBrain(
            name="test_python_brain",
            bus=mock_bus,
            workspace="test_workspace",
            timeout=5,
            work_dir=temp_work_dir
        )
        yield brain
        if brain.is_running():
            await brain.stop()
    
    @pytest.mark.asyncio
    async def test_simple_code_execution(self, python_brain):
        """Test executing simple Python code."""
        task_message = BusMessage(
            type=MessageType.TASK,
            source="orchestrator",
            target="test_python_brain",
            payload={
                "type": "execute_code",
                "code": "print('Hello, BigBrain!')"
            }
        )
        
        result = await python_brain.handle_task(task_message)
        
        assert result["success"] is True
        assert result["exit_code"] == 0
        assert "Hello, BigBrain!" in result["stdout"]
        assert result["stderr"] == ""
        assert not result["timed_out"]
    
    @pytest.mark.asyncio
    async def test_code_with_error(self, python_brain):
        """Test executing code that produces an error."""
        task_message = BusMessage(
            type=MessageType.TASK,
            source="orchestrator",
            target="test_python_brain",
            payload={
                "type": "execute_code",
                "code": "print(undefined_variable)"
            }
        )
        
        result = await python_brain.handle_task(task_message)
        
        assert result["success"] is False
        assert result["exit_code"] != 0
        assert "NameError" in result["stderr"]
        assert "undefined_variable" in result["stderr"]
        assert not result["timed_out"]
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_file_creation(self, python_brain):
        """Test creating files during execution."""
        task_message = BusMessage(
            type=MessageType.TASK,
            source="orchestrator",
            target="test_python_brain",
            payload={
                "type": "execute_code",
                "files": {
                    "input.txt": "Hello from input file!"
                },
                "code": """
# Read input file and create output
with open('input.txt', 'r') as f:
    content = f.read()

with open('output.txt', 'w') as f:
    f.write(f"Processed: {content}")

print("Files processed successfully")
"""
            }
        )
        
        result = await python_brain.handle_task(task_message)
        
        assert result["success"] is True
        assert "Files processed successfully" in result["stdout"]
        assert "output.txt" in result["files_created"]
        
        # Check that output file was actually created
        output_file = python_brain.work_dir / "output.txt"
        assert output_file.exists()
        content = output_file.read_text()
        assert "Processed: Hello from input file!" in content
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self, python_brain):
        """Test timeout handling for long-running code."""
        task_message = BusMessage(
            type=MessageType.TASK,
            source="orchestrator",
            target="test_python_brain",
            payload={
                "type": "execute_code",
                "timeout": 1,  # Short timeout
                "code": """
import time
print("Starting long operation...")
time.sleep(5)  # This should timeout
print("This should not print")
"""
            }
        )
        
        result = await python_brain.handle_task(task_message)
        
        assert result["success"] is False
        assert result["timed_out"] is True
        assert result["exit_code"] == -1
        assert "timed out" in result["stderr"]
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_execution_environment(self, python_brain):
        """Test that execution environment is properly set up."""
        task_message = BusMessage(
            type=MessageType.TASK,
            source="orchestrator",
            target="test_python_brain",
            payload={
                "type": "execute_code",
                "code": """
import os
import sys

print(f"Python version: {sys.version_info[:3]}")
print(f"Working directory: {os.getcwd()}")
print(f"PYTHONPATH: {os.environ.get('PYTHONPATH', 'Not set')}")
print(f"PYTHONDONTWRITEBYTECODE: {os.environ.get('PYTHONDONTWRITEBYTECODE', 'Not set')}")
"""
            }
        )
        
        result = await python_brain.handle_task(task_message)
        
        assert result["success"] is True
        output = result["stdout"]
        
        assert "Python version:" in output
        assert "Working directory:" in output
        assert str(python_brain.work_dir) in output
        assert "PYTHONDONTWRITEBYTECODE: 1" in output
    
    @pytest.mark.asyncio
    async def test_invalid_task_type(self, python_brain):
        """Test handling of invalid task types."""
        task_message = BusMessage(
            type=MessageType.TASK,
            source="orchestrator",
            target="test_python_brain",
            payload={
                "type": "invalid_task_type",
                "data": "something"
            }
        )
        
        with pytest.raises(ValueError, match="Unknown task type"):
            await python_brain.handle_task(task_message)
    
    @pytest.mark.asyncio
    async def test_missing_code(self, python_brain):
        """Test handling of missing code in task."""
        task_message = BusMessage(
            type=MessageType.TASK,
            source="orchestrator", 
            target="test_python_brain",
            payload={
                "type": "execute_code"
                # No code provided
            }
        )
        
        with pytest.raises(ValueError, match="No code provided"):
            await python_brain.handle_task(task_message)
    
    @pytest.mark.asyncio
    async def test_capabilities_query(self, python_brain, mock_bus):
        """Test responding to capabilities query."""
        await python_brain.start()
        
        query_message = BusMessage(
            type=MessageType.QUERY,
            source="requester",
            target="test_python_brain",
            payload={"type": "capabilities"}
        )
        
        await python_brain._handle_message_wrapper(query_message)
        
        # Check capabilities response
        mock_bus.send_result.assert_called_once()
        result_data = mock_bus.send_result.call_args[1]["result_data"]
        
        assert result_data["brain_type"] == "python"
        assert "python_version" in result_data
        assert "features" in result_data
        assert "code_execution" in result_data["features"]
        assert "subprocess_isolation" in result_data["features"]
    
    @pytest.mark.asyncio
    async def test_cleanup(self, python_brain, temp_work_dir):
        """Test cleanup of temporary files."""
        # Create some temp files
        temp_file1 = python_brain.work_dir / "temp1.txt"
        temp_file2 = python_brain.work_dir / "temp2.txt"
        
        temp_file1.write_text("temp content 1")
        temp_file2.write_text("temp content 2")
        
        python_brain._temp_files.add(temp_file1)
        python_brain._temp_files.add(temp_file2)
        
        assert temp_file1.exists()
        assert temp_file2.exists()
        
        # Cleanup
        await python_brain.cleanup()
        
        # Files should be removed
        assert not temp_file1.exists()
        assert not temp_file2.exists()
        assert len(python_brain._temp_files) == 0
    
    def test_get_status(self, python_brain):
        """Test getting detailed Python brain status."""
        status = python_brain.get_status()
        
        assert status["name"] == "test_python_brain"
        assert status["brain_type"] == "python"
        assert "python_version" in status
        assert "work_dir" in status
        assert status["timeout"] == 5
        assert status["temp_files_count"] == 0
    
    @pytest.mark.asyncio
    async def test_cross_platform_execution(self, python_brain):
        """Test that execution works cross-platform."""
        # Test using sys.executable instead of hardcoded python3
        task_message = BusMessage(
            type=MessageType.TASK,
            source="orchestrator",
            target="test_python_brain",
            payload={
                "type": "execute_code",
                "code": """
import sys
import platform

print(f"Platform: {platform.system()}")
print(f"Python executable: {sys.executable}")
print("Cross-platform test successful")
"""
            }
        )
        
        result = await python_brain.handle_task(task_message)
        
        assert result["success"] is True
        assert "Cross-platform test successful" in result["stdout"]
        assert "Python executable:" in result["stdout"]