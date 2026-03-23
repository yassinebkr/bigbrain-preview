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
        self._voice_listen_task: Optional[asyncio.Task] = None
        self._voice_tts_playing = False
        
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
            self._refocus_input()
            return

        front = system.front_brain
        front._conversation_history.append({"role": "user", "content": message})

        try:
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
                "run", "execute", "code", "python", "script", "write a program",
                "write a script", "write code",
                "calculate", "fibonacci", "simulate", "plot",
                "create a function", "create a class", "create a program",
            ])

            if is_code:
                # === CODE PATH: Route through PythonBrain via bus ===
                await self._handle_code_request(message, system, front)
            else:
                # === CONVERSATION PATH: FrontBrain streams directly ===
                await self._handle_conversation(message, system, front)
        except asyncio.CancelledError:
            raise  # Let Textual handle worker cancellation
        except Exception as e:
            self.chat_panel.add_message("system", f"❌ Error: {e}")
        finally:
            # ALWAYS refocus input so user can keep typing
            self._refocus_input()

    def _refocus_input(self) -> None:
        """Restore focus to the message input field.
        
        Called after every message processing to prevent focus loss
        when widgets are mounted/updated during the worker.
        """
        if self.message_input:
            self.call_after_refresh(lambda: self.set_focus(self.message_input))

    async def _handle_conversation(self, message, system, front):
        """Stream a conversational response from FrontBrain LLM."""
        focus_status = front.focus_manager.get_focus_status()
        system_prompt = front._build_system_prompt(focus_status)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(front._conversation_history[-20:])

        response_text = ""

        # Try streaming first
        try:
            self.chat_panel.start_streaming_message("assistant")
            stream = await system.llm_provider.chat_complete(messages=messages, stream=True)
            full = []
            async for chunk in stream:
                full.append(chunk)
                self.chat_panel.append_to_streaming(chunk)
            self.chat_panel.finish_streaming_message()
            response_text = "".join(full)
        except Exception as e:
            self.chat_panel.finish_streaming_message()
            # Streaming failed — fall through to non-streaming fallback
            response_text = ""

        # Fallback: if streaming yielded nothing, try non-streaming
        if not response_text.strip():
            try:
                response_text = await system.llm_provider.chat_complete(
                    messages=messages, stream=False
                )
            except Exception as e:
                self.chat_panel.add_message("system", f"❌ LLM error: {e}")
                return

        if response_text and response_text.strip():
            # If we got text from fallback (not streaming), show it now
            if not self.chat_panel.current_streaming_message:
                self.chat_panel.add_message("assistant", response_text)
            front._conversation_history.append({"role": "assistant", "content": response_text})
        else:
            self.chat_panel.add_message("system", "⚠️ LLM returned empty response. Check model config.")

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

        result_future = asyncio.get_running_loop().create_future()

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
                generated_code = data.get("generated_code", "").strip()
                attempts = data.get("total_attempts", 1)

                # Build rich result message with code + output
                parts = []

                # Show generated code (collapsed if long)
                if generated_code:
                    code_preview = generated_code[:800]
                    if len(generated_code) > 800:
                        code_preview += "\n# ... (truncated)"
                    parts.append(f"```python\n{code_preview}\n```")

                # Show execution result
                if exit_code == 0:
                    if stdout:
                        parts.append(f"**Output:**\n```\n{stdout[:500]}\n```")
                    else:
                        parts.append("✅ Code ran successfully (no output)")
                else:
                    parts.append(f"⚠️ Exit code: {exit_code}")
                    if stderr:
                        parts.append(f"**Errors:**\n```\n{stderr[:300]}\n```")

                if attempts > 1:
                    parts.append(f"_(took {attempts} attempts via Honk loop)_")

                result_text = "\n\n".join(parts)
                self.chat_panel.add_message("assistant", result_text)

                # Store in conversation history (compact version)
                summary = f"[Code executed: exit={exit_code}, output={stdout[:100]}]"
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

        # Ensure input has focus after system boots
        self._refocus_input()
    
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
        """Toggle voice interaction — starts/stops the full STT→VoiceBrain→TTS pipeline."""
        system = self.bigbrain_system
        if not system:
            self.notify("No BigBrain system connected", severity="warning")
            return

        self.voice_enabled = not self.voice_enabled
        self.mic_enabled = self.voice_enabled
        self.speaker_enabled = self.voice_enabled

        if self.voice_enabled:
            # Enable voice on the manager
            if system.voice_manager:
                system.voice_manager.enable_voice()

            self.message_input.placeholder = "🎤 Listening... (F2 to stop, or type)"
            self.notify("🎤 Voice ON — listening for speech")
            self.chat_panel.add_message("system", "🎤 Voice mode activated. Speak naturally — I'm listening.")

            # Update brain panel
            if self.brain_panel:
                self.brain_panel.update_brain_status("voice_brain", "idle", True)

            # Start the voice listen loop in background
            self._start_voice_loop()
        else:
            # Stop listening
            if system.voice_manager:
                system.voice_manager.disable_voice()

            # Cancel background listener
            if self._voice_listen_task and not self._voice_listen_task.done():
                self._voice_listen_task.cancel()
                self._voice_listen_task = None

            self.message_input.placeholder = "Type your message... 💬"
            self.notify("🔇 Voice OFF")
            self.chat_panel.add_message("system", "🔇 Voice mode deactivated.")

            if self.brain_panel:
                self.brain_panel.update_brain_status("voice_brain", "disabled", False)

    @work(thread=False)
    async def _start_voice_loop(self) -> None:
        """Background worker: continuously listen → transcribe → respond → speak."""
        system = self.bigbrain_system
        if not system or not system.voice_manager:
            return

        vm = system.voice_manager
        vb = system.voice_brain

        while self.voice_enabled and vm.is_enabled:
            try:
                await self._voice_listen_once(vm, vb, system)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.chat_panel.add_message("system", f"🎤 Voice error: {e}")
                if self.brain_panel:
                    self.brain_panel.update_brain_status("voice_brain", "error", True)
                # Brief pause before retrying
                await asyncio.sleep(1.0)

        # Clean exit
        if self.brain_panel:
            state = "idle" if self.voice_enabled else "disabled"
            self.brain_panel.update_brain_status("voice_brain", state, self.voice_enabled)

    async def _voice_listen_once(self, vm, vb, system) -> None:
        """Run one listen→transcribe→respond→speak cycle.

        Flow:
          1. STT streams interim + final transcripts (shown in chat)
          2. Final transcript → VoiceBrain (fast LLM) for spoken response
          3. Response text shown in chat
          4. TTS streams audio chunks (plays via sounddevice or simulated)
        """
        stt = vm.stt

        # --- Phase 1: Listening (STT) ---
        if self.brain_panel:
            self.brain_panel.update_brain_status("voice_brain", "busy", True, "listening")
        self.message_input.placeholder = "🎤 Listening..."

        final_text = ""
        self.chat_panel.start_streaming_message("user")

        try:
            async for result in stt.stream():
                if not self.voice_enabled:
                    break

                text = result.get("text", "").strip()
                is_final = result.get("is_final", False)

                if is_final:
                    final_text = text
                    # Replace streaming content with final clean text
                    self.chat_panel.finish_streaming_message()
                    if final_text:
                        self.chat_panel.add_message("user", f"🎤 {final_text}")
                    break
                else:
                    # Show interim transcription — REPLACE (not append)
                    # so we see the evolving transcript, not duplicated words
                    if self.chat_panel.current_streaming_message:
                        self.chat_panel.current_streaming_message.replace_content(f"🎤 {text}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.chat_panel.finish_streaming_message()
            self.chat_panel.add_message("system", f"🎤 STT error: {e}")
            return

        # Make sure streaming is finished even if we got no results
        if self.chat_panel.current_streaming_message:
            self.chat_panel.finish_streaming_message()

        if not final_text or not self.voice_enabled:
            # Nothing transcribed or voice was toggled off — go back to idle
            if self.brain_panel and self.voice_enabled:
                self.brain_panel.update_brain_status("voice_brain", "idle", True)
            return

        # Check for stop commands
        if any(w in final_text.lower() for w in vm.stop_words):
            self.chat_panel.add_message("system", "🛑 Voice stopped by command.")
            self.action_toggle_voice()
            return

        # --- Phase 2: Thinking (VoiceBrain LLM) ---
        if self.brain_panel:
            self.brain_panel.update_brain_status("voice_brain", "busy", True, "thinking")
        self.message_input.placeholder = "🧠 Thinking..."

        response_text = ""
        try:
            if vb and vb._running:
                # Stream response for lower perceived latency
                self.chat_panel.start_streaming_message("assistant")
                chunks = []
                async for sentence in vb.stream_response(final_text):
                    chunks.append(sentence)
                    self.chat_panel.append_to_streaming(sentence)
                self.chat_panel.finish_streaming_message()
                response_text = "".join(chunks)
            else:
                # Fallback: use Front Brain conversation path
                if system.front_brain:
                    system.front_brain._conversation_history.append(
                        {"role": "user", "content": final_text}
                    )
                    focus_status = system.front_brain.focus_manager.get_focus_status()
                    system_prompt = system.front_brain._build_system_prompt(focus_status)
                    messages = [{"role": "system", "content": system_prompt}]
                    messages.extend(system.front_brain._conversation_history[-20:])

                    response_text = await system.llm_provider.chat_complete(
                        messages=messages, stream=False
                    )
                    self.chat_panel.add_message("assistant", response_text)
                    system.front_brain._conversation_history.append(
                        {"role": "assistant", "content": response_text}
                    )
                else:
                    response_text = f"I heard: {final_text}"
                    self.chat_panel.add_message("assistant", response_text)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if self.chat_panel.current_streaming_message:
                self.chat_panel.finish_streaming_message()
            response_text = f"Sorry, hit a snag — {e}"
            self.chat_panel.add_message("assistant", response_text)

        if not response_text or not self.voice_enabled:
            if self.brain_panel and self.voice_enabled:
                self.brain_panel.update_brain_status("voice_brain", "idle", True)
            return

        # --- Phase 3: Speaking (TTS) ---
        if self.brain_panel:
            self.brain_panel.update_brain_status("voice_brain", "busy", True, "speaking")
        self.message_input.placeholder = "🔊 Speaking..."
        self._voice_tts_playing = True

        try:
            tts = vm.tts
            has_audio_playback = self._has_audio_playback()

            async for chunk in tts.stream(response_text):
                if not self.voice_enabled:
                    break

                audio = chunk.get("audio", b"")
                word = chunk.get("word", "")
                is_final = chunk.get("is_final", False)

                if has_audio_playback and audio:
                    # Real audio playback via sounddevice
                    await self._play_audio_chunk(audio)
                elif not has_audio_playback:
                    # Mock mode: simulate timing
                    duration = chunk.get("duration", 0.1)
                    await asyncio.sleep(duration)

                if is_final:
                    break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.chat_panel.add_message("system", f"🔊 TTS error: {e}")
        finally:
            self._voice_tts_playing = False

        # Back to listening (auto-listen loop continues)
        if self.brain_panel and self.voice_enabled:
            self.brain_panel.update_brain_status("voice_brain", "idle", True)
        if self.voice_enabled:
            self.message_input.placeholder = "🎤 Listening..."
            # Small pause between turns
            await asyncio.sleep(0.5)

    def _has_audio_playback(self) -> bool:
        """Check if real audio playback is available (sounddevice installed)."""
        try:
            import sounddevice  # noqa: F401
            return True
        except ImportError:
            return False

    async def _play_audio_chunk(self, audio_data: bytes) -> None:
        """Play a raw PCM audio chunk via sounddevice.

        Audio format: 16-bit signed little-endian, 16kHz, mono.
        Non-blocking — uses sounddevice's async-compatible play.
        """
        try:
            import sounddevice as sd
            import numpy as np

            # Convert bytes → numpy int16 → float32 for playback
            samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32767.0
            sd.play(samples, samplerate=16000, blocking=False)
            # Wait roughly the duration of the chunk
            duration = len(samples) / 16000
            await asyncio.sleep(duration)
        except Exception:
            # If playback fails, just skip — don't crash the voice loop
            pass
    
    def action_show_help(self) -> None:
        """Show help information."""
        help_text = """**BigBrain TUI Help**

**Keybindings:**
• `Ctrl+C` - Quit application  
• `Ctrl+R` - Refresh all panels
• `F1` - Toggle focus mode (normal ↔ deep_focus)
• `F2` - Toggle voice (mic → STT → VoiceBrain → TTS → speaker)
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

**Voice Mode (F2):**
Press F2 to toggle voice. When active:
• 🎤 Mic captures audio → Deepgram Nova-3 transcribes
• 🧠 VoiceBrain (fast Sonnet LLM) generates spoken-style response
• 🔊 Cartesia Sonic TTS plays audio back
• Say "stop" or "cancel" to deactivate voice
• You can still type while voice is active

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