"""Front Brain - User-facing intelligence layer for BigBrain."""

import asyncio
import time
from typing import Any, Dict, List, Optional

from ..bus.bus import MessageBus
from ..bus.message import BusMessage, MessageType, Priority
from ..memory.memory_manager import MemoryManager
from .focus_manager import FocusManager, FocusMode, FocusState


class FrontBrain:
    """
    Front Brain - The user-facing intelligence of BigBrain.
    
    Layer 1 of the 3-layer architecture. This is the "person" the user
    talks to - the personality, the relationship, the context holder.
    
    Key Responsibilities:
    - User interaction and conversation management
    - Intent understanding and task routing
    - Focus system management and attention filtering
    - Context preservation across sessions
    - Natural language communication
    - Proactive notifications and suggestions
    
    Design Principles:
    - Behaves like a human colleague - silent when not needed
    - Guards user's flow state and focus
    - Provides information without overwhelming
    - Makes intelligent decisions about what to surface
    """
    
    def __init__(self, bus: MessageBus, user_name: str = "User", llm_provider=None):
        """
        Initialize Front Brain.
        
        Args:
            bus: MessageBus for communication
            user_name: Name of the user for personalization
            llm_provider: LLM provider for intelligent responses
        """
        self.bus = bus
        self.user_name = user_name
        self.name = "front_brain"
        self.llm_provider = llm_provider
        
        # Focus and attention management
        self.focus_manager = FocusManager()
        
        # Memory for context and relationships
        self.memory = MemoryManager(
            brain_name=self.name,
            project_name="user_context",
            workspace="front_brain"
        )
        
        # State
        self._running = False
        self._current_conversation_id: Optional[str] = None
        self._conversation_history: List[Dict[str, str]] = []
        
        # Load user preferences and context
        self._load_user_context()
    
    async def start(self) -> None:
        """Start the Front Brain and register with message bus."""
        if self._running:
            raise RuntimeError("Front Brain is already running")
        
        self._running = True
        
        # Subscribe to all bus messages for filtering
        self.bus.subscribe("*", self._handle_bus_event)
        self.bus.subscribe(self.name, self._handle_direct_message)
        
        # Announce availability
        await self.bus.broadcast_event(
            source=self.name,
            event_type="front_brain.started",
            payload={"user": self.user_name},
            priority=Priority.LOW
        )
        
        # Set initial focus
        await self._initialize_focus()
    
    async def stop(self) -> None:
        """Stop the Front Brain."""
        if not self._running:
            return
        
        self._running = False
        
        # Save current context
        await self._save_user_context()
        
        # Unregister from bus
        self.bus.unsubscribe("*", self._handle_bus_event)
        self.bus.unsubscribe(self.name, self._handle_direct_message)
        
        await self.bus.broadcast_event(
            source=self.name,
            event_type="front_brain.stopped",
            payload={"user": self.user_name},
            priority=Priority.LOW
        )
    
    async def handle_user_input(self, input_text: str, input_type: str = "text") -> str:
        """
        Process user input and return response.
        
        When a real LLM is available, uses it for all responses.
        Falls back to pattern-matching + mock when no LLM configured.
        
        Args:
            input_text: User's input text
            input_type: Type of input ("text", "voice", "command")
            
        Returns:
            Response text for the user
        """
        self.focus_manager.mark_user_activity()
        
        # Store conversation turn
        self._conversation_history.append({"role": "user", "content": input_text})
        self.memory.store_conversation_turn("user", input_text, {
            "type": input_type,
            "conversation_id": self._current_conversation_id
        })
        
        # Handle built-in commands first (no LLM needed)
        command = input_text.lower().strip()
        if command == "help":
            response = self._get_help_text()
        elif command == "status":
            response = await self._handle_status_query({"target": "general"})
        elif any(word in command for word in ["deep focus", "normal focus", "overview"]):
            intent = await self._analyze_intent(input_text)
            response = await self._handle_focus_command(intent)
        elif self.llm_provider and not isinstance(self.llm_provider, type(None)):
            # Use LLM for everything else
            response = await self._llm_respond(input_text)
        else:
            # Fallback to pattern matching
            intent = await self._analyze_intent(input_text)
            if intent["type"] == "task_request":
                response = await self._handle_task_request(intent, input_text)
            elif intent["type"] == "conversation":
                response = await self._handle_conversation(intent, input_text)
            else:
                response = await self._handle_unknown_input(input_text)
        
        # Store response
        self._conversation_history.append({"role": "assistant", "content": response})
        self.memory.store_conversation_turn("assistant", response, {
            "conversation_id": self._current_conversation_id
        })
        
        return response
    
    async def _llm_respond(self, input_text: str) -> str:
        """Generate response using the real LLM with full conversation context."""
        # Check if user wants code execution
        text_lower = input_text.lower()
        is_code_request = any(kw in text_lower for kw in [
            "run", "execute", "code", "python", "script", "write a program",
            "write code", "create a script", "calculate", "fibonacci", "simulate",
            "plot", "generate", "```"
        ])
        
        if is_code_request and "```" in input_text:
            # User provided code directly — extract and execute
            code = self._extract_code_blocks(input_text)
            if code:
                exec_result = await self._execute_code_direct(code)
                return f"Running your code...\n\n```\n{exec_result}\n```"
        
        # Build system prompt with current context
        focus_status = self.focus_manager.get_focus_status()
        system_prompt = self._build_system_prompt(focus_status)
        
        # For code requests, tell Claude to include runnable code
        if is_code_request:
            system_prompt += "\n\nIMPORTANT: When the user asks for code, include a complete, runnable Python script in a ```python code block. The code WILL be auto-executed, so make sure it's self-contained and prints output."
        
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history (keep last 20 turns for context)
        history = self._conversation_history[-20:]
        messages.extend(history)
        
        try:
            response = await self.llm_provider.chat_complete(
                messages=messages,
                stream=False
            )
            
            # Auto-execute code blocks if this was a code request
            if is_code_request and response and "```python" in response:
                code = self._extract_code_blocks(response)
                if code:
                    exec_result = await self._execute_code_direct(code)
                    response += f"\n\n📍 **Execution Output:**\n```\n{exec_result}\n```"
            
            return response
        except Exception as e:
            return f"I encountered an error processing your request: {e}"
    
    @staticmethod
    def _extract_code_blocks(text: str) -> str:
        """Extract Python code from markdown code blocks."""
        import re
        # Find all ```python ... ``` blocks
        pattern = r'```python\s*\n(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return "\n\n".join(matches)
        # Try generic ``` blocks
        pattern = r'```\s*\n(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return "\n\n".join(matches)
        return ""
    
    async def _execute_code_direct(self, code: str) -> str:
        """Execute Python code directly via subprocess."""
        import asyncio
        import sys
        import tempfile
        from pathlib import Path
        
        # Write code to temp file
        work_dir = Path("work/execution")
        work_dir.mkdir(parents=True, exist_ok=True)
        
        script_path = work_dir / "script.py"
        script_path.write_text(code, encoding="utf-8")
        
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            
            output = stdout.decode("utf-8", errors="replace").strip()
            errors = stderr.decode("utf-8", errors="replace").strip()
            
            if proc.returncode != 0:
                return f"{output}\n⚠️ STDERR:\n{errors}" if output else f"⚠️ Error:\n{errors}"
            return output if output else "(no output)"
        except asyncio.TimeoutError:
            return "⚠️ Execution timed out (30s limit)"
        except Exception as e:
            return f"⚠️ Execution error: {e}"
    
    def _build_system_prompt(self, focus_status: dict) -> str:
        """Build the system prompt for the Front Brain LLM."""
        active_ws = focus_status.get("active_workspace", "default")
        mode = focus_status.get("focus_mode", "normal")
        
        return f"""You are BigBrain, a multi-brain AI assistant system. You are the Front Brain — the user-facing personality layer.

Your name is BigBrain. You're helpful, direct, and technically capable.

Current state:
- User: {self.user_name}
- Active workspace: {active_ws}
- Focus mode: {mode}
- Available brains: PythonBrain (code execution), ResearcherBrain (web research)

Capabilities you can help with:
- Writing and executing Python code
- Research and analysis
- General conversation and questions
- Managing focus and attention across workspaces
- Task decomposition and delegation

When the user asks you to write or run code, provide the code and explain what it does.
When the user asks a question, answer it directly and helpfully.
Be conversational but concise. No filler phrases like "Great question!" or "I'd be happy to help!"
"""
    
    def _get_help_text(self) -> str:
        """Return help text."""
        return """**BigBrain Commands & Capabilities**

💬 **Chat** — Just talk naturally. I use a real LLM to understand and respond.
🐍 **Code** — "Write a fibonacci function" or paste code in ``` blocks to execute
🔍 **Research** — "Research quantum computing" (routes to Researcher Brain)
🎯 **Focus** — "deep focus" / "normal focus" / "overview" to change attention mode
📊 **Status** — Check system and workspace status
❓ **Help** — This message

Type 'quit' or 'exit' to stop."""
    
    async def _handle_bus_event(self, event: BusMessage) -> None:
        """
        Handle events from the message bus through focus filtering.
        
        This is where the Focus Manager filters events based on
        current focus mode and workspace states.
        """
        if not self._running or event.source == self.name:
            return  # Don't process our own events
        
        # Only process EVENT type messages in the wildcard handler
        if event.type not in (MessageType.EVENT, "event"):
            return
        
        # Filter through focus system
        filtered_event = self.focus_manager.filter_event(event)
        
        if filtered_event:
            await self._process_filtered_event(filtered_event)
    
    async def _handle_direct_message(self, message: BusMessage) -> None:
        """Handle messages sent directly to the Front Brain."""
        # Skip broadcasts — already handled by _handle_bus_event wildcard
        if message.target == "*":
            return
        
        if message.type == MessageType.RESULT:
            await self._handle_task_result(message)
        
        elif message.type == MessageType.QUERY:
            await self._handle_query(message)
        
        elif message.type == MessageType.EVENT:
            # Direct events bypass focus filtering
            await self._process_filtered_event(message)
    
    async def _process_filtered_event(self, event: BusMessage) -> None:
        """
        Process an event that passed focus filtering.
        
        Decides whether and how to surface the event to the user.
        """
        event_type = event.payload.get("event", str(event.type))
        workspace = event.workspace or "system"
        
        # Check if we should interrupt the user
        should_interrupt = self._should_interrupt_user(event)
        
        if should_interrupt:
            # Generate natural language notification
            notification = await self._generate_notification(event)
            
            # For this preview, we'll just print the notification
            # In a real system, this would go to TTS/UI
            print(f"\n🔔 {notification}\n")
        
        # Store event for context
        self.memory.store(
            content=f"Event: {event_type} from {event.source}",
            memory_type="working",
            metadata={
                "event_type": event_type,
                "source": event.source,
                "workspace": workspace,
                "priority": str(event.priority),
                "interrupted_user": should_interrupt
            }
        )
    
    async def _analyze_intent(self, input_text: str) -> Dict[str, Any]:
        """
        Analyze user input to determine intent.
        
        In production, this would use LLM-based intent classification.
        For preview, we use simple pattern matching.
        """
        text_lower = input_text.lower()
        
        # Focus management commands
        focus_keywords = ["focus", "attention", "switch", "workspace"]
        if any(keyword in text_lower for keyword in focus_keywords):
            
            # Determine specific focus action
            if "deep" in text_lower or "concentrate" in text_lower:
                return {"type": "focus_management", "action": "set_deep_focus"}
            elif "overview" in text_lower or "all" in text_lower:
                return {"type": "focus_management", "action": "set_overview"}
            elif "normal" in text_lower:
                return {"type": "focus_management", "action": "set_normal"}
            else:
                return {"type": "focus_management", "action": "query_focus"}
        
        # Task requests
        task_keywords = ["run", "execute", "search", "research", "analyze", "code"]
        if any(keyword in text_lower for keyword in task_keywords):
            
            # Determine task type
            if "code" in text_lower or "python" in text_lower:
                return {"type": "task_request", "task_type": "execute_code", "content": input_text}
            elif "search" in text_lower or "research" in text_lower:
                return {"type": "task_request", "task_type": "research", "query": input_text}
            else:
                return {"type": "task_request", "task_type": "general", "content": input_text}
        
        # Status queries
        status_keywords = ["status", "what's", "how", "show", "list"]
        if any(keyword in text_lower for keyword in status_keywords):
            return {"type": "status_query", "target": "general"}
        
        # Default to conversation
        return {"type": "conversation", "content": input_text}
    
    async def _handle_focus_command(self, intent: Dict[str, Any]) -> str:
        """Handle focus management commands."""
        action = intent.get("action")
        
        if action == "set_deep_focus":
            self.focus_manager.set_focus_mode(FocusMode.DEEP_FOCUS, "user")
            return "Switched to Deep Focus mode. I'll only interrupt you for critical issues."
        
        elif action == "set_overview":
            self.focus_manager.set_focus_mode(FocusMode.OVERVIEW, "user")
            return "Switched to Overview mode. I'll keep you updated on all active workspaces."
        
        elif action == "set_normal":
            self.focus_manager.set_focus_mode(FocusMode.NORMAL, "user")
            return "Switched to Normal focus mode. I'll surface important events and completion notifications."
        
        elif action == "query_focus":
            status = self.focus_manager.get_focus_status()
            active_ws = status.get("active_workspace", "none")
            mode = status["focus_mode"]
            
            return (f"Current focus: {mode.replace('_', ' ').title()} mode. "
                   f"Active workspace: {active_ws}. "
                   f"You've been idle for {status['idle_minutes']:.1f} minutes.")
        
        return "I didn't understand that focus command."
    
    async def _handle_task_request(self, intent: Dict[str, Any], original_text: str) -> str:
        """Route task requests to appropriate orchestrators."""
        task_type = intent.get("task_type")
        workspace = "default"  # Could be determined from context
        
        # Create task message
        task_payload = {
            "type": task_type,
            "user_request": original_text,
            "timestamp": time.time()
        }
        
        if task_type == "execute_code":
            # Check if user provided actual code or just a description
            if "```" in original_text:
                # Extract code from markdown fences
                code_start = original_text.find("```") + 3
                code_end = original_text.rfind("```")
                code = original_text[code_start:code_end].strip()
                if code.startswith("python"):
                    code = code[6:].strip()
                task_payload["code"] = code
                task_payload["type"] = "execute_code"
            else:
                # Natural language request — let PythonBrain generate code via LLM
                task_payload["type"] = "generate_and_execute"
                task_payload["user_request"] = original_text
            
            target = "python_brain"
        
        elif task_type == "research":
            # Extract query
            query = original_text.replace("search", "").replace("research", "").strip()
            task_payload["query"] = query
            target = "orchestrator_research"
        
        else:
            # Route to general orchestrator
            target = f"orchestrator_{workspace}"
        
        # Send task
        task_message = await self.bus.send_task(
            source=self.name,
            target=target,
            task_data=task_payload,
            workspace=workspace,
            priority=Priority.NORMAL
        )
        
        # Set workspace to active focus
        self.focus_manager.set_workspace_focus(workspace, FocusState.ACTIVE, "task_start")
        
        # Store task context
        self._current_conversation_id = task_message.id
        
        return f"I'll work on that {task_type.replace('_', ' ')} for you. I'll let you know when it's done."
    
    async def _handle_status_query(self, intent: Dict[str, Any]) -> str:
        """Handle status and information queries."""
        focus_status = self.focus_manager.get_focus_status()
        
        response_parts = []
        
        # Focus status
        mode = focus_status["focus_mode"].replace("_", " ").title()
        response_parts.append(f"Focus: {mode} mode")
        
        # Active workspace
        active_ws = focus_status.get("active_workspace")
        if active_ws:
            response_parts.append(f"Active workspace: {active_ws}")
        
        # Workspace summary
        workspaces = focus_status.get("workspaces", {})
        if workspaces:
            ws_summary = []
            for ws_name, ws_data in workspaces.items():
                state = ws_data["state"]
                buffered = ws_data.get("buffered_events", 0)
                if buffered > 0:
                    ws_summary.append(f"{ws_name} ({state}, {buffered} pending)")
                else:
                    ws_summary.append(f"{ws_name} ({state})")
            
            if ws_summary:
                response_parts.append("Workspaces: " + ", ".join(ws_summary))
        
        # Suggestions
        suggestion = self.focus_manager.suggest_focus_change()
        if suggestion:
            if suggestion["type"] == "workspace_attention":
                response_parts.append(f"💡 Suggestion: Check {suggestion['workspace']} - {suggestion['reason']}")
            elif suggestion["type"] == "mode_change":
                mode_name = suggestion["suggested_mode"].value.replace("_", " ").title()
                response_parts.append(f"💡 Suggestion: Switch to {mode_name} - {suggestion['reason']}")
        
        return ". ".join(response_parts) + "."
    
    async def _handle_conversation(self, intent: Dict[str, Any], input_text: str) -> str:
        """Handle general conversation using LLM when available."""
        # Use LLM for natural conversation when available
        if self.llm_provider:
            try:
                response = await self.llm_provider.chat_complete(
                    messages=[
                        {"role": "system", "content": (
                            f"You are BigBrain, a multi-brain AI assistant. "
                            f"The user's name is {self.user_name}. Be helpful and conversational. "
                            f"You can help with coding, research, analysis, and general tasks."
                        )},
                        {"role": "user", "content": input_text}
                    ],
                    stream=False
                )
                return response
            except Exception:
                pass  # Fall through to hardcoded responses
        
        # Fallback: simple pattern matching
        text_lower = input_text.lower()
        
        if any(greeting in text_lower for greeting in ["hello", "hi", "hey"]):
            return f"Hello {self.user_name}! I'm here to help you stay focused and manage your work. What can I help you with?"
        
        elif any(thanks in text_lower for thanks in ["thank", "thanks"]):
            return "You're welcome! Let me know if you need anything else."
        
        elif "help" in text_lower:
            return ("I can help you with:\n"
                   "- Running code and research tasks\n"
                   "- Managing your focus and attention\n"
                   "- Checking status of your workspaces\n"
                   "- Filtering notifications based on your current focus\n"
                   "\nJust ask me naturally!")
        
        else:
            return "I understand you're talking to me, but I'm not sure how to help with that. Could you be more specific?"
    
    async def _handle_unknown_input(self, input_text: str) -> str:
        """Handle input that couldn't be classified."""
        # Try LLM for a natural response
        if self.llm_provider:
            try:
                return await self.llm_provider.chat_complete(
                    messages=[
                        {"role": "system", "content": f"You are BigBrain, an AI assistant. The user's name is {self.user_name}."},
                        {"role": "user", "content": input_text}
                    ],
                    stream=False
                )
            except Exception:
                pass
        return "I'm not sure what you want me to do with that. Try asking me to run code, research something, or check status."
    
    async def _handle_task_result(self, message: BusMessage) -> None:
        """Handle results from tasks we initiated."""
        result = message.payload
        success = result.get("success", False)
        
        if success:
            notification = "✅ Task completed successfully!"
            
            # Add specific details based on result type
            if "summary" in result:
                notification += f" Summary: {result['summary'][:100]}..."
            elif "stdout" in result:
                stdout = result["stdout"].strip()
                if stdout:
                    notification += f" Output: {stdout[:100]}..."
        else:
            error = result.get("error", "Unknown error")
            notification = f"❌ Task failed: {error}"
        
        # Check if we should interrupt based on focus mode
        if self.focus_manager.focus_rules.current_mode != FocusMode.DEEP_FOCUS:
            print(f"\n🔔 {notification}\n")
        
        # Store result in memory
        self.memory.store(
            content=f"Task result: {notification}",
            memory_type="working",
            metadata={"result": result, "success": success}
        )
    
    async def _handle_query(self, message: BusMessage) -> None:
        """Handle queries sent to the Front Brain."""
        query_type = message.payload.get("type")
        
        if query_type == "focus_status":
            await self.bus.send_result(
                source=self.name,
                result_data=self.focus_manager.get_focus_status(),
                reply_to=message.id
            )
        
        elif query_type == "user_context":
            context = {
                "user_name": self.user_name,
                "current_conversation": self._current_conversation_id,
                "memory_stats": self.memory.get_memory_stats(),
                "focus_status": self.focus_manager.get_focus_status()
            }
            
            await self.bus.send_result(
                source=self.name,
                result_data=context,
                reply_to=message.id
            )
    
    def _should_interrupt_user(self, event: BusMessage) -> bool:
        """
        Decide if an event should interrupt the user.
        
        This considers focus mode, event priority, and timing.
        """
        # Critical events always interrupt
        if event.priority >= Priority.CRITICAL:
            return True
        
        # In deep focus, only critical events interrupt
        if self.focus_manager.focus_rules.current_mode == FocusMode.DEEP_FOCUS:
            return False
        
        # High priority events interrupt in normal/overview modes
        if event.priority >= Priority.HIGH:
            return True
        
        # Task completion events interrupt if from active workspace
        if (event.payload.get("event") in ["task.complete", "task.failed"] and
            event.workspace):
            ws_focus = self.focus_manager.workspaces.get(event.workspace)
            if ws_focus and ws_focus.state == FocusState.ACTIVE:
                return True
        
        return False
    
    async def _generate_notification(self, event: BusMessage) -> str:
        """Generate natural language notification for an event."""
        event_type = event.payload.get("event", str(event.type))
        source = event.source
        workspace = event.workspace or "system"
        
        # Simple notification generation
        # In production, this would use LLM for natural language
        
        if event_type == "task.complete":
            return f"Your {source.replace('_', ' ')} task in {workspace} is complete."
        
        elif event_type == "task.failed":
            error = event.payload.get("error", "unknown error")
            return f"Your {source.replace('_', ' ')} task failed: {error}"
        
        elif event_type == "brain.error":
            return f"There's an issue with {source.replace('_', ' ')} in {workspace}."
        
        elif event_type.endswith(".started"):
            return f"{source.replace('_', ' ').title()} has started working in {workspace}."
        
        else:
            return f"Update from {source.replace('_', ' ')} in {workspace}: {event_type}"
    
    async def _initialize_focus(self) -> None:
        """Initialize focus settings based on user preferences."""
        # Load saved focus preferences
        saved_mode = self.memory.get_user_preference("focus_mode")
        if saved_mode:
            try:
                mode = FocusMode(saved_mode)
                self.focus_manager.set_focus_mode(mode, "loaded_preference")
            except ValueError:
                pass  # Invalid saved mode, use default
        
        # Set up default workspace
        self.focus_manager.set_workspace_focus("default", FocusState.ACTIVE, "initialization")
    
    def _load_user_context(self) -> None:
        """Load user context and preferences."""
        # Load user name if previously saved
        saved_name = self.memory.get_user_preference("user_name")
        if saved_name:
            self.user_name = saved_name
        
        # Load other preferences
        self.focus_manager.focus_rules.auto_switch_enabled = self.memory.get_user_preference(
            "auto_focus_switch", True
        )
    
    async def _save_user_context(self) -> None:
        """Save current user context and preferences."""
        self.memory.store_user_preference("user_name", self.user_name)
        self.memory.store_user_preference("focus_mode", str(self.focus_manager.focus_rules.current_mode))
        self.memory.store_user_preference("auto_focus_switch", self.focus_manager.focus_rules.auto_switch_enabled)
        
        # Consolidate memories before shutdown
        # Consolidate memories (sync call, run in executor to not block)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.memory.consolidate_memories)
    
    def get_status(self) -> Dict[str, Any]:
        """Get Front Brain status."""
        return {
            "name": self.name,
            "running": self._running,
            "user_name": self.user_name,
            "current_conversation": self._current_conversation_id,
            "focus_status": self.focus_manager.get_focus_status(),
            "memory_stats": self.memory.get_memory_stats()
        }