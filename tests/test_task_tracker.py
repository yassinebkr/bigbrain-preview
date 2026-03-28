"""Tests for TaskTracker system."""

import time
from unittest.mock import Mock

import pytest

from bigbrain.orchestrator.task_tracker import (
    TaskTracker, TrackedTask, TaskStatus, TaskPriority
)


class TestTrackedTask:
    """Test TrackedTask functionality."""
    
    def test_create_tracked_task(self):
        """Test creating a TrackedTask."""
        task = TrackedTask(
            id="task_1",
            description="Test task",
            status=TaskStatus.PENDING,
            priority=TaskPriority.HIGH
        )
        
        assert task.id == "task_1"
        assert task.description == "Test task"
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.HIGH
        assert task.result_summary is None
        assert task.created_at > 0
        assert task.started_at is None
        assert task.completed_at is None
    
    def test_task_duration_calculation(self):
        """Test task duration calculation."""
        task = TrackedTask("task_1", "Test task")
        
        # No duration without start time
        assert task.duration is None
        
        # Set start time
        task.started_at = time.time() - 5.0  # 5 seconds ago
        duration = task.duration
        assert duration is not None
        assert 4.5 <= duration <= 5.5  # Approximate duration
        
        # Set completion time
        task.completed_at = task.started_at + 3.0
        assert task.duration == 3.0


class TestTaskTracker:
    """Test TaskTracker functionality."""
    
    def test_create_empty_tracker(self):
        """Test creating empty TaskTracker."""
        tracker = TaskTracker()
        
        assert len(tracker.tasks) == 0
        assert tracker.created_at > 0
        assert tracker.last_updated > 0
    
    def test_create_from_plan(self):
        """Test creating TaskTracker from subtasks."""
        # Create mock subtasks
        subtask1 = Mock()
        subtask1.id = "sub1"
        subtask1.description = "Write models.py"
        subtask1.dependencies = set()
        subtask1.status = Mock()
        subtask1.status.value = "pending"
        
        subtask2 = Mock()
        subtask2.id = "sub2" 
        subtask2.description = "Write app.py"
        subtask2.dependencies = {"sub1"}
        subtask2.status = Mock()
        subtask2.status.value = "running"
        
        subtasks = [subtask1, subtask2]
        
        tracker = TaskTracker.create_from_plan(subtasks)
        
        assert len(tracker.tasks) == 2
        assert "sub1" in tracker.tasks
        assert "sub2" in tracker.tasks
        
        # Check task 1 (independent, should be high priority)
        task1 = tracker.tasks["sub1"]
        assert task1.description == "models.py"  # Cleaned description
        assert task1.priority == TaskPriority.HIGH  # Independent task
        assert task1.status == TaskStatus.PENDING
        
        # Check task 2 (dependent, should be normal priority)
        task2 = tracker.tasks["sub2"]
        assert task2.description == "app.py"
        assert task2.priority == TaskPriority.NORMAL
        assert task2.status == TaskStatus.IN_PROGRESS
    
    def test_update_status(self):
        """Test updating task status."""
        tracker = TaskTracker()
        
        # Add a task manually
        task = TrackedTask("test_task", "Test task")
        tracker.tasks["test_task"] = task
        
        # Update status to in progress
        result = tracker.update_status("test_task", TaskStatus.IN_PROGRESS)
        assert result is True
        assert task.status == TaskStatus.IN_PROGRESS
        assert task.started_at is not None
        
        # Update status to complete with result summary
        result = tracker.update_status("test_task", TaskStatus.COMPLETE, "Successfully completed")
        assert result is True
        assert task.status == TaskStatus.COMPLETE
        assert task.result_summary == "Successfully completed"
        assert task.completed_at is not None
        
        # Try to update non-existent task
        result = tracker.update_status("nonexistent", TaskStatus.COMPLETE)
        assert result is False
    
    def test_render_for_prompt(self):
        """Test rendering task state for LLM prompt."""
        tracker = TaskTracker()
        
        # Empty tracker
        prompt_text = tracker.render_for_prompt()
        assert prompt_text == "No tasks to track."
        
        # Add some tasks
        task1 = TrackedTask("task1", "Complete task", TaskStatus.COMPLETE, TaskPriority.HIGH)
        task2 = TrackedTask("task2", "Running task", TaskStatus.IN_PROGRESS, TaskPriority.NORMAL) 
        task3 = TrackedTask("task3", "Pending task", TaskStatus.PENDING, TaskPriority.LOW)
        task4 = TrackedTask("task4", "Failed task", TaskStatus.FAILED, TaskPriority.NORMAL)
        
        tracker.tasks = {
            "task1": task1,
            "task2": task2, 
            "task3": task3,
            "task4": task4
        }
        
        prompt_text = tracker.render_for_prompt()
        
        # Check that all status groups are represented
        assert "✓ 1 completed" in prompt_text
        assert "In Progress:" in prompt_text
        assert "Running task" in prompt_text
        assert "Pending:" in prompt_text
        assert "Pending task" in prompt_text
        assert "Failed:" in prompt_text
        assert "Failed task" in prompt_text
    
    def test_render_for_ui(self):
        """Test rendering task state for UI."""
        tracker = TaskTracker()
        
        # Add test tasks
        task1 = TrackedTask("task1", "Task 1", TaskStatus.COMPLETE)
        task2 = TrackedTask("task2", "Task 2", TaskStatus.IN_PROGRESS)
        task3 = TrackedTask("task3", "Task 3", TaskStatus.PENDING)
        
        tracker.tasks = {"task1": task1, "task2": task2, "task3": task3}
        
        ui_data = tracker.render_for_ui()
        
        # Check structure
        assert "tasks" in ui_data
        assert "summary" in ui_data
        assert len(ui_data["tasks"]) == 3
        
        # Check summary stats
        summary = ui_data["summary"]
        assert summary["total"] == 3
        assert summary["completed"] == 1
        assert summary["in_progress"] == 1
        assert summary["pending"] == 1
        assert summary["failed"] == 0
        assert summary["completion_percent"] == pytest.approx(33.33, rel=1e-2)
    
    def test_to_ws_event(self):
        """Test WebSocket event formatting."""
        tracker = TaskTracker()
        
        # Add a test task
        task = TrackedTask("task1", "Test task", TaskStatus.IN_PROGRESS, TaskPriority.HIGH)
        tracker.tasks = {"task1": task}
        
        ws_event = tracker.to_ws_event()
        
        # Check event structure
        assert ws_event["event_type"] == "task_tracker.updated"
        assert "data" in ws_event
        assert "task_tracker" in ws_event["data"]
        assert "interactive_checklist" in ws_event["data"]
        
        # Check interactive checklist
        checklist = ws_event["data"]["interactive_checklist"]
        assert len(checklist["items"]) == 1
        
        item = checklist["items"][0]
        assert item["id"] == "task1"
        assert item["description"] == "Test task"
        assert item["status"] == "in_progress"
        assert item["priority"] == "high"
        assert item["status_icon"] == "⏳"
        assert item["priority_color"] == "#ff4444"
        assert item["can_cancel"] is True
        assert item["can_retry"] is False
    
    def test_get_tasks_by_status(self):
        """Test getting tasks by status."""
        tracker = TaskTracker()
        
        task1 = TrackedTask("task1", "Task 1", TaskStatus.COMPLETE)
        task2 = TrackedTask("task2", "Task 2", TaskStatus.COMPLETE)
        task3 = TrackedTask("task3", "Task 3", TaskStatus.PENDING)
        
        tracker.tasks = {"task1": task1, "task2": task2, "task3": task3}
        
        completed_tasks = tracker.get_tasks_by_status(TaskStatus.COMPLETE)
        assert len(completed_tasks) == 2
        assert all(task.status == TaskStatus.COMPLETE for task in completed_tasks)
        
        pending_tasks = tracker.get_tasks_by_status(TaskStatus.PENDING)
        assert len(pending_tasks) == 1
        assert pending_tasks[0].id == "task3"
    
    def test_get_summary_stats(self):
        """Test getting summary statistics."""
        tracker = TaskTracker()
        
        # Add tasks with different statuses
        tracker.tasks = {
            "task1": TrackedTask("task1", "Task 1", TaskStatus.COMPLETE),
            "task2": TrackedTask("task2", "Task 2", TaskStatus.COMPLETE), 
            "task3": TrackedTask("task3", "Task 3", TaskStatus.IN_PROGRESS),
            "task4": TrackedTask("task4", "Task 4", TaskStatus.FAILED),
            "task5": TrackedTask("task5", "Task 5", TaskStatus.PENDING)
        }
        
        stats = tracker.get_summary_stats()
        
        assert stats["total"] == 5
        assert stats["complete"] == 2
        assert stats["in_progress"] == 1
        assert stats["failed"] == 1
        assert stats["pending"] == 1
        assert stats["skipped"] == 0
    
    def test_progress_percent_calculation(self):
        """Test progress percentage calculation."""
        tracker = TaskTracker()
        
        # Test different task states
        complete_task = {"status": "complete"}
        assert tracker._calculate_progress_percent(complete_task) == 100
        
        failed_task = {"status": "failed"}
        assert tracker._calculate_progress_percent(failed_task) == 0
        
        pending_task = {"status": "pending"}
        assert tracker._calculate_progress_percent(pending_task) == 0
        
        # In-progress without duration
        in_progress_task = {"status": "in_progress"}
        assert tracker._calculate_progress_percent(in_progress_task) == 50
        
        # In-progress with duration
        in_progress_with_duration = {"status": "in_progress", "duration": 15.0}
        progress = tracker._calculate_progress_percent(in_progress_with_duration)
        assert 0 <= progress <= 90  # Should be between 0 and 90
    
    def test_status_icon_mapping(self):
        """Test status icon mapping."""
        tracker = TaskTracker()
        
        assert tracker._get_status_icon("complete") == "✅"
        assert tracker._get_status_icon("in_progress") == "⏳"
        assert tracker._get_status_icon("pending") == "⏸️"
        assert tracker._get_status_icon("failed") == "❌"
        assert tracker._get_status_icon("skipped") == "⏭️"
        assert tracker._get_status_icon("unknown") == "❓"
    
    def test_priority_color_mapping(self):
        """Test priority color mapping.""" 
        tracker = TaskTracker()
        
        assert tracker._get_priority_color("high") == "#ff4444"
        assert tracker._get_priority_color("normal") == "#4488ff"
        assert tracker._get_priority_color("low") == "#44ff44"
        assert tracker._get_priority_color("unknown") == "#888888"