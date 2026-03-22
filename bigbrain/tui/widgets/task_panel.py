"""Task Panel - Active tasks with progress tracking."""

import time
from datetime import datetime, timedelta

from textual.widgets import Static, ProgressBar
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from rich.text import Text


class TaskItem(Vertical):
    """Individual task item with progress tracking."""
    
    def __init__(self, task_id: str, description: str, **kwargs):
        """
        Initialize task item.
        
        Args:
            task_id: Unique task identifier
            description: Task description
        """
        self.task_id = task_id
        self.description = description
        self.status = "pending"
        self.progress = 0.0
        self.start_time = datetime.now()
        self.subtasks = []
        self.current_subtask = None
        
        super().__init__(**kwargs)
    
    def compose(self):
        """Compose the task item."""
        with Horizontal():
            yield Static(self._format_task_header(), id=f"task_header_{self.task_id}")
        
        yield ProgressBar(
            total=100,
            show_eta=True,
            show_percentage=True,
            id=f"task_progress_{self.task_id}"
        )
        
        yield Static("", id=f"task_details_{self.task_id}")
    
    def update_progress(self, progress: float, status: str = None, subtask: str = None) -> None:
        """
        Update task progress.
        
        Args:
            progress: Progress percentage (0-100)
            status: New status
            subtask: Current subtask description
        """
        self.progress = max(0, min(100, progress))
        
        if status:
            self.status = status
        if subtask:
            self.current_subtask = subtask
        
        # Update widgets
        try:
            # Update header
            header_widget = self.query_one(f"#task_header_{self.task_id}")
            header_widget.update(self._format_task_header())
            
            # Update progress bar
            progress_widget = self.query_one(f"#task_progress_{self.task_id}")
            progress_widget.update(progress=self.progress)
            
            # Update details
            details_widget = self.query_one(f"#task_details_{self.task_id}")
            details_widget.update(self._format_task_details())
            
        except Exception:
            # Widgets might not be ready yet
            pass
    
    def add_subtask(self, subtask: str) -> None:
        """
        Add a subtask to the task.
        
        Args:
            subtask: Subtask description
        """
        self.subtasks.append({
            "description": subtask,
            "timestamp": datetime.now(),
            "status": "active"
        })
        self.current_subtask = subtask
        self.update_progress(self.progress, self.status, subtask)
    
    def complete_subtask(self, subtask: str = None) -> None:
        """
        Mark a subtask as complete.
        
        Args:
            subtask: Subtask to complete (current if None)
        """
        target_subtask = subtask or self.current_subtask
        
        for st in self.subtasks:
            if st["description"] == target_subtask:
                st["status"] = "complete"
                break
        
        self.current_subtask = None
        self.update_progress(self.progress, self.status)
    
    def _format_task_header(self) -> Text:
        """Format the task header."""
        text = Text()
        
        # Task ID and description
        text.append(f"Task {self.task_id}: ", style="bold")
        text.append(self.description[:40], style="white")
        if len(self.description) > 40:
            text.append("...", style="dim")
        
        # Status emoji
        if self.status == "pending":
            text.append(" ⏳", style="yellow")
        elif self.status == "running":
            text.append(" 🔄", style="cyan")
        elif self.status == "complete":
            text.append(" ✅", style="green")
        elif self.status == "failed":
            text.append(" ❌", style="red")
        elif self.status == "paused":
            text.append(" ⏸️", style="yellow")
        
        return text
    
    def _format_task_details(self) -> Text:
        """Format task details."""
        text = Text()
        
        # Current subtask
        if self.current_subtask:
            text.append(f"  └ {self.current_subtask}", style="cyan")
        
        # Timing info
        elapsed = datetime.now() - self.start_time
        elapsed_str = f"{int(elapsed.total_seconds())}s"
        if elapsed.total_seconds() > 60:
            elapsed_str = f"{int(elapsed.total_seconds() // 60)}m {int(elapsed.total_seconds() % 60)}s"
        
        text.append(f"\n  Time: {elapsed_str}", style="dim")
        
        # Subtask count
        completed_subtasks = sum(1 for st in self.subtasks if st["status"] == "complete")
        if self.subtasks:
            text.append(f" | Steps: {completed_subtasks}/{len(self.subtasks)}", style="dim")
        
        return text


class TaskPanel(Vertical):
    """
    Task panel widget showing active tasks with progress.
    
    Features:
    - Real-time progress tracking
    - Subtask breakdown
    - Timing information
    - Visual progress bars
    - Status indicators
    - Task flow visualization
    """
    
    def __init__(self, **kwargs):
        """Initialize task panel."""
        self.tasks = {}
        self.task_counter = 0
        super().__init__(**kwargs)
    
    def compose(self):
        """Compose the task panel."""
        yield Static("No active tasks", id="empty_message", classes="dim")
        yield Static("", id="task_summary")
    
    def add_task(self, description: str, task_id: str = None) -> str:
        """
        Add a new task to tracking.
        
        Args:
            description: Task description
            task_id: Custom task ID (auto-generated if None)
            
        Returns:
            Task ID
        """
        if not task_id:
            self.task_counter += 1
            task_id = f"task_{self.task_counter}"
        
        # Remove empty message if this is first task
        if not self.tasks:
            try:
                empty_msg = self.query_one("#empty_message")
                empty_msg.remove()
            except Exception:
                pass
        
        # Create task widget
        task_item = TaskItem(task_id, description)
        self.mount(task_item)
        self.tasks[task_id] = task_item
        
        self.update_summary()
        return task_id
    
    def update_task_progress(
        self, 
        task_id: str, 
        progress: float, 
        status: str = None,
        subtask: str = None
    ) -> bool:
        """
        Update progress for a specific task.
        
        Args:
            task_id: Task identifier
            progress: Progress percentage (0-100)
            status: New status
            subtask: Current subtask
            
        Returns:
            True if task was updated successfully
        """
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        task.update_progress(progress, status, subtask)
        self.update_summary()
        return True
    
    def add_subtask(self, task_id: str, subtask: str) -> bool:
        """
        Add a subtask to a task.
        
        Args:
            task_id: Task identifier
            subtask: Subtask description
            
        Returns:
            True if subtask was added successfully
        """
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        task.add_subtask(subtask)
        return True
    
    def complete_task(self, task_id: str, success: bool = True) -> bool:
        """
        Mark a task as complete.
        
        Args:
            task_id: Task identifier
            success: Whether task completed successfully
            
        Returns:
            True if task was completed successfully
        """
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        status = "complete" if success else "failed"
        task.update_progress(100 if success else task.progress, status)
        
        # Schedule removal after a delay
        self.call_later(5.0, lambda: self.remove_task(task_id))
        
        self.update_summary()
        return True
    
    def remove_task(self, task_id: str) -> bool:
        """
        Remove a task from tracking.
        
        Args:
            task_id: Task identifier
            
        Returns:
            True if task was removed successfully
        """
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        task.remove()
        del self.tasks[task_id]
        
        # Show empty message if no tasks remain
        if not self.tasks:
            empty_msg = Static("No active tasks", id="empty_message", classes="dim")
            self.mount(empty_msg)
        
        self.update_summary()
        return True
    
    def get_task_status(self, task_id: str) -> dict:
        """
        Get status for a specific task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task status dictionary
        """
        if task_id not in self.tasks:
            return {}
        
        task = self.tasks[task_id]
        return {
            "id": task.task_id,
            "description": task.description,
            "status": task.status,
            "progress": task.progress,
            "start_time": task.start_time.isoformat(),
            "current_subtask": task.current_subtask,
            "subtasks": task.subtasks.copy(),
            "elapsed_seconds": (datetime.now() - task.start_time).total_seconds()
        }
    
    def get_all_tasks(self) -> dict:
        """
        Get status for all tasks.
        
        Returns:
            Dictionary of all task statuses
        """
        return {task_id: self.get_task_status(task_id) for task_id in self.tasks}
    
    def update_summary(self) -> None:
        """Update the task summary display."""
        try:
            summary_widget = self.query_one("#task_summary")
        except Exception:
            return  # Widget not ready yet
        
        if not self.tasks:
            summary_widget.update("")
            return
        
        # Calculate statistics
        total = len(self.tasks)
        running = sum(1 for t in self.tasks.values() if t.status == "running")
        complete = sum(1 for t in self.tasks.values() if t.status == "complete")
        failed = sum(1 for t in self.tasks.values() if t.status == "failed")
        
        avg_progress = sum(t.progress for t in self.tasks.values()) / total if total > 0 else 0
        
        # Build summary
        text = Text()
        text.append("─" * 20 + "\n", style="dim")
        text.append(f"Active: {running}", style="cyan")
        text.append(f" | Done: {complete}", style="green")
        if failed > 0:
            text.append(f" | Failed: {failed}", style="red")
        text.append(f"\nAvg Progress: {avg_progress:.1f}%", style="white")
        
        summary_widget.update(text)
    
    def simulate_task_workflow(self, description: str) -> str:
        """
        Simulate a complete task workflow for demo purposes.
        
        Args:
            description: Task description
            
        Returns:
            Task ID
        """
        task_id = self.add_task(description)
        
        # Simulate task progression
        async def run_simulation():
            import asyncio
            
            # Start task
            self.update_task_progress(task_id, 0, "running")
            await asyncio.sleep(1)
            
            # Planning phase
            self.add_subtask(task_id, "Planning and analysis")
            self.update_task_progress(task_id, 20, "running")
            await asyncio.sleep(1.5)
            
            # Execution phase
            self.add_subtask(task_id, "Executing main logic")
            self.update_task_progress(task_id, 50, "running")
            await asyncio.sleep(2)
            
            # Verification phase
            self.add_subtask(task_id, "Verifying results")
            self.update_task_progress(task_id, 80, "running")
            await asyncio.sleep(1)
            
            # Complete
            self.update_task_progress(task_id, 100, "complete")
        
        # Start simulation
        import asyncio
        asyncio.create_task(run_simulation())
        
        return task_id