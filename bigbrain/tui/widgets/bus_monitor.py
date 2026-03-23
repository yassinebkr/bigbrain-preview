"""Bus Monitor - Real-time message flow display."""

import time
from datetime import datetime
from typing import Dict, List

from textual.widgets import Static
from textual.containers import Vertical, VerticalScroll
from rich.text import Text


class BusMessage(Static):
    """Individual bus message display."""
    
    def __init__(self, msg_type: str, route: str, payload: str, timestamp: datetime = None, **kwargs):
        """
        Initialize bus message.
        
        Args:
            msg_type: Message type (TASK, RESULT, EVENT, etc.)
            route: Source → Target route
            payload: Message payload (truncated)
            timestamp: Message timestamp
        """
        self.msg_type = msg_type
        self.route = route
        self.payload = payload
        self.timestamp = timestamp or datetime.now()
        
        super().__init__(**kwargs)
        self._update_display()
    
    def _update_display(self) -> None:
        """Update the message display."""
        # Format timestamp
        time_str = self.timestamp.strftime("%H:%M:%S")
        
        # Type-specific styling
        type_colors = {
            "TASK": "blue",
            "RESULT": "green", 
            "EVENT": "yellow",
            "ERROR": "red",
            "PROGRESS": "cyan",
            "QUERY": "magenta",
            "CANCEL": "red",
            "STATE": "white"
        }
        
        type_color = type_colors.get(self.msg_type, "white")
        
        # Build display text
        text = Text()
        text.append(f"[{time_str}] ", style="dim")
        text.append(f"{self.msg_type}", style=f"bold {type_color}")
        text.append(f" {self.route}", style="white")
        
        if self.payload:
            # Truncate long payloads
            display_payload = self.payload
            if len(display_payload) > 50:
                display_payload = display_payload[:47] + "..."
            text.append(f"\n    └ {display_payload}", style="dim")
        
        self.update(text)


class BusMonitor(VerticalScroll):
    """
    Bus monitor widget showing real-time message flow.
    
    Features:
    - Color-coded message types
    - Source → Target routing display
    - Payload preview with truncation
    - Automatic scrolling to latest
    - Message filtering capabilities
    - Activity statistics
    """
    
    BORDER_TITLE = "📡 Bus Monitor"
    
    def __init__(self, max_messages: int = 100, **kwargs):
        """
        Initialize bus monitor.
        
        Args:
            max_messages: Maximum messages to keep in history
        """
        self.max_messages = max_messages
        self.messages = []
        self.message_counts = {
            "TASK": 0,
            "RESULT": 0, 
            "EVENT": 0,
            "ERROR": 0,
            "PROGRESS": 0,
            "QUERY": 0,
            "CANCEL": 0,
            "STATE": 0
        }
        self.start_time = datetime.now()
        
        super().__init__(**kwargs)
    
    def compose(self):
        """Compose the bus monitor."""
        with Vertical(id="bus-messages"):
            yield Static(
                "🚌 Monitoring message bus...\nWaiting for activity...",
                id="welcome-message",
                classes="dim"
            )
            yield Static("", id="bus-stats")
    
    def add_message(self, msg_type: str, route: str, payload: str = "") -> None:
        """
        Add a new bus message.
        
        Args:
            msg_type: Message type
            route: Source → Target route
            payload: Message payload
        """
        # Remove welcome message on first real message
        if not self.messages:
            try:
                welcome_msg = self.query_one("#welcome-message")
                welcome_msg.remove()
            except Exception:
                pass
        
        # Create message widget
        message = BusMessage(msg_type, route, payload)
        self.messages.append(message)
        
        # Update statistics
        self.message_counts[msg_type] = self.message_counts.get(msg_type, 0) + 1
        
        # Add to UI
        bus_container = self.query_one("#bus-messages")
        bus_container.mount(message)
        
        # Trim old messages if over limit
        if len(self.messages) > self.max_messages:
            old_message = self.messages.pop(0)
            old_message.remove()
        
        # Auto-scroll to bottom
        self.scroll_end(animate=True)
        
        # Update statistics
        self.update_stats()
    
    def add_task_message(self, source: str, target: str, task_description: str) -> None:
        """Add a TASK message."""
        route = f"{source} → {target}"
        self.add_message("TASK", route, task_description)
    
    def add_result_message(self, source: str, target: str, result: str) -> None:
        """Add a RESULT message."""
        route = f"{source} → {target}"
        self.add_message("RESULT", route, result)
    
    def add_event_message(self, source: str, event_type: str, details: str = "") -> None:
        """Add an EVENT message."""
        route = f"{source} → *"
        payload = f"{event_type}: {details}" if details else event_type
        self.add_message("EVENT", route, payload)
    
    def add_progress_message(self, source: str, target: str, progress: str) -> None:
        """Add a PROGRESS message."""
        route = f"{source} → {target}"
        self.add_message("PROGRESS", route, progress)
    
    def add_error_message(self, source: str, error: str) -> None:
        """Add an ERROR message."""
        route = f"{source} → system"
        self.add_message("ERROR", route, error)
    
    def update_stats(self) -> None:
        """Update the statistics display."""
        try:
            stats_widget = self.query_one("#bus-stats")
        except Exception:
            return  # Widget not ready yet
        
        total_messages = sum(self.message_counts.values())
        if total_messages == 0:
            stats_widget.update("")
            return
        
        # Calculate activity rate
        elapsed = (datetime.now() - self.start_time).total_seconds()
        rate = total_messages / max(elapsed, 1)  # messages per second
        
        # Build stats display
        text = Text()
        text.append("─" * 25 + "\n", style="dim")
        
        # Message type breakdown
        for msg_type, count in self.message_counts.items():
            if count > 0:
                percentage = (count / total_messages) * 100
                color = {
                    "TASK": "blue",
                    "RESULT": "green",
                    "EVENT": "yellow", 
                    "ERROR": "red",
                    "PROGRESS": "cyan"
                }.get(msg_type, "white")
                
                text.append(f"{msg_type}: {count} ({percentage:.1f}%) ", style=color)
        
        text.append(f"\nTotal: {total_messages} | Rate: {rate:.2f}/s", style="dim")
        
        stats_widget.update(text)
    
    def filter_messages(self, msg_type: str = None, source: str = None, target: str = None) -> List[Dict]:
        """
        Filter messages by criteria.
        
        Args:
            msg_type: Filter by message type
            source: Filter by source
            target: Filter by target
            
        Returns:
            List of matching message dictionaries
        """
        filtered = []
        
        for message in self.messages:
            # Check type filter
            if msg_type and message.msg_type != msg_type:
                continue
            
            # Check source/target filters
            route_parts = message.route.split(" → ")
            if len(route_parts) == 2:
                msg_source, msg_target = route_parts
                if source and source not in msg_source:
                    continue
                if target and target not in msg_target:
                    continue
            
            filtered.append({
                "type": message.msg_type,
                "route": message.route,
                "payload": message.payload,
                "timestamp": message.timestamp.isoformat()
            })
        
        return filtered
    
    def clear(self) -> None:
        """Clear all messages."""
        # Remove all message widgets
        bus_container = self.query_one("#bus-messages")
        for message in self.messages:
            if message.parent:
                message.remove()
        
        # Reset tracking
        self.messages.clear()
        self.message_counts = {key: 0 for key in self.message_counts}
        self.start_time = datetime.now()
        
        # Add welcome message back
        welcome_msg = Static(
            "🚌 Bus monitor cleared\nWaiting for new activity...",
            id="welcome-message",
            classes="dim"
        )
        bus_container.mount(welcome_msg)
        
        # Update stats
        self.update_stats()
    
    def get_message_count(self, msg_type: str = None) -> int:
        """
        Get message count.
        
        Args:
            msg_type: Specific type to count (all if None)
            
        Returns:
            Message count
        """
        if msg_type:
            return self.message_counts.get(msg_type, 0)
        return sum(self.message_counts.values())
    
    def get_activity_rate(self) -> float:
        """
        Get current activity rate.
        
        Returns:
            Messages per second
        """
        elapsed = (datetime.now() - self.start_time).total_seconds()
        total_messages = sum(self.message_counts.values())
        return total_messages / max(elapsed, 1)
    
    def export_messages(self, limit: int = None) -> List[Dict]:
        """
        Export message history.
        
        Args:
            limit: Maximum number of messages to export
            
        Returns:
            List of message dictionaries
        """
        messages_to_export = self.messages
        if limit:
            messages_to_export = self.messages[-limit:]
        
        return [
            {
                "type": msg.msg_type,
                "route": msg.route,
                "payload": msg.payload,
                "timestamp": msg.timestamp.isoformat()
            }
            for msg in messages_to_export
        ]
    
    def simulate_bus_activity(self) -> None:
        """Simulate bus activity for demo purposes."""
        import asyncio
        
        async def activity_simulation():
            # Simulate a typical workflow
            self.add_task_message("user_interface", "front_brain", "Analyze user request")
            await asyncio.sleep(0.5)
            
            self.add_progress_message("front_brain", "user_interface", "Processing intent...")
            await asyncio.sleep(0.3)
            
            self.add_event_message("front_brain", "intent.analyzed", "coding_task")
            await asyncio.sleep(0.2)
            
            self.add_task_message("front_brain", "orchestrator", "Plan coding task")
            await asyncio.sleep(0.4)
            
            self.add_task_message("orchestrator", "python_brain", "Generate code solution")
            await asyncio.sleep(1.0)
            
            self.add_progress_message("python_brain", "orchestrator", "Writing code...")
            await asyncio.sleep(0.8)
            
            self.add_result_message("python_brain", "orchestrator", "Code generated successfully")
            await asyncio.sleep(0.3)
            
            self.add_result_message("orchestrator", "front_brain", "Task completed")
            await asyncio.sleep(0.2)
            
            self.add_event_message("front_brain", "task.complete", "200 lines of code")
        
        asyncio.create_task(activity_simulation())