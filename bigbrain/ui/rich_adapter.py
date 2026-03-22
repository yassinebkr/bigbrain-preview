"""RichAdapter - Rich library terminal interface for BigBrain."""

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich.prompt import Prompt
    from rich.syntax import Syntax
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from .ui_adapter import UIAdapter


class RichAdapter(UIAdapter):
    """
    Rich library terminal interface for BigBrain.
    
    Provides a modern terminal UI with:
    - Color-coded messages and status
    - Progress bars for long-running tasks
    - Live updating dashboard
    - Syntax highlighting for code
    - Interactive input prompts
    - Workspace and brain status overview
    
    Falls back to simple text output if Rich is not available.
    """
    
    def __init__(self):
        """Initialize Rich adapter."""
        if not RICH_AVAILABLE:
            print("Warning: Rich library not available. Using simple text output.")
        
        self.console = Console() if RICH_AVAILABLE else None
        self._running = False
        self._live_display = None
        self._layout = None
        
        # State tracking
        self._messages: List[Dict[str, Any]] = []
        self._progress_tasks: Dict[str, Any] = {}
        self._brain_statuses: Dict[str, Dict[str, Any]] = {}
        self._workspace_info: Dict[str, Any] = {}
        self._recent_events: List[Dict[str, Any]] = []
        self._system_status = {"mode": "Normal", "workspace": "default", "time": datetime.now()}
        
        # Configuration
        self._max_messages = 50
        self._max_events = 20
    
    async def start(self) -> None:
        """Start the Rich UI system."""
        if self._running:
            return
        
        self._running = True
        
        if RICH_AVAILABLE:
            self._setup_layout()
            self._live_display = Live(self._layout, console=self.console, refresh_per_second=2)
            self._live_display.start()
        
        await self.render_message("🧠 BigBrain UI Started", "success")
        await self.show_help()
    
    async def stop(self) -> None:
        """Stop the UI system."""
        if not self._running:
            return
        
        self._running = False
        
        if self._live_display:
            self._live_display.stop()
        
        if RICH_AVAILABLE:
            self.console.print("\n[bold green]BigBrain UI stopped. Goodbye![/bold green]")
        else:
            print("\nBigBrain UI stopped. Goodbye!")
    
    async def render_message(self, message: str, message_type: str = "info",
                           metadata: Dict[str, Any] = None) -> None:
        """Render a message to the user."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        message_data = {
            "timestamp": timestamp,
            "message": message,
            "type": message_type,
            "metadata": metadata or {}
        }
        
        self._messages.append(message_data)
        
        # Keep only recent messages
        if len(self._messages) > self._max_messages:
            self._messages = self._messages[-self._max_messages:]
        
        if RICH_AVAILABLE and self._live_display:
            self._update_messages_panel()
        else:
            # Fallback to simple print
            type_prefix = {
                "info": "ℹ️",
                "success": "✅",
                "error": "❌",
                "warning": "⚠️"
            }.get(message_type, "📝")
            print(f"[{timestamp}] {type_prefix} {message}")
    
    async def render_progress(self, task_name: str, progress: float = None,
                            status: str = None, details: Dict[str, Any] = None) -> None:
        """Render progress for a running task."""
        if task_name in self._progress_tasks:
            # Update existing task
            task_data = self._progress_tasks[task_name]
            task_data.update({
                "progress": progress,
                "status": status or task_data.get("status", "Running"),
                "last_update": time.time(),
                "details": details or {}
            })
        else:
            # New task
            self._progress_tasks[task_name] = {
                "name": task_name,
                "progress": progress,
                "status": status or "Starting",
                "start_time": time.time(),
                "last_update": time.time(),
                "details": details or {}
            }
        
        if RICH_AVAILABLE and self._live_display:
            self._update_progress_panel()
        else:
            # Fallback
            if progress is not None:
                progress_bar = "█" * int(progress * 20) + "░" * (20 - int(progress * 20))
                print(f"Progress [{progress_bar}] {task_name}: {status or 'Running'}")
            else:
                print(f"⏳ {task_name}: {status or 'Running'}")
    
    async def render_brain_status(self, brain_name: str, status: Dict[str, Any]) -> None:
        """Render the status of a specific brain."""
        self._brain_statuses[brain_name] = {
            **status,
            "last_update": time.time()
        }
        
        if RICH_AVAILABLE and self._live_display:
            self._update_brains_panel()
        else:
            # Fallback
            running = status.get("running", False)
            busy = status.get("busy", False)
            status_icon = "🟢" if running else "🔴"
            busy_text = " (busy)" if busy else ""
            print(f"{status_icon} {brain_name}: {'running' if running else 'stopped'}{busy_text}")
    
    async def render_workspace_overview(self, workspaces: Dict[str, Any]) -> None:
        """Render overview of all workspaces."""
        self._workspace_info = workspaces
        
        if RICH_AVAILABLE and self._live_display:
            self._update_workspace_panel()
        else:
            # Fallback
            print("📁 Workspaces:")
            for ws_name, ws_data in workspaces.items():
                state = ws_data.get("state", "unknown")
                print(f"  - {ws_name}: {state}")
    
    async def render_event_stream(self, events: List[Dict[str, Any]]) -> None:
        """Render recent events from the system."""
        # Add new events and keep only recent ones
        current_time = time.time()
        for event in events:
            event["ui_timestamp"] = current_time
            self._recent_events.append(event)
        
        # Sort by timestamp and keep recent
        self._recent_events.sort(key=lambda e: e.get("timestamp", 0), reverse=True)
        self._recent_events = self._recent_events[:self._max_events]
        
        if RICH_AVAILABLE and self._live_display:
            self._update_events_panel()
        else:
            # Fallback
            if events:
                print("🔔 Recent events:")
                for event in events[-5:]:  # Show last 5
                    event_type = event.get("event", "unknown")
                    source = event.get("source", "system")
                    print(f"  - {source}: {event_type}")
    
    async def get_user_input(self, prompt: str = None) -> str:
        """Get input from the user."""
        if RICH_AVAILABLE:
            if self._live_display:
                self._live_display.stop()
            
            try:
                result = Prompt.ask(prompt or "BigBrain", console=self.console)
            finally:
                if self._live_display and self._running:
                    self._live_display.start()
            
            return result
        else:
            # Fallback
            return input(f"{prompt or 'BigBrain'}: ")
    
    async def show_help(self) -> None:
        """Display help information."""
        help_text = """
🧠 BigBrain - Multi-Brain AI Agent System

Commands:
• Type your task naturally (e.g., "run this code", "research quantum computing")
• Focus commands: "deep focus", "normal focus", "overview mode"
• Status: "status", "what's happening?", "show workspaces"
• Help: "help"
• Quit: "quit", "exit"

Focus Modes:
• Deep Focus: Only critical interruptions
• Normal: Important events and completions  
• Overview: All workspace activity

The system will automatically route your tasks to the appropriate brains
and keep you informed based on your current focus mode.
"""
        await self.render_message(help_text.strip(), "info")
    
    async def show_error(self, error: str, details: str = None) -> None:
        """Display an error message."""
        error_msg = f"Error: {error}"
        if details:
            error_msg += f"\nDetails: {details}"
        
        await self.render_message(error_msg, "error")
    
    async def update_status_bar(self, status: Dict[str, Any]) -> None:
        """Update the status bar with current system information."""
        self._system_status.update(status)
        self._system_status["time"] = datetime.now()
        
        if RICH_AVAILABLE and self._live_display:
            self._update_status_panel()
        else:
            # Fallback - just update in memory for now
            pass
    
    def is_running(self) -> bool:
        """Check if the UI is currently running."""
        return self._running
    
    async def render_code_output(self, code: str, output: Dict[str, Any]) -> None:
        """Render code execution results."""
        success = output.get("success", False)
        stdout = output.get("stdout", "")
        stderr = output.get("stderr", "")
        
        if RICH_AVAILABLE:
            # Create a panel with syntax highlighted code
            code_panel = Panel(
                Syntax(code, "python", theme="monokai"),
                title="Executed Code",
                border_style="blue"
            )
            self.console.print(code_panel)
            
            # Show output
            if stdout:
                output_panel = Panel(
                    stdout,
                    title="Output",
                    border_style="green" if success else "red"
                )
                self.console.print(output_panel)
            
            if stderr:
                error_panel = Panel(
                    stderr,
                    title="Errors",
                    border_style="red"
                )
                self.console.print(error_panel)
        else:
            # Fallback
            print(f"\n--- Code ---\n{code}\n")
            if stdout:
                print(f"--- Output ---\n{stdout}\n")
            if stderr:
                print(f"--- Errors ---\n{stderr}\n")
    
    async def render_research_results(self, query: str, results: Dict[str, Any]) -> None:
        """Render research results."""
        summary = results.get("summary", "")
        sources = results.get("sources", [])
        confidence = results.get("confidence", 0.0)
        
        if RICH_AVAILABLE:
            # Research summary panel
            summary_panel = Panel(
                summary,
                title=f"Research: {query}",
                subtitle=f"Confidence: {confidence:.1%}",
                border_style="cyan"
            )
            self.console.print(summary_panel)
            
            # Sources table
            if sources:
                table = Table(title="Sources", box=box.ROUNDED)
                table.add_column("Title", style="cyan")
                table.add_column("URL", style="blue")
                
                for source in sources[:5]:  # Show top 5 sources
                    title = source.get("title", "Unknown")
                    url = source.get("url", "")
                    table.add_row(title[:50] + "..." if len(title) > 50 else title, url)
                
                self.console.print(table)
        else:
            # Fallback
            print(f"\n--- Research: {query} ---")
            print(f"Confidence: {confidence:.1%}")
            print(f"\nSummary:\n{summary}\n")
            if sources:
                print("Sources:")
                for i, source in enumerate(sources[:3], 1):
                    print(f"{i}. {source.get('title', 'Unknown')}")
    
    async def set_focus_mode(self, mode: str, workspace: str = None) -> None:
        """Update UI to reflect focus mode change."""
        self._system_status["mode"] = mode.replace("_", " ").title()
        if workspace:
            self._system_status["workspace"] = workspace
        
        await self.render_message(f"Focus mode changed to: {mode}", "info")
    
    def _setup_layout(self) -> None:
        """Setup the Rich layout."""
        if not RICH_AVAILABLE:
            return
        
        self._layout = Layout()
        
        # Split into header, body, and footer
        self._layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=5)
        )
        
        # Split body into left and right
        self._layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )
        
        # Split left into messages and progress
        self._layout["left"].split(
            Layout(name="messages", ratio=2),
            Layout(name="progress", size=8)
        )
        
        # Split right into status panels
        self._layout["right"].split(
            Layout(name="workspace", size=8),
            Layout(name="brains", size=8),
            Layout(name="events")
        )
        
        # Initialize panels
        self._update_all_panels()
    
    def _update_all_panels(self) -> None:
        """Update all display panels."""
        if not RICH_AVAILABLE or not self._layout:
            return
        
        self._update_status_panel()
        self._update_messages_panel()
        self._update_progress_panel()
        self._update_workspace_panel()
        self._update_brains_panel()
        self._update_events_panel()
        self._update_footer_panel()
    
    def _update_status_panel(self) -> None:
        """Update the status header panel."""
        if not RICH_AVAILABLE or not self._layout:
            return
        
        mode = self._system_status.get("mode", "Unknown")
        workspace = self._system_status.get("workspace", "default")
        current_time = self._system_status.get("time", datetime.now())
        
        status_text = Text(f"🧠 BigBrain - Mode: {mode} | Workspace: {workspace} | {current_time.strftime('%H:%M:%S')}")
        status_text.stylize("bold blue")
        
        self._layout["header"].update(Panel(status_text, box=box.ROUNDED))
    
    def _update_messages_panel(self) -> None:
        """Update the messages panel."""
        if not RICH_AVAILABLE or not self._layout:
            return
        
        if not self._messages:
            content = Text("No messages yet...", style="dim")
        else:
            content = Text()
            for msg in self._messages[-10:]:  # Show last 10 messages
                timestamp = msg["timestamp"]
                message_type = msg["type"]
                message = msg["message"]
                
                style = {
                    "info": "white",
                    "success": "green",
                    "error": "red",
                    "warning": "yellow"
                }.get(message_type, "white")
                
                content.append(f"[{timestamp}] ", style="dim")
                content.append(message[:80] + "..." if len(message) > 80 else message, style=style)
                content.append("\n")
        
        self._layout["messages"].update(Panel(content, title="Messages", box=box.ROUNDED))
    
    def _update_progress_panel(self) -> None:
        """Update the progress panel."""
        if not RICH_AVAILABLE or not self._layout:
            return
        
        if not self._progress_tasks:
            content = Text("No active tasks", style="dim")
        else:
            content = Text()
            for task_name, task_data in list(self._progress_tasks.items()):
                # Remove completed tasks after 5 seconds
                if (task_data.get("progress") == 1.0 and 
                    time.time() - task_data.get("last_update", 0) > 5):
                    del self._progress_tasks[task_name]
                    continue
                
                progress = task_data.get("progress")
                status = task_data.get("status", "Running")
                
                if progress is not None:
                    bar = "█" * int(progress * 20) + "░" * (20 - int(progress * 20))
                    content.append(f"{task_name[:20]:<20} [{bar}] {progress:.1%}\n")
                else:
                    content.append(f"{task_name[:20]:<20} [⏳] {status}\n")
        
        self._layout["progress"].update(Panel(content, title="Progress", box=box.ROUNDED))
    
    def _update_workspace_panel(self) -> None:
        """Update the workspace panel."""
        if not RICH_AVAILABLE or not self._layout:
            return
        
        if not self._workspace_info:
            content = Text("No workspace info", style="dim")
        else:
            table = Table(box=None)
            table.add_column("Workspace")
            table.add_column("State")
            
            for ws_name, ws_data in self._workspace_info.items():
                state = ws_data.get("state", "unknown")
                style = {
                    "active": "green",
                    "peripheral": "yellow",
                    "background": "dim"
                }.get(state, "white")
                
                table.add_row(ws_name, state, style=style)
            
            content = table
        
        self._layout["workspace"].update(Panel(content, title="Workspaces", box=box.ROUNDED))
    
    def _update_brains_panel(self) -> None:
        """Update the brains status panel."""
        if not RICH_AVAILABLE or not self._layout:
            return
        
        if not self._brain_statuses:
            content = Text("No brain info", style="dim")
        else:
            table = Table(box=None)
            table.add_column("Brain")
            table.add_column("Status")
            
            for brain_name, brain_data in self._brain_statuses.items():
                running = brain_data.get("running", False)
                busy = brain_data.get("busy", False)
                
                status_text = "🟢 Running" if running else "🔴 Stopped"
                if running and busy:
                    status_text += " (busy)"
                
                table.add_row(brain_name, status_text)
            
            content = table
        
        self._layout["brains"].update(Panel(content, title="Brains", box=box.ROUNDED))
    
    def _update_events_panel(self) -> None:
        """Update the events panel."""
        if not RICH_AVAILABLE or not self._layout:
            return
        
        if not self._recent_events:
            content = Text("No recent events", style="dim")
        else:
            content = Text()
            for event in self._recent_events[-8:]:  # Show last 8 events
                source = event.get("source", "unknown")
                event_type = event.get("event", event.get("type", "unknown"))
                
                content.append(f"• {source}: {event_type}\n", style="cyan")
        
        self._layout["events"].update(Panel(content, title="Events", box=box.ROUNDED))
    
    def _update_footer_panel(self) -> None:
        """Update the footer panel."""
        if not RICH_AVAILABLE or not self._layout:
            return
        
        help_text = Text("Type your commands below. Use 'help' for assistance, 'quit' to exit.")
        help_text.stylize("dim")
        
        self._layout["footer"].update(Panel(help_text, box=box.ROUNDED))