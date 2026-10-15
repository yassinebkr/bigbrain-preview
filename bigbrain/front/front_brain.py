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
        
        # Brain registry for system prompt
        self._registered_brains: Dict[str, str] = {}
        
        # Load user preferences and context
        self._load_user_context()
    
    def register_brain(self, name: str, description: str) -> None:
        """Register a brain so the Front Brain knows how to delegate."""
        self._registered_brains[name] = description
    
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
    
    def _current_project(self) -> str | None:
        """The selected working project, if any (and if web is loaded)."""
        try:
            from ..web.fs_api import get_current_project

            return get_current_project()
        except Exception:
            return None

    async def _llm_respond(self, input_text: str) -> str:
        """Generate response using the real LLM with full conversation context.
        
        The LLM will return either plain text (conversation) or delegation
        JSON (task request). The caller handles both cases.
        """
        # Build system prompt with current context
        focus_status = self.focus_manager.get_focus_status()
        system_prompt = self._build_system_prompt(focus_status)
        
        messages = [{"role": "system", "content": system_prompt}]

        # Project context: the chat knows which project the user works in;
        # generated files land there (the pool's work_dir follows it too).
        project = self._current_project()
        if project:
            messages.append({"role": "system", "content": (
                f"Current project: '{project}'. The user is working inside "
                f"the project directory '{project}/' of the workspace. "
                f"File operations and generated code belong in this project."
            )})
        
        # Add conversation history (keep last 20 turns for context)
        history = self._conversation_history[-20:]
        messages.extend(history)
        
        try:
            response = await self.llm_provider.chat_complete(
                messages=messages,
                stream=False
            )
            
            return response
        except Exception as e:
            return f"I encountered an error processing your request: {e}"
    
    # _execute_code_direct REMOVED — Front Brain must never execute code.
    # All execution goes through the orchestrator → PythonBrain pipeline.
    
    def _build_system_prompt(self, focus_status: dict) -> str:
        """Build the system prompt for the Front Brain LLM.
        
        The Front Brain is a conversational layer that DELEGATES work.
        It never writes code, never does research — it routes tasks to
        the orchestrator as a SINGLE compound request and stays available
        for conversation. The ORCHESTRATOR handles decomposition into
        subtasks with dependencies.
        """
        active_ws = focus_status.get("active_workspace", "default")
        mode = focus_status.get("focus_mode", "normal")
        
        # Build brain list from registered brains
        brain_lines = []
        if hasattr(self, '_registered_brains') and self._registered_brains:
            for name, desc in self._registered_brains.items():
                brain_lines.append(f"  - {name}: {desc}")
        else:
            brain_lines = [
                "  - python_brain: Generates and executes Python code",
                "  - researcher: Researches topics, gathers information",
            ]
        brains_str = "\n".join(brain_lines)
        
        return f"""You are BigBrain's Front Brain — the user-facing conversational layer.

You are NOT a code assistant. You are NOT a chatbot. You are the personality and router of a multi-brain AI system.

YOUR JOB:
1. Talk to the user naturally — answer questions, chat, manage context
2. When the user wants WORK done (code, research, analysis), DELEGATE it as ONE task
3. Stay available for conversation while work runs in background

DELEGATION: When the user asks for work, respond with EXACTLY this JSON format:
{{"reply": "brief natural acknowledgment to the user", "task": "full description of what the user wants done, preserving ALL details and intent"}}

IMPORTANT: Send the ENTIRE request as ONE task. Do NOT break it into subtasks yourself.
The orchestrator will decompose it into subtasks with proper dependencies.
For example, "research sorting algorithms and benchmark them" is ONE task — the orchestrator
will figure out that research must complete before benchmarking can start.

CONVERSATION: For greetings, questions, status, opinions — just respond naturally as plain text (no JSON).

RULES:
- NEVER write code yourself. NEVER. That's PythonBrain's job.
- NEVER do research yourself. That's Researcher's job.
- NEVER decompose tasks into multiple items — that's the Orchestrator's job.
- Keep task acknowledgments brief and natural: "On it.", "Working on that.", "Let me look into that."
- You CAN answer factual questions directly (those aren't tasks)
- You CAN give opinions, explain concepts, have conversations
- Be direct, no filler phrases

Current state:
- Active workspace: {active_ws}
- Focus mode: {mode}

Available brains (for your awareness, NOT for you to assign):
{brains_str}

Examples:
User: "write a fibonacci function"
You: {{"reply": "On it.", "task": "Write a fibonacci function in Python and execute it"}}

User: "what's the capital of France?"  
You: Paris.

User: "research the best sorting algorithms and then implement quicksort"
You: {{"reply": "Got it — I'll have the team research first, then code it up.", "task": "Research the best sorting algorithms with time/space complexity comparisons, then implement quicksort in Python using the research findings and benchmark it"}}

User: "hello"
You: Hey! What are you working on?"""
    
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
        
        elif message.type in (MessageType.TASK, "task"):
            # Handle user messages from Morphable UI
            payload = message.payload or {}
            if payload.get("type") == "user_message":
                await self._handle_ui_message(message)
    
    async def _handle_ui_message(self, message: BusMessage) -> None:
        """
        Handle a user message from the Morphable UI.
        
        Processes the text through handle_user_input(), then sends
        the response back on the bus as a chat.message event so the
        ChatPanel in the browser can display it.
        
        Delegation sends ONE compound task to the orchestrator, which
        handles decomposition into subtasks with proper dependencies.
        """
        import json
        import re
        
        text = message.payload.get("text", "").strip()
        if not text:
            return
        
        try:
            # Process through the normal input pipeline
            response = await self.handle_user_input(text, input_type="web")
            
            # Try to parse as delegation JSON
            parsed = self._try_parse_delegation(response)
            
            if parsed and "task" in parsed:
                # Front Brain wants to delegate — send the reply part to chat
                reply_text = parsed.get("reply", "Working on it...")
                await self._emit_chat_message("assistant", reply_text)
                
                # Send ONE compound task to the orchestrator.
                # Always route to "default" workspace — the system only creates
                # one orchestrator (orchestrator_default). Using the focus
                # manager's active workspace caused tasks to be sent to
                # non-existent orchestrators (e.g. orchestrator_python-dev).
                ws = "default"
                task_request = parsed["task"]
                description = task_request[:60] + "..." if len(task_request) > 60 else task_request
                await self.bus.send_task(
                    source=self.name,
                    target=f"orchestrator_{ws}",
                    task_data={
                        "type": "compound",
                        "request": task_request,
                        "description": description,
                        "user_request": task_request,
                        "reply_to_ui": True,
                    },
                    priority=Priority.NORMAL,
                )
            elif parsed and "tasks" in parsed:
                # Legacy multi-task format — merge into single compound request
                reply_text = parsed.get("reply", "Working on it...")
                await self._emit_chat_message("assistant", reply_text)
                
                tasks = parsed.get("tasks", [])
                combined_request = "; then ".join(
                    t.get("request", t.get("description", "")) for t in tasks
                )
                ws = "default"  # Always route to the single orchestrator
                description = combined_request[:60] + "..." if len(combined_request) > 60 else combined_request
                await self.bus.send_task(
                    source=self.name,
                    target=f"orchestrator_{ws}",
                    task_data={
                        "type": "compound",
                        "request": combined_request,
                        "description": description,
                        "user_request": combined_request,
                        "reply_to_ui": True,
                    },
                    priority=Priority.NORMAL,
                )
            else:
                # Plain text response — send to chat
                await self._emit_chat_message("assistant", response)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            await self._emit_chat_message("system", f"Error: {e}")
    
    @staticmethod
    def _try_parse_delegation(response: str) -> dict | None:
        """
        Try to parse a Front Brain response as delegation JSON.
        
        Handles:
        - New format: {"reply": "...", "task": "single compound request"}
        - Legacy format: {"reply": "...", "tasks": [...]}
        - Raw JSON, markdown-fenced JSON, JSON embedded in text
        """
        import json
        import re
        
        if not response:
            return None
        
        # 1. Try raw JSON
        try:
            parsed = json.loads(response.strip())
            if isinstance(parsed, dict) and ("task" in parsed or "tasks" in parsed):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        
        # 2. Try extracting from markdown code fences
        fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL)
        if fence_match:
            try:
                parsed = json.loads(fence_match.group(1).strip())
                if isinstance(parsed, dict) and ("task" in parsed or "tasks" in parsed):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
        
        # 3. Try finding JSON object with "task" key in the text
        brace_match = re.search(r'\{[^{}]*"task(?:s)?"\s*:.*?\}', response, re.DOTALL)
        if brace_match:
            try:
                parsed = json.loads(brace_match.group(0))
                if isinstance(parsed, dict) and ("task" in parsed or "tasks" in parsed):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
        
        return None
    
    async def _summarize_result(self, raw_outputs: list) -> str:
        """Use the LLM to turn raw task output into a conversational answer.
        
        Takes the user's last question + raw stdout/summary and produces
        a natural, direct response. Falls back to brief formatting if
        no LLM is available.
        """
        # Build context from raw outputs
        output_text = ""
        for kind, content in raw_outputs:
            if kind == "research":
                output_text += f"Research findings:\n{content}\n\n"
            elif kind == "code":
                output_text += f"Code execution output:\n{content}\n\n"
            elif kind == "code_only":
                output_text += f"Generated code (no output):\n{content[:500]}\n\n"
            elif kind == "preview":
                output_text += f"Deployment: {content}\n\n"
            elif kind == "files":
                output_text += f"{content}\n\n"
        
        # Find the user's original question from conversation history
        user_question = ""
        for msg in reversed(self._conversation_history):
            if msg.get("role") == "user":
                user_question = msg.get("content", "")
                break
        
        if self.llm_provider and user_question:
            try:
                response = await self.llm_provider.chat_complete(
                    messages=[
                        {"role": "system", "content": (
                            "You are summarizing task results for the user. "
                            "Multiple brains may have contributed (research + code execution). "
                            "Give a direct, accurate, comprehensive answer.\n\n"
                            "RULES:\n"
                            "- Include key findings from BOTH research AND code output when both exist\n"
                            "- For numerical results (benchmarks, timings), use exact numbers from code output\n"
                            "- Research provides context and analysis; code provides measurements — present both\n"
                            "- Be concise (3-5 sentences)\n"
                            "- Don't show raw code or describe the process\n"
                            "- Start with the main answer, then add supporting details\n"
                            "- If output was truncated or incomplete, say so — don't fabricate results\n"
                            "- NEVER invent URLs, domains, or deployment links. Only mention a URL if one appears in the task output\n"
                            "- If a preview_url is provided in the output, use EXACTLY that URL — do not modify it\n"
                            "- If files were written but no preview is running, say the code was generated (not deployed)\n"
                            "- Mention which algorithms/items were actually tested vs what research found"
                        )},
                        {"role": "user", "content": (
                            f"User's question: {user_question}\n\n"
                            f"Task output:\n{output_text[:3000]}"
                        )},
                    ],
                    stream=False,
                )
                return response
            except Exception as e:
                print(f"[FrontBrain] LLM summarize failed: {e}")
        
        # Fallback: brief formatting without LLM
        if raw_outputs:
            kind, content = raw_outputs[0]
            if kind == "research":
                return content[:300]
            elif kind == "code":
                lines = content.split("\n")
                return lines[0] if lines else "✅ Done."
            else:
                return "✅ Done — check the workspace tab for details."
        return "✅ Done."

    async def _emit_chat_message(self, role: str, text: str) -> None:
        """Emit a chat message event on the bus for the Morphable UI."""
        await self.bus.broadcast_event(
            source=self.name,
            event_type="chat.message",
            payload={
                "role": role,
                "text": text,
            },
            priority=Priority.NORMAL,
        )
    
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
        """Route ALL task requests through the workspace orchestrator.
        
        Never sends directly to individual brains — the orchestrator
        handles decomposition, dependency management, and brain assignment.
        """
        task_type = intent.get("task_type")
        workspace = "default"  # Could be determined from context
        
        # Create task message with human-readable description for UI
        description = original_text[:60] + "..." if len(original_text) > 60 else original_text
        task_payload = {
            "type": "compound",
            "description": description,
            "user_request": original_text,
            "request": original_text,
            "timestamp": time.time()
        }
        
        # If user provided raw code in backticks, include it as context
        if "```" in original_text:
            code_start = original_text.find("```") + 3
            code_end = original_text.rfind("```")
            code = original_text[code_start:code_end].strip()
            if code.startswith("python"):
                code = code[6:].strip()
            task_payload["code"] = code
        
        # Always route through the workspace orchestrator
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
        
        return f"I'll work on that for you. I'll let you know when it's done."
    
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
        """Handle results from tasks we initiated.
        
        Instead of dumping raw stdout, uses the LLM to generate a
        conversational answer to the user's original question.
        """
        result = message.payload
        success = result.get("success", False)
        
        # Collect raw outputs and determine workspace hint
        workspace_hint = None
        raw_outputs = []  # (kind, content) tuples
        
        if success:
            if "results" in result and isinstance(result["results"], dict):
                for _sid, sub_result in result["results"].items():
                    if not isinstance(sub_result, dict):
                        continue
                    data = sub_result.get("data", sub_result)
                    if data.get("summary"):
                        raw_outputs.append(("research", data["summary"]))
                        workspace_hint = "research"
                    elif data.get("stdout", "").strip():
                        raw_outputs.append(("code", data["stdout"].strip()))
                        workspace_hint = workspace_hint or "python-dev"
                    elif data.get("generated_code"):
                        raw_outputs.append(("code_only", data["generated_code"]))
                        workspace_hint = workspace_hint or "python-dev"
                    # Capture preview URL if server started
                    if data.get("preview_port") and data.get("server_running"):
                        raw_outputs.append(("preview", f"Preview server running at https://preview.clawos.fr (port {data['preview_port']})"))
                    elif data.get("files_written"):
                        files = data.get("files_written", [])
                        raw_outputs.append(("files", f"Project files written: {', '.join(files)}"))
            elif "summary" in result:
                raw_outputs.append(("research", result["summary"]))
                workspace_hint = "research"
            elif "stdout" in result and result["stdout"].strip():
                raw_outputs.append(("code", result["stdout"].strip()))
                workspace_hint = "python-dev"
        
        # Generate conversational answer via LLM
        if success and raw_outputs:
            notification = await self._summarize_result(raw_outputs)
        elif success:
            notification = "✅ Done, but no output was produced."
        else:
            error = result.get("error", "Unknown error")
            notification = f"❌ Task failed: {error}"
        
        # Emit workspace highlight event so UI can pulse the tab
        if workspace_hint:
            await self.bus.broadcast_event(
                source=self.name,
                event_type="workspace.highlight",
                payload={"workspace": workspace_hint, "reason": "task_complete"},
                workspace=workspace_hint,
                priority=Priority.NORMAL,
            )
        
        # Send result to Morphable UI chat
        await self._emit_chat_message("assistant", notification)
        
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