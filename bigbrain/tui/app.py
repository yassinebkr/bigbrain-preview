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
        """Process user message through the full brain pipeline."""
        system = self.bigbrain_system
        if not system or not system.front_brain:
            self.chat_panel.add_message("system", "System not ready.")
            return

        front = system.front_brain
        front._conversation_history.append({"role": "user", "content": message})

        # Built-in commands
        cmd = message.lower().strip()
        if cmd == "help":
            self.chat_panel.add_message("assistant", front._get_help_text())
            return
        if cmd == "status":
            resp = await front._handle_status_query({"target": "general"})
            self.chat_panel.add_message("assistant", resp)
            return

        # Detect intent
        text_lower = message.lower()
        is_code = any(kw in text_lower for kw in [
            "run", "execute", "code", "python", "script", "write a",
            "calculate", "fibonacci", "simulate", "plot", "generate",
            "create a function", "create a class", "create a program",
        ])

        if is_code:
            # === CODE PATH: Route through PythonBrain via bus ===
            await self._handle_code_request(message, system, front)
        else:
            # === CONVERSATION PATH: FrontBrain streams directly ===
            await self._handle_conversation(message, system, front)

    async def _handle_conversation(self, message, system, front):
        """Stream a conversational response from FrontBrain LLM."""
        focus_status = front.focus_manager.get_focus_status()
        system_prompt = front._build_system_prompt(focus_status)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(front._conversation_history[-20:])

        try:
            self.chat_panel.start_streaming_message("assistant")
            stream = await system.llm_provider.chat_complete(messages=messages, stream=True)
            full = []
            async for chunk in stream:
                full.append(chunk)
                self.chat_panel.append_to_streaming(chunk)
            self.chat_panel.finish_streaming_message()
            front._conversation_history.append({"role": "assistant", "content": "".join(full)})
        except Exception as e:
            self.chat_panel.finish_streaming_message()
            self.chat_panel.add_message("system", f"❌ {e}")

    async def _handle_code_request(self, message, system, front):
        """Route code through brain pipeline. FrontBrain decides what to tell user."""
        from ..bus.message import BusMessage, MessageType, Priority

        # 1. FrontBrain acknowledges (brief, human-like)
        self.chat_panel.add_message("assistant", "On it — sending to PythonBrain...")

        # Update brain + task panels
        if self.brain_panel:
            self.brain_panel.update_brain_status("python_brain", "busy", True, message[:30])
        task_id = None
        if self.task_panel:
            task_id = self.task_panel.add_task(message[:50], "code")
            self.task_panel.update_task_progress("code", 10, "running", "Generating code...")

        # 2. Send TASK via bus
        task_msg = BusMessage(
            type=MessageType.TASK,
            source="front_brain",
            target="python_brain",
            workspace=system.workspace,
            payload={"type": "generate_and_execute", "user_request": message},
            priority=Priority.NORMAL,
        )

        result_future = asyncio.get_event_loop().create_future()

        async def _capture_result(result_msg: BusMessage):
            if result_msg.source == "python_brain" and result_msg.type == MessageType.RESULT:
                if not result_future.done():
                    result_future.set_result(result_msg)

        system.bus.subscribe("front_brain", _capture_result)

        try:
            await system.bus.send(task_msg)

            if self.task_panel:
                self.task_panel.update_task_progress("code", 40, "running", "PythonBrain working...")

            # 3. Wait for result
            try:
                result_msg = await asyncio.wait_for(result_future, timeout=90)
            except asyncio.TimeoutError:
                self.chat_panel.add_message("assistant", "PythonBrain took too long. Want me to try again?")
                if self.task_panel:
                    self.task_panel.complete_task("code", False)
                return

            if self.task_panel:
                self.task_panel.update_task_progress("code", 80, "running", "Processing result...")

            # 4. FrontBrain interprets result — decides what to tell user
            data = result_msg.payload.get("data", result_msg.payload)
            success = result_msg.payload.get("success", False)

            if success and isinstance(data, dict):
                stdout = data.get("stdout", "").strip()
                stderr = data.get("stderr", "").strip()
                exit_code = data.get("exit_code", -1)
                code_lines = data.get("generated_code", "").count("\n") + 1

                # FrontBrain uses LLM to craft human response
                summary_prompt = f"""The user asked: "{message}"

PythonBrain generated {code_lines} lines of code and executed it.
Exit code: {exit_code}
Output: {stdout[:500] if stdout else '(no output)'}
{f'Errors: {stderr[:300]}' if stderr else ''}

Write a brief, natural response to the user summarizing what was done and the result.
Do NOT include the code — just explain what happened and show key output.
If there were errors, explain them simply.
Be concise (2-4 sentences max)."""

                # Stream the human-layer response
                self.chat_panel.start_streaming_message("assistant")
                try:
                    stream = await system.llm_provider.chat_complete(
                        messages=[{"role": "user", "content": summary_prompt}],
                        stream=True, max_tokens=300,
                    )
                    full = []
                    async for chunk in stream:
                        full.append(chunk)
                        self.chat_panel.append_to_streaming(chunk)
                    self.chat_panel.finish_streaming_message()
                    summary = "".join(full)
                except Exception:
                    self.chat_panel.finish_streaming_message()
                    summary = f"Done! Output:\n{stdout[:200]}" if stdout else "Code ran successfully."
                    self.chat_panel.add_message("assistant", summary)

                front._conversation_history.append({"role": "assistant", "content": summary})

                if self.task_panel:
                    self.task_panel.complete_task("code", True)
            else:
                error = data.get("error", str(data)) if isinstance(data, dict) else str(data)
                self.chat_panel.add_message("assistant", f"PythonBrain hit an issue: {error}")
                front._conversation_history.append({"role": "assistant", "content": f"[Error: {error[:200]}]"})
                if self.task_panel:
                    self.task_panel.complete_task("code", False)

        finally:
            system.bus.unsubscribe("front_brain", _capture_result)
            if self.brain_panel:
                self.brain_panel.update_brain_status("python_brain", "idle", True)
    
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

        # Wire bus events BEFORE starting (so we catch startup events)
        if system.bus:
            system.bus.subscribe("*", self._on_bus_message)

        # Start the system (orchestrator, brains, front brain)
        try:
            await system.start()
            self.chat_panel.add_message("system", "✅ Ready! Chat with Claude below.")
        except Exception as e:
            self.chat_panel.add_message("system", f"❌ Failed to start: {e}")
            return

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
            
            # Update brain panel + task panel on brain events
            event_type = message.payload.get("event", "")
            brain_name = message.payload.get("brain", message.source)
            task_id = message.payload.get("task_id", "")[:8] if message.payload.get("task_id") else None

            if "brain.started" in event_type and task_id:
                # Brain picked up a task
                if self.brain_panel:
                    task_type = message.payload.get("task_type", "task")
                    self.brain_panel.update_brain_status(brain_name, "busy", True, task_type)
                if self.task_panel and task_id:
                    self.task_panel.add_task(f"{brain_name}: {message.payload.get('task_type', 'working')}", task_id)
                    self.task_panel.update_task_progress(task_id, 30, "running", "Processing...")

            elif "brain.complete" in event_type:
                if self.brain_panel:
                    self.brain_panel.update_brain_status(brain_name, "idle", True)
                if self.task_panel and task_id:
                    self.task_panel.update_task_progress(task_id, 100, "complete")
                    self.task_panel.complete_task(task_id, True)

            elif "brain.error" in event_type:
                if self.brain_panel:
                    self.brain_panel.update_brain_status(brain_name, "error", True)
                if self.task_panel and task_id:
                    self.task_panel.complete_task(task_id, False)

            elif "progress" in event_type:
                # Progress updates from brains
                stage = message.payload.get("stage", "working")
                if self.task_panel and task_id:
                    self.task_panel.update_task_progress(task_id, 50, "running", stage)
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