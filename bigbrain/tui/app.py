"""Main BigBrain Textual TUI Application."""

import asyncio
from typing import Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, Input
from textual.binding import Binding

from .widgets.brain_panel import BrainPanel
from .widgets.bus_monitor import BusMonitor
from .widgets.chat_panel import ChatPanel
from .widgets.focus_panel import FocusPanel
from .widgets.task_panel import TaskPanel


class BigBrainApp(App):
    """
    Main BigBrain Textual application.
    
    Provides a comprehensive TUI for monitoring and interacting with
    the BigBrain system. Features real-time updates, streaming responses,
    and integration with all BigBrain components.
    """
    
    TITLE = "BigBrain - Multi-Brain AI Agent System"
    CSS_PATH = "app.css"
    
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("ctrl+r", "refresh", "Refresh"),
        Binding("f1", "toggle_focus_mode", "Focus Mode"),
        Binding("f2", "toggle_voice", "Voice"),
        Binding("f3", "show_help", "Help"),
        Binding("ctrl+l", "clear_chat", "Clear Chat"),
        Binding("ctrl+b", "clear_bus", "Clear Bus"),
        Binding("tab", "focus_next", "Next Panel"),
        Binding("shift+tab", "focus_previous", "Previous Panel"),
    ]
    
    def __init__(self, bigbrain_system=None, **kwargs):
        """
        Initialize BigBrain app.
        
        Args:
            bigbrain_system: BigBrain system instance
        """
        super().__init__(**kwargs)
        self.bigbrain_system = bigbrain_system
        self.voice_enabled = False
        self.mic_enabled = False
        self.speaker_enabled = False
        
        # Widget references
        self.chat_panel: Optional[ChatPanel] = None
        self.brain_panel: Optional[BrainPanel] = None
        self.task_panel: Optional[TaskPanel] = None
        self.bus_monitor: Optional[BusMonitor] = None
        self.focus_panel: Optional[FocusPanel] = None
        self.message_input: Optional[Input] = None
    
    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield Header(show_clock=True)
        
        with Container(id="main-container"):
            with Horizontal(id="top-row"):
                with Vertical(id="chat-container", classes="panel"):
                    yield ChatPanel(id="chat-panel")
                    with Horizontal(id="input-container"):
                        yield Input(
                            placeholder="Type your message... 💬",
                            id="message-input"
                        )
                
                with Vertical(id="right-column"):
                    yield BrainPanel(id="brain-panel", classes="panel")
                    yield TaskPanel(id="task-panel", classes="panel")
            
            with Horizontal(id="bottom-row"):
                yield BusMonitor(id="bus-monitor", classes="panel")
                yield FocusPanel(id="focus-panel", classes="panel")
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Handle app mounting."""
        # Get widget references
        self.chat_panel = self.query_one("#chat-panel", ChatPanel)
        self.brain_panel = self.query_one("#brain-panel", BrainPanel)
        self.task_panel = self.query_one("#task-panel", TaskPanel)
        self.bus_monitor = self.query_one("#bus-monitor", BusMonitor)
        self.focus_panel = self.query_one("#focus-panel", FocusPanel)
        self.message_input = self.query_one("#message-input", Input)
        
        # Focus input by default
        self.set_focus(self.message_input)
        
        # Start the BigBrain system inside TUI's event loop
        if self.bigbrain_system:
            self.start_bigbrain_system()
    
    @on(Input.Submitted, "#message-input")
    async def on_message_submitted(self, event: Input.Submitted) -> None:
        """Handle message input submission."""
        message = event.value.strip()
        if not message:
            return
        
        # Clear input
        self.message_input.value = ""
        
        # Add user message to chat
        self.chat_panel.add_message("user", message)
        
        # Process in background worker (doesn't block TUI)
        if self.bigbrain_system:
            self.process_user_message(message)
        else:
            self.chat_panel.add_message("assistant", f"Echo: {message}")
    
    @work(exclusive=True, group="chat")
    async def process_user_message(self, message: str) -> None:
        """Process user message in background worker (non-blocking)."""
        # Show thinking indicator
        self.chat_panel.add_message("system", "⏳ Thinking...")
        
        try:
            if self.bigbrain_system and self.bigbrain_system.front_brain:
                response = await self.bigbrain_system.front_brain.handle_user_input(message)
            else:
                response = "System not ready."
            
            # Remove thinking indicator (last system message)
            if self.chat_panel.messages:
                last = self.chat_panel.messages[-1]
                if hasattr(last, 'message_text') and '⏳' in last.message_text:
                    last.remove()
                    self.chat_panel.messages.pop()
            
            # Show response
            self.chat_panel.add_message("assistant", str(response))
        
        except Exception as e:
            self.chat_panel.add_message("system", f"❌ Error: {e}")
    
    async def simulate_bigbrain_response(self, message: str) -> str:
        """
        Simulate BigBrain response for demo purposes.
        
        Args:
            message: User message
            
        Returns:
            Response text or async iterator
        """
        # This would integrate with the actual BigBrain system
        if "code" in message.lower() or "python" in message.lower():
            return """I'll help you with that coding task. Let me break it down:

```python
def process_data(input_data):
    \"\"\"Process the input data according to your requirements.\"\"\"
    results = []
    
    for item in input_data:
        if validate_item(item):
            processed = transform_item(item)
            results.append(processed)
    
    return results

def validate_item(item):
    \"\"\"Validate individual data item.\"\"\"
    return item is not None and len(str(item)) > 0

def transform_item(item):
    \"\"\"Transform item according to business rules.\"\"\"
    # Add your transformation logic here
    return str(item).strip().lower()
```

This provides a solid foundation for your data processing needs. Would you like me to modify any part of it?"""
        
        elif "status" in message.lower():
            return "All systems are operational! 🟢\n\n• Python Brain: Active and ready\n• Researcher Brain: Standing by\n• Memory System: 3-tier storage online\n• Bus: Message flow normal\n• Focus: Normal mode, demo workspace active"
        
        elif "help" in message.lower():
            return "I'm BigBrain, your multi-brain AI assistant! I can help with:\n\n🔧 **Coding**: Write Python functions, debug code, architectural advice\n📊 **Research**: Investigate topics, analyze data, gather insights\n🧠 **Thinking**: Break down complex problems, strategic planning\n💬 **Chat**: General conversation and questions\n\nJust tell me what you'd like to work on!"
        
        else:
            return f"I understand you're asking about '{message}'. Let me process that and provide you with a thoughtful response. This is a demo of the BigBrain system showing real-time conversation capabilities."
    
    @work(exclusive=True)
    async def start_bigbrain_system(self) -> None:
        """Start BigBrain system inside the TUI event loop."""
        if not self.bigbrain_system:
            return

        system = self.bigbrain_system

        # Give widgets time to fully mount
        await asyncio.sleep(0.3)

        # Start the system (orchestrator, brains, front brain)
        try:
            await system.start()
            self.chat_panel.add_message("system", "✅ BigBrain system ready! Type a message to chat with Claude.")
        except Exception as e:
            self.chat_panel.add_message("system", f"❌ Failed to start: {e}")
            return

        # Wire bus events to TUI panels
        if system.bus:
            system.bus.subscribe("*", self._on_bus_message)

        # Wait for brain panel refs to be set up
        await asyncio.sleep(0.2)

        # Sync brain status — directly update widgets if refs aren't ready
        if self.brain_panel:
            # Force setup refs
            self.brain_panel._setup_brain_refs()
            for brain_name, brain in system.brains.items():
                status = brain.get_status()
                state = "idle" if status.get("running") else "offline"
                self.brain_panel.update_brain_status(brain_name, state, status.get("running", False))
            self.brain_panel.update_brain_status("voice_brain", "disabled", False)

        # Set initial focus
        if self.focus_panel:
            self.focus_panel.update_focus("normal", system.workspace, 0.0)
    
    async def _on_bus_message(self, message) -> None:
        """Handle real bus messages and route to TUI widgets."""
        try:
            msg_type = str(message.type).upper()
            
            source = message.source or "unknown"
            target = message.target or "*"
            route = f"{source} → {target}"
            
            # Build payload preview
            payload_preview = ""
            if message.payload:
                event_type = message.payload.get("event", "")
                task_type = message.payload.get("type", "")
                payload_preview = event_type or task_type or str(message.payload)[:50]
            
            # Feed to bus monitor
            if self.bus_monitor:
                self.bus_monitor.add_message(msg_type, route, payload_preview)
            
            # Update brain panel on brain events
            event_type = message.payload.get("event", "")
            if "brain.started" in event_type:
                brain_name = message.payload.get("brain", message.source)
                if self.brain_panel:
                    self.brain_panel.update_brain_status(brain_name, "idle", True)
            elif "brain.complete" in event_type:
                brain_name = message.payload.get("brain", message.source)
                if self.brain_panel:
                    self.brain_panel.update_brain_status(brain_name, "idle", True)
            elif "brain.error" in event_type:
                brain_name = message.payload.get("brain", message.source)
                if self.brain_panel:
                    self.brain_panel.update_brain_status(brain_name, "error", True)
            
            # Update task panel on task events
            if "task.received" in event_type and self.task_panel:
                task_id = message.payload.get("task_id", "")[:8]
                desc = f"Task in {message.workspace or 'default'}"
                self.task_panel.add_task(desc, task_id)
            elif "task.complete" in event_type and self.task_panel:
                task_id = message.payload.get("task_id", "")[:8]
                self.task_panel.complete_task(task_id, True)
            elif "task.failed" in event_type and self.task_panel:
                task_id = message.payload.get("task_id", "")[:8]
                self.task_panel.complete_task(task_id, False)
        except Exception:
            pass  # Don't crash the TUI on bus message errors
    
    def action_refresh(self) -> None:
        """Refresh all panels."""
        self.notify("Refreshing BigBrain interface...")
        if self.bigbrain_system:
            # Trigger refresh of all components
            pass
    
    def action_toggle_focus_mode(self) -> None:
        """Toggle focus mode."""
        if self.focus_panel:
            current_mode = self.focus_panel.current_mode
            new_mode = "deep_focus" if current_mode == "normal" else "normal"
            self.focus_panel.update_focus(new_mode, "demo", 0.0)
            self.notify(f"Focus mode: {new_mode}")
    
    def action_toggle_voice(self) -> None:
        """Toggle voice interaction."""
        self.voice_enabled = not self.voice_enabled
        self.mic_enabled = self.voice_enabled
        self.speaker_enabled = self.voice_enabled
        
        # Update input placeholder
        if self.voice_enabled:
            self.message_input.placeholder = "Type your message... 💬 🎤 🔊"
            self.notify("Voice interaction enabled")
        else:
            self.message_input.placeholder = "Type your message... 💬"
            self.notify("Voice interaction disabled")
        
        # Update brain panel
        if self.brain_panel:
            self.brain_panel.update_brain_status("voice_brain", "enabled" if self.voice_enabled else "disabled", self.voice_enabled)
    
    def action_show_help(self) -> None:
        """Show help information."""
        help_text = """**BigBrain TUI Help**

**Keybindings:**
• `Ctrl+C` - Quit application  
• `Ctrl+R` - Refresh all panels
• `F1` - Toggle focus mode (normal ↔ deep_focus)
• `F2` - Toggle voice interaction
• `F3` - Show this help
• `Ctrl+L` - Clear chat history
• `Ctrl+B` - Clear bus monitor
• `Tab` / `Shift+Tab` - Navigate panels

**Panels:**
• **Chat** - Conversation with Front Brain
• **Brains** - Status of all brain modules  
• **Tasks** - Active task progress
• **Bus Monitor** - Real-time message flow
• **Focus** - Attention management

**Usage:**
Type messages in the input field to interact with BigBrain.
All system activity is shown in real-time across the panels."""
        
        if self.chat_panel:
            self.chat_panel.add_message("system", help_text)
    
    def action_clear_chat(self) -> None:
        """Clear chat history."""
        if self.chat_panel:
            self.chat_panel.clear()
            self.notify("Chat cleared")
    
    def action_clear_bus(self) -> None:
        """Clear bus monitor."""
        if self.bus_monitor:
            self.bus_monitor.clear()
            self.notify("Bus monitor cleared")