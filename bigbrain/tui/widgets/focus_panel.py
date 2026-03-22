"""Focus Panel - Current focus mode and workspace status."""

from datetime import datetime, timedelta

from textual.widgets import Static
from textual.containers import Vertical
from rich.text import Text


class FocusPanel(Vertical):
    """
    Focus panel widget showing attention management status.
    
    Features:
    - Current focus mode display with emoji
    - Active workspace information
    - Idle time tracking
    - Workspace state indicators
    - Focus mode switching controls
    - Attention statistics
    """
    
    def __init__(self, **kwargs):
        """Initialize focus panel."""
        self.current_mode = "normal"
        self.active_workspace = "demo"
        self.last_activity = datetime.now()
        self.focus_start_time = datetime.now()
        
        # Workspace states
        self.workspaces = {
            "demo": {"state": "active", "since": datetime.now(), "events": 12},
            "research": {"state": "peripheral", "since": datetime.now() - timedelta(minutes=15), "events": 3},
            "coding": {"state": "background", "since": datetime.now() - timedelta(hours=1), "events": 0}
        }
        
        super().__init__(**kwargs)
    
    def compose(self):
        """Compose the focus panel."""
        yield Static("", id="focus_mode_display")
        yield Static("", id="workspace_display") 
        yield Static("", id="timing_display")
        yield Static("", id="workspace_list")
        yield Static("", id="focus_stats")
        
        # Initial update
        self.call_after_refresh(self.update_all_displays)
    
    def update_focus(self, mode: str, workspace: str = None, idle_minutes: float = None) -> None:
        """
        Update focus information.
        
        Args:
            mode: Focus mode (normal, deep_focus, overview)
            workspace: Active workspace name
            idle_minutes: Minutes since last activity
        """
        # Update mode if changed
        if mode != self.current_mode:
            self.current_mode = mode
            self.focus_start_time = datetime.now()
        
        # Update workspace if provided
        if workspace:
            self.active_workspace = workspace
            if workspace not in self.workspaces:
                self.workspaces[workspace] = {
                    "state": "active",
                    "since": datetime.now(),
                    "events": 0
                }
            else:
                self.workspaces[workspace]["state"] = "active"
                self.workspaces[workspace]["since"] = datetime.now()
        
        # Update activity time
        if idle_minutes is not None:
            self.last_activity = datetime.now() - timedelta(minutes=idle_minutes)
        else:
            self.last_activity = datetime.now()
        
        self.update_all_displays()
    
    def update_all_displays(self) -> None:
        """Update all display elements."""
        self.update_focus_mode_display()
        self.update_workspace_display()
        self.update_timing_display()
        self.update_workspace_list()
        self.update_focus_stats()
    
    def update_focus_mode_display(self) -> None:
        """Update the focus mode display."""
        try:
            mode_widget = self.query_one("#focus_mode_display")
        except Exception:
            return  # Widget not ready yet
        
        # Mode emoji and styling
        mode_info = {
            "deep_focus": {"emoji": "🔴", "name": "Deep Focus", "style": "bold red"},
            "normal": {"emoji": "🟢", "name": "Normal", "style": "bold green"},
            "overview": {"emoji": "🔵", "name": "Overview", "style": "bold blue"}
        }
        
        info = mode_info.get(self.current_mode, mode_info["normal"])
        
        # Build display
        text = Text()
        text.append(f"Mode: {info['emoji']} ", style=info['style'])
        text.append(info['name'], style=info['style'])
        
        # Show how long in this mode
        time_in_mode = datetime.now() - self.focus_start_time
        if time_in_mode.total_seconds() < 60:
            time_str = f"{int(time_in_mode.total_seconds())}s"
        elif time_in_mode.total_seconds() < 3600:
            time_str = f"{int(time_in_mode.total_seconds() / 60)}m"
        else:
            hours = int(time_in_mode.total_seconds() / 3600)
            minutes = int((time_in_mode.total_seconds() % 3600) / 60)
            time_str = f"{hours}h {minutes}m"
        
        text.append(f"\n({time_str})", style="dim")
        
        mode_widget.update(text)
    
    def update_workspace_display(self) -> None:
        """Update the workspace display."""
        try:
            workspace_widget = self.query_one("#workspace_display")
        except Exception:
            return
        
        text = Text()
        text.append("Active: ", style="bold")
        text.append(f"📂 {self.active_workspace}", style="cyan")
        
        # Show workspace state
        if self.active_workspace in self.workspaces:
            ws_info = self.workspaces[self.active_workspace]
            state_emoji = {
                "active": "🎯",
                "peripheral": "👁️",
                "background": "💤"
            }.get(ws_info["state"], "❓")
            
            text.append(f"\nState: {state_emoji} {ws_info['state']}", style="white")
        
        workspace_widget.update(text)
    
    def update_timing_display(self) -> None:
        """Update timing information."""
        try:
            timing_widget = self.query_one("#timing_display")
        except Exception:
            return
        
        # Calculate idle time
        idle_time = datetime.now() - self.last_activity
        if idle_time.total_seconds() < 60:
            idle_str = f"{int(idle_time.total_seconds())}s"
        else:
            idle_str = f"{int(idle_time.total_seconds() / 60)}m"
        
        text = Text()
        text.append("Idle: ", style="bold")
        
        # Color based on idle time
        if idle_time.total_seconds() < 300:  # < 5 minutes
            text.append(f"⚡ {idle_str}", style="green")
        elif idle_time.total_seconds() < 1800:  # < 30 minutes
            text.append(f"⏰ {idle_str}", style="yellow")
        else:  # > 30 minutes
            text.append(f"💤 {idle_str}", style="red")
        
        timing_widget.update(text)
    
    def update_workspace_list(self) -> None:
        """Update the workspace list display."""
        try:
            ws_list_widget = self.query_one("#workspace_list")
        except Exception:
            return
        
        if not self.workspaces:
            ws_list_widget.update("")
            return
        
        text = Text()
        text.append("─" * 15 + "\n", style="dim")
        text.append("Workspaces:\n", style="bold")
        
        for ws_name, ws_info in self.workspaces.items():
            # State indicator
            state_indicators = {
                "active": "🎯",
                "peripheral": "👁️",
                "background": "💤"
            }
            indicator = state_indicators.get(ws_info["state"], "❓")
            
            # Name and state
            text.append(f"  {indicator} {ws_name}", style="white")
            
            # Event count
            if ws_info.get("events", 0) > 0:
                text.append(f" ({ws_info['events']})", style="dim")
            
            text.append("\n")
        
        ws_list_widget.update(text)
    
    def update_focus_stats(self) -> None:
        """Update focus statistics."""
        try:
            stats_widget = self.query_one("#focus_stats")
        except Exception:
            return
        
        # Calculate stats
        total_workspaces = len(self.workspaces)
        active_workspaces = sum(1 for ws in self.workspaces.values() if ws["state"] == "active")
        total_events = sum(ws.get("events", 0) for ws in self.workspaces.values())
        
        text = Text()
        text.append("─" * 15 + "\n", style="dim")
        text.append(f"Workspaces: {active_workspaces}/{total_workspaces}", style="cyan")
        text.append(f"\nEvents: {total_events}", style="yellow")
        
        # Focus efficiency (mock calculation)
        if total_events > 0:
            efficiency = min(100, (active_workspaces / total_workspaces) * 100)
            text.append(f"\nEfficiency: {efficiency:.0f}%", style="green" if efficiency > 70 else "yellow")
        
        stats_widget.update(text)
    
    def add_workspace(self, name: str, state: str = "background") -> None:
        """
        Add a new workspace.
        
        Args:
            name: Workspace name
            state: Initial state (active, peripheral, background)
        """
        self.workspaces[name] = {
            "state": state,
            "since": datetime.now(),
            "events": 0
        }
        self.update_all_displays()
    
    def update_workspace_state(self, name: str, state: str) -> None:
        """
        Update workspace state.
        
        Args:
            name: Workspace name
            state: New state
        """
        if name in self.workspaces:
            self.workspaces[name]["state"] = state
            self.workspaces[name]["since"] = datetime.now()
            self.update_all_displays()
    
    def increment_workspace_events(self, name: str, count: int = 1) -> None:
        """
        Increment event count for a workspace.
        
        Args:
            name: Workspace name
            count: Number of events to add
        """
        if name in self.workspaces:
            self.workspaces[name]["events"] = self.workspaces[name].get("events", 0) + count
            self.update_all_displays()
    
    def get_focus_status(self) -> dict:
        """
        Get current focus status.
        
        Returns:
            Focus status dictionary
        """
        idle_seconds = (datetime.now() - self.last_activity).total_seconds()
        mode_seconds = (datetime.now() - self.focus_start_time).total_seconds()
        
        return {
            "mode": self.current_mode,
            "active_workspace": self.active_workspace,
            "idle_seconds": idle_seconds,
            "mode_duration_seconds": mode_seconds,
            "workspaces": {
                name: {
                    "state": info["state"],
                    "since": info["since"].isoformat(),
                    "events": info.get("events", 0)
                }
                for name, info in self.workspaces.items()
            },
            "total_workspaces": len(self.workspaces),
            "active_workspaces": sum(1 for ws in self.workspaces.values() if ws["state"] == "active")
        }
    
    def simulate_focus_changes(self) -> None:
        """Simulate focus changes for demo purposes."""
        import asyncio
        
        async def focus_simulation():
            # Simulate normal workflow
            await asyncio.sleep(3)
            self.increment_workspace_events("demo", 2)
            
            await asyncio.sleep(2)
            self.update_focus("normal", "demo", 0.1)
            
            await asyncio.sleep(4)
            self.add_workspace("analysis", "peripheral")
            
            await asyncio.sleep(3)
            self.increment_workspace_events("analysis", 1)
        
        asyncio.create_task(focus_simulation())