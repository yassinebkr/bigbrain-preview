"""TaskTracker - TodoWrite equivalent for BigBrain orchestrator."""

import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(str, Enum):
    """Status values for tracked tasks."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskPriority(str, Enum):
    """Priority values for tracked tasks."""
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class TrackedTask:
    """Individual tracked task item."""
    id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    result_summary: Optional[str] = None
    created_at: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()
    
    @property
    def duration(self) -> Optional[float]:
        """Duration in seconds if task has started."""
        if not self.started_at:
            return None
        end_time = self.completed_at or time.time()
        return end_time - self.started_at


class TaskTracker:
    """
    TaskTracker maintains a structured task list for the orchestrator.
    
    Like Claude Code's TodoWrite, this shows the current state of ALL tasks
    in a compact text format after each operation, keeping brains aware of
    what's done and what's left.
    
    Key features:
    - Maintains structured task list with id, description, status, priority
    - Provides compact text rendering for LLM prompt injection
    - Provides structured data for Web UI / TUI rendering
    - Tracks task timing and result summaries
    """
    
    def __init__(self):
        self.tasks: Dict[str, TrackedTask] = {}
        self.created_at = time.time()
        self.last_updated = time.time()
    
    @classmethod
    def create_from_plan(cls, subtasks: List[Any]) -> 'TaskTracker':
        """
        Create a TaskTracker from orchestrator subtasks.
        
        Args:
            subtasks: List of SubTask objects from the orchestrator
            
        Returns:
            TaskTracker instance with tasks initialized from subtasks
        """
        tracker = cls()
        
        for subtask in subtasks:
            # Extract a clean description (remove redundant project name)
            description = subtask.description
            # Remove common prefixes like "Write project.py:" to keep clean
            for prefix in ["Write ", "Generate ", "Create "]:
                if description.startswith(prefix):
                    description = description[len(prefix):]
                    break
            
            # Determine priority based on subtask characteristics
            priority = TaskPriority.NORMAL
            if hasattr(subtask, 'dependencies') and len(subtask.dependencies) == 0:
                priority = TaskPriority.HIGH  # Independent tasks get high priority
            elif "assemble" in subtask.description.lower() or "run" in subtask.description.lower():
                priority = TaskPriority.LOW  # Assembly/execution tasks are lower priority
            
            # Map orchestrator status to tracker status
            if hasattr(subtask, 'status'):
                if subtask.status.value == "pending":
                    status = TaskStatus.PENDING
                elif subtask.status.value == "running":
                    status = TaskStatus.IN_PROGRESS
                elif subtask.status.value == "complete":
                    status = TaskStatus.COMPLETE
                elif subtask.status.value == "failed":
                    status = TaskStatus.FAILED
                else:
                    status = TaskStatus.PENDING
            else:
                status = TaskStatus.PENDING
            
            task = TrackedTask(
                id=subtask.id,
                description=description,
                status=status,
                priority=priority
            )
            
            # Set timing from subtask if available
            if hasattr(subtask, 'start_time') and subtask.start_time:
                task.started_at = subtask.start_time
            if hasattr(subtask, 'end_time') and subtask.end_time:
                task.completed_at = subtask.end_time
            
            tracker.tasks[task.id] = task
        
        tracker.last_updated = time.time()
        return tracker
    
    def update_status(self, task_id: str, status: TaskStatus, 
                     result_summary: Optional[str] = None) -> bool:
        """
        Update the status of a tracked task.
        
        Args:
            task_id: ID of the task to update
            status: New status for the task
            result_summary: Optional summary of the result
            
        Returns:
            True if task was found and updated, False if task not found
        """
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        old_status = task.status
        task.status = status
        
        if result_summary:
            task.result_summary = result_summary
        
        # Update timing
        current_time = time.time()
        if old_status == TaskStatus.PENDING and status == TaskStatus.IN_PROGRESS:
            task.started_at = current_time
        elif status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.SKIPPED):
            task.completed_at = current_time
        
        self.last_updated = current_time
        return True
    
    def render_for_prompt(self) -> str:
        """
        Render task state as compact text for LLM prompt injection.
        
        Like Claude Code's TodoWrite, this provides a compact overview of
        all tasks showing current progress state.
        
        Returns:
            Compact text representation showing task progress
        """
        if not self.tasks:
            return "No tasks to track."
        
        lines = []
        
        # Group tasks by status for better readability
        status_groups = {
            TaskStatus.COMPLETE: [],
            TaskStatus.IN_PROGRESS: [],
            TaskStatus.PENDING: [],
            TaskStatus.FAILED: [],
            TaskStatus.SKIPPED: []
        }
        
        for task in self.tasks.values():
            status_groups[task.status].append(task)
        
        # Show completed tasks first (concise)
        if status_groups[TaskStatus.COMPLETE]:
            completed_count = len(status_groups[TaskStatus.COMPLETE])
            lines.append(f"✓ {completed_count} completed")
        
        # Show in-progress tasks
        if status_groups[TaskStatus.IN_PROGRESS]:
            lines.append("In Progress:")
            for task in sorted(status_groups[TaskStatus.IN_PROGRESS], 
                              key=lambda t: t.created_at):
                duration_str = ""
                if task.duration:
                    duration_str = f" ({task.duration:.1f}s)"
                lines.append(f"  ⏳ {task.description}{duration_str}")
        
        # Show pending tasks (prioritized)
        if status_groups[TaskStatus.PENDING]:
            pending_high = [t for t in status_groups[TaskStatus.PENDING] 
                           if t.priority == TaskPriority.HIGH]
            pending_normal = [t for t in status_groups[TaskStatus.PENDING] 
                             if t.priority == TaskPriority.NORMAL]
            pending_low = [t for t in status_groups[TaskStatus.PENDING] 
                          if t.priority == TaskPriority.LOW]
            
            lines.append("Pending:")
            for task in pending_high + pending_normal + pending_low:
                priority_marker = "🔥" if task.priority == TaskPriority.HIGH else ""
                lines.append(f"  ⏸️ {priority_marker}{task.description}")
        
        # Show failed tasks
        if status_groups[TaskStatus.FAILED]:
            lines.append("Failed:")
            for task in status_groups[TaskStatus.FAILED]:
                error_text = task.result_summary or "unknown error"
                lines.append(f"  ❌ {task.description} ({error_text})")
        
        # Show skipped tasks
        if status_groups[TaskStatus.SKIPPED]:
            skipped_count = len(status_groups[TaskStatus.SKIPPED])
            lines.append(f"⏭️ {skipped_count} skipped")
        
        return "\n".join(lines)
    
    def render_for_ui(self) -> Dict[str, Any]:
        """
        Render task state as structured data for Web UI / TUI.
        
        Returns:
            Dictionary with structured task data for UI rendering
        """
        task_items = []
        for task in sorted(self.tasks.values(), key=lambda t: t.created_at):
            task_items.append({
                "id": task.id,
                "description": task.description,
                "status": task.status.value,
                "priority": task.priority.value,
                "result_summary": task.result_summary,
                "created_at": task.created_at,
                "started_at": task.started_at,
                "completed_at": task.completed_at,
                "duration": task.duration
            })
        
        # Calculate summary statistics
        total_tasks = len(self.tasks)
        completed = len([t for t in self.tasks.values() if t.status == TaskStatus.COMPLETE])
        in_progress = len([t for t in self.tasks.values() if t.status == TaskStatus.IN_PROGRESS])
        pending = len([t for t in self.tasks.values() if t.status == TaskStatus.PENDING])
        failed = len([t for t in self.tasks.values() if t.status == TaskStatus.FAILED])
        
        return {
            "tasks": task_items,
            "summary": {
                "total": total_tasks,
                "completed": completed,
                "in_progress": in_progress,
                "pending": pending,
                "failed": failed,
                "completion_percent": (completed / total_tasks * 100) if total_tasks > 0 else 0
            },
            "created_at": self.created_at,
            "last_updated": self.last_updated
        }
    
    def to_ws_event(self) -> Dict[str, Any]:
        """
        Return a dict suitable for broadcasting over WebSocket.
        
        Includes task_id, items with id/description/status/priority/duration
        for real-time UI updates.
        
        Returns:
            Dictionary formatted for WebSocket broadcast
        """
        ui_data = self.render_for_ui()
        
        # Enhanced WebSocket format with additional metadata for UI
        return {
            "event_type": "task_tracker.updated",
            "data": {
                "task_tracker": ui_data,
                "timestamp": time.time(),
                "interactive_checklist": {
                    "items": [
                        {
                            "id": task["id"],
                            "description": task["description"],
                            "status": task["status"],
                            "priority": task["priority"],
                            "duration": task.get("duration"),
                            "progress_percent": self._calculate_progress_percent(task),
                            "can_retry": task["status"] == "failed",
                            "can_cancel": task["status"] in ["pending", "in_progress"],
                            "status_icon": self._get_status_icon(task["status"]),
                            "priority_color": self._get_priority_color(task["priority"])
                        }
                        for task in ui_data["tasks"]
                    ],
                    "summary": ui_data["summary"],
                    "actions_available": {
                        "can_pause_all": ui_data["summary"]["in_progress"] > 0,
                        "can_retry_failed": ui_data["summary"]["failed"] > 0,
                        "can_cancel_pending": ui_data["summary"]["pending"] > 0
                    }
                }
            }
        }
    
    def _calculate_progress_percent(self, task: Dict[str, Any]) -> int:
        """Calculate progress percentage for a task."""
        status = task["status"]
        if status == "complete":
            return 100
        elif status == "in_progress":
            # If duration is available, estimate progress based on typical task duration
            if task.get("duration"):
                # Simple heuristic: assume tasks take 30 seconds on average
                progress = min(90, int(task["duration"] / 30 * 100))
                return progress
            return 50  # Default for in-progress without duration info
        elif status == "failed":
            return 0
        else:  # pending, skipped
            return 0
    
    def _get_status_icon(self, status: str) -> str:
        """Get icon for task status."""
        icons = {
            "complete": "✅",
            "in_progress": "⏳", 
            "pending": "⏸️",
            "failed": "❌",
            "skipped": "⏭️"
        }
        return icons.get(status, "❓")
    
    def _get_priority_color(self, priority: str) -> str:
        """Get color code for task priority."""
        colors = {
            "high": "#ff4444",    # red
            "normal": "#4488ff",  # blue  
            "low": "#44ff44"      # green
        }
        return colors.get(priority, "#888888")
    
    def get_task(self, task_id: str) -> Optional[TrackedTask]:
        """Get a specific task by ID."""
        return self.tasks.get(task_id)
    
    def get_tasks_by_status(self, status: TaskStatus) -> List[TrackedTask]:
        """Get all tasks with a specific status."""
        return [task for task in self.tasks.values() if task.status == status]
    
    def get_summary_stats(self) -> Dict[str, int]:
        """Get summary statistics for all tasks."""
        stats = {status.value: 0 for status in TaskStatus}
        for task in self.tasks.values():
            stats[task.status.value] += 1
        stats["total"] = len(self.tasks)
        return stats