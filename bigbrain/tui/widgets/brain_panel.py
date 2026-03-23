"""Brain Panel - Live status display for all brain modules."""

import time
from datetime import datetime, timedelta

from textual.widgets import Static
from textual.containers import Vertical
from textual.reactive import reactive
from rich.text import Text
from rich.table import Table


class BrainStatus(Static):
    """Individual brain status widget."""
    
    def __init__(self, name: str, status: str = "offline", enabled: bool = False, **kwargs):
        """
        Initialize brain status.
        
        Args:
            name: Brain name
            status: Current status
            enabled: Whether brain is enabled
        """
        self.name = name
        self.status = status
        self.enabled = enabled
        self.last_task = None
        self.last_activity = None
        self.task_count = 0
        
        super().__init__(**kwargs)
        self._update_display()
    
    def update_status(self, status: str, enabled: bool = None, task: str = None) -> None:
        """
        Update brain status.
        
        Args:
            status: New status
            enabled: New enabled state
            task: Current task description
        """
        self.status = status
        if enabled is not None:
            self.enabled = enabled
        if task:
            self.last_task = task
            self.task_count += 1
        
        self.last_activity = datetime.now()
        self._update_display()
    
    def _update_display(self) -> None:
        """Update the display content."""
        # Status emoji and color
        if not self.enabled:
            emoji = "🔇"
            color = "red"
        elif self.status == "busy":
            emoji = "🔄"
            color = "yellow"
        elif self.status in ["online", "ready", "idle"]:
            emoji = "🟢"
            color = "green"
        else:
            emoji = "⚫"
            color = "red"
        
        # Format brain name
        brain_display = self.name.replace("_brain", "").replace("_", " ").title()
        
        # Build display text
        text = Text()
        text.append(f"{brain_display}: ", style="bold")
        text.append(f"{emoji} ", style=color)
        text.append(self.status, style=color)
        
        # Add task info if available
        if self.last_task:
            text.append(f"\n  └ {self.last_task[:30]}...", style="dim")
        
        # Add activity info
        if self.last_activity:
            time_ago = datetime.now() - self.last_activity
            if time_ago.total_seconds() < 60:
                activity_str = f"{int(time_ago.total_seconds())}s ago"
            else:
                activity_str = f"{int(time_ago.total_seconds() // 60)}m ago"
            text.append(f"\n  {activity_str} | Tasks: {self.task_count}", style="dim")
        
        self.update(text)


class BrainPanel(Vertical):
    """
    Brain panel widget showing live status of all brain modules.
    
    Features:
    - Real-time brain status (online, offline, busy, idle)
    - Current task display
    - Activity indicators
    - Task counters
    - Color-coded status indicators
    """
    
    def __init__(self, **kwargs):
        """Initialize brain panel."""
        self.brains = {}
        super().__init__(**kwargs)
    
    def compose(self):
        """Compose the brain panel."""
        # Initialize default brains
        yield BrainStatus("python_brain", "offline", False, id="python_brain_status")
        yield BrainStatus("researcher", "offline", False, id="researcher_status") 
        yield BrainStatus("voice_brain", "disabled", False, id="voice_brain_status")
        yield Static("", id="brain_summary")
    
    def on_mount(self) -> None:
        """Handle mounting."""
        # Initialize brain references after mounting
        self.call_after_refresh(self._setup_brain_refs)
        self.update_summary()
    
    def _setup_brain_refs(self) -> None:
        """Set up brain widget references after mounting."""
        try:
            self.brains = {
                "python_brain": self.query_one("#python_brain_status"),
                "researcher": self.query_one("#researcher_status"),
                "voice_brain": self.query_one("#voice_brain_status")
            }
        except Exception:
            # Widgets not ready yet, will retry
            pass
    
    def update_brain_status(self, brain_name: str, status: str, enabled: bool = None, task: str = None) -> None:
        """
        Update status for a specific brain.
        
        Args:
            brain_name: Name of the brain
            status: New status
            enabled: Whether brain is enabled
            task: Current task description
        """
        if brain_name in self.brains:
            try:
                brain_widget = self.brains[brain_name]
                brain_widget.update_status(status, enabled, task)
                self.update_summary()
            except Exception:
                # Widget might not be ready yet
                pass
    
    def add_brain(self, brain_name: str, initial_status: str = "offline") -> None:
        """
        Add a new brain to monitoring.
        
        Args:
            brain_name: Name of the new brain
            initial_status: Initial status
        """
        if brain_name not in self.brains:
            brain_status = BrainStatus(brain_name, initial_status, False)
            self.mount(brain_status)
            self.brains[brain_name] = brain_status
            self.update_summary()
    
    def remove_brain(self, brain_name: str) -> None:
        """
        Remove a brain from monitoring.
        
        Args:
            brain_name: Name of the brain to remove
        """
        if brain_name in self.brains:
            brain_widget = self.brains[brain_name]
            brain_widget.remove()
            del self.brains[brain_name]
            self.update_summary()
    
    def update_summary(self) -> None:
        """Update the summary display."""
        try:
            summary_widget = self.query_one("#brain_summary")
        except Exception:
            return  # Widget not ready yet
        
        # Count brain states
        online_count = 0
        busy_count = 0
        total_count = len(self.brains)
        total_tasks = 0
        
        for brain_name, brain_widget in self.brains.items():
            if hasattr(brain_widget, 'enabled') and brain_widget.enabled:
                if brain_widget.status == "busy":
                    busy_count += 1
                    online_count += 1
                elif brain_widget.status in ["online", "ready", "idle"]:
                    online_count += 1
            
            if hasattr(brain_widget, 'task_count'):
                total_tasks += brain_widget.task_count
        
        # Build summary text
        summary = Text()
        summary.append("─" * 20 + "\n", style="dim")
        summary.append(f"Online: {online_count}/{total_count}", style="green" if online_count > 0 else "red")
        if busy_count > 0:
            summary.append(f" | Active: {busy_count}", style="yellow")
        summary.append(f"\nTotal Tasks: {total_tasks}", style="cyan")
        
        summary_widget.update(summary)
    
    def get_brain_status(self, brain_name: str) -> dict:
        """
        Get status information for a specific brain.
        
        Args:
            brain_name: Name of the brain
            
        Returns:
            Status dictionary or empty dict if brain not found
        """
        if brain_name not in self.brains:
            return {}
        
        brain_widget = self.brains[brain_name]
        return {
            "name": brain_widget.name,
            "status": brain_widget.status,
            "enabled": brain_widget.enabled,
            "last_task": brain_widget.last_task,
            "last_activity": brain_widget.last_activity,
            "task_count": brain_widget.task_count
        }
    
    def get_all_brain_status(self) -> dict:
        """
        Get status for all brains.
        
        Returns:
            Dictionary of brain statuses
        """
        status = {}
        for brain_name in self.brains:
            status[brain_name] = self.get_brain_status(brain_name)
        return status
    
    def simulate_brain_activity(self, brain_name: str, task: str) -> None:
        """
        Simulate brain activity for demo purposes.
        
        Args:
            brain_name: Brain to simulate
            task: Task description
        """
        if brain_name not in self.brains:
            return
        
        # Start task
        self.update_brain_status(brain_name, "busy", True, task)
        
        # Schedule completion (in a real app, this would come from actual events)
        self.call_later(3.0, lambda: self.update_brain_status(brain_name, "idle", True))