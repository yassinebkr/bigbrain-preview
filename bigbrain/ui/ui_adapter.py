"""UIAdapter - Abstract interface for BigBrain user interfaces."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class UIAdapter(ABC):
    """
    Abstract interface for BigBrain user interfaces.
    
    Provides a consistent API that different UI implementations can use:
    - RichAdapter (terminal with Rich library)
    - TextualAdapter (interactive TUI with mouse support)
    - WebAdapter (browser-based interface)
    - CLIAdapter (simple command line)
    
    The core BigBrain system only talks to this interface,
    making UI swapping seamless.
    """
    
    @abstractmethod
    async def start(self) -> None:
        """Start the UI system."""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the UI system and cleanup."""
        pass
    
    @abstractmethod
    async def render_message(self, message: str, message_type: str = "info",
                           metadata: Dict[str, Any] = None) -> None:
        """
        Render a message to the user.
        
        Args:
            message: Message content
            message_type: Type of message ("info", "error", "success", "warning")
            metadata: Additional metadata for rendering
        """
        pass
    
    @abstractmethod
    async def render_progress(self, task_name: str, progress: float = None,
                            status: str = None, details: Dict[str, Any] = None) -> None:
        """
        Render progress for a running task.
        
        Args:
            task_name: Name of the task
            progress: Progress percentage (0.0-1.0) or None for indeterminate
            status: Current status text
            details: Additional progress details
        """
        pass
    
    @abstractmethod
    async def render_brain_status(self, brain_name: str, status: Dict[str, Any]) -> None:
        """
        Render the status of a specific brain.
        
        Args:
            brain_name: Name of the brain
            status: Status dictionary with brain information
        """
        pass
    
    @abstractmethod
    async def render_workspace_overview(self, workspaces: Dict[str, Any]) -> None:
        """
        Render overview of all workspaces.
        
        Args:
            workspaces: Dictionary of workspace information
        """
        pass
    
    @abstractmethod
    async def render_event_stream(self, events: List[Dict[str, Any]]) -> None:
        """
        Render recent events from the system.
        
        Args:
            events: List of recent events
        """
        pass
    
    @abstractmethod
    async def get_user_input(self, prompt: str = None) -> str:
        """
        Get input from the user.
        
        Args:
            prompt: Optional prompt to display
            
        Returns:
            User input string
        """
        pass
    
    @abstractmethod
    async def show_help(self) -> None:
        """Display help information."""
        pass
    
    @abstractmethod
    async def show_error(self, error: str, details: str = None) -> None:
        """
        Display an error message.
        
        Args:
            error: Error message
            details: Optional detailed error information
        """
        pass
    
    @abstractmethod
    async def update_status_bar(self, status: Dict[str, Any]) -> None:
        """
        Update the status bar with current system information.
        
        Args:
            status: System status information
        """
        pass
    
    @abstractmethod
    def is_running(self) -> bool:
        """Check if the UI is currently running."""
        pass
    
    # Optional methods for advanced UI features
    
    async def render_code_output(self, code: str, output: Dict[str, Any]) -> None:
        """
        Render code execution results (optional).
        
        Args:
            code: Code that was executed
            output: Execution output and results
        """
        pass
    
    async def render_research_results(self, query: str, results: Dict[str, Any]) -> None:
        """
        Render research results (optional).
        
        Args:
            query: Research query
            results: Research findings
        """
        pass
    
    async def set_focus_mode(self, mode: str, workspace: str = None) -> None:
        """
        Update UI to reflect focus mode change (optional).
        
        Args:
            mode: Focus mode name
            workspace: Active workspace
        """
        pass