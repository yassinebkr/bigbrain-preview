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
        # Sessions (web): one history per session id. The legacy
        # _conversation_history stays the default (TUI, no session).
        self._session_histories: Dict[str, List[Dict[str, str]]] = {}
        self._last_session_id: Optional[str] = None
        # Set by the stop button (chat.cancel): the current LLM stream
        # breaks at the next delta and returns what it already has.
        self._stop_requested = False

        # The soul: batch-consolidated identity memory (memory/soul.py).
        # Injected as a few lines per turn; consolidated by ONE LLM call
        # every BIGBRAIN_SOUL_TURNS user turns.
        from ..memory.soul import SoulStore, soul_enabled
        self._soul_store = SoulStore()
        self._soul_turns_since = 0
        self._soul_task = None
        self._soul_enabled = soul_enabled()
        
        # Brain registry for system prompt
        self._registered_brains: Dict[str, str] = {}
        
        # Load user preferences and context
        self._load_user_context()
    
    def register_brain(self, name: str, description: str) -> None:
        """Register a brain so the Front Brain knows how to delegate."""
        self._registered_brains[name] = description

    def _history_for(self, session_id: Optional[str]) -> List[Dict[str, str]]:
        """The conversation history of a session (default: the legacy one)."""
        if not session_id:
            return self._conversation_history
        return self._session_histories.setdefault(session_id, [])

    def request_stop(self) -> None:
        """Ask the current LLM stream to stop at the next delta.

        The partial reply is kept: the stream loop breaks and the caller
        broadcasts chat.done with whatever was already emitted.
        """
        self._stop_requested = True
    
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
    
    def _hydrate_session_history(self, session_id: Optional[str], messages: Any) -> None:
        """Restore the exact persisted session window after restarts or tab changes."""
        if not session_id or not isinstance(messages, list):
            return
        normalized = []
        for item in messages[-20:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                normalized.append({"role": role, "content": content})
        self._history_for(session_id)[:] = normalized

    async def handle_user_input(self, input_text: str, input_type: str = "text",
                                session_id: Optional[str] = None,
                                llm_content: Any = None) -> str:
        """
        Process user input and return response.

        When a real LLM is available, uses it for all responses.
        Falls back to pattern-matching + mock when no LLM configured.

        Args:
            input_text: User's input text
            input_type: Type of input ("text", "voice", "command")
            session_id: Web session this turn belongs to (None = default)

        Returns:
            Response text for the user
        """
        self.focus_manager.mark_user_activity()
        self._stop_requested = False
        self._last_session_id = session_id
        history = self._history_for(session_id)

        # Store conversation turn
        history.append({"role": "user", "content": input_text})
        self.memory.store_conversation_turn("user", input_text, {
            "type": input_type,
            "session_id": session_id,
            "conversation_id": self._current_conversation_id
        })
        # Soul: count user turns; every N turns a background task
        # consolidates the recent transcript once (batch, not per-turn).
        self._soul_tick()
        
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
            response = await self._llm_respond(
                input_text, session_id=session_id, llm_content=llm_content)
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
        history.append({"role": "assistant", "content": response})
        self.memory.store_conversation_turn("assistant", response, {
            "conversation_id": self._current_conversation_id
        })
        
        return response
    
    def _soul_tick(self) -> None:
        """One user turn counted; trigger batch consolidation every N."""
        from ..memory.soul import soul_turn_interval
        if not self._soul_enabled or not self.llm_provider:
            return
        self._soul_turns_since += 1
        if self._soul_turns_since < soul_turn_interval():
            return
        self._soul_turns_since = 0
        if self._soul_task and not self._soul_task.done():
            return  # a consolidation is still running
        import asyncio
        self._soul_task = asyncio.create_task(self._consolidate_soul())

    async def _consolidate_soul(self) -> None:
        """ONE LLM call distilling recent turns into the updated soul."""
        from ..memory.soul import (SOUL_PROMPT, collect_recent_transcript)
        try:
            transcript = collect_recent_transcript(self._soul_store.updated_at)
            if not transcript:
                return
            excerpt = "\n".join(
                f"{role}: {text[:300]}" for role, text, _ in transcript[-60:])
            previous = self._soul_store.summary or "(none yet)"
            response = await self.llm_provider.chat_complete(
                messages=[
                    {"role": "system", "content": SOUL_PROMPT},
                    {"role": "user", "content": (
                        f"Previous soul:\n{previous}\n\n"
                        f"Recent transcript:\n{excerpt[:6000]}")},
                ],
                stream=False,
            )
            summary = str(response or "").strip()
            if summary:
                self._soul_store.save(summary)
        except Exception as e:
            # Consolidation is best-effort: never break a conversation.
            print(f"[FrontBrain] soul consolidation failed: {e}")

    def _recall_relevant(self, query: str,
                         history: List[Dict[str, str]]) -> List[str]:
        """Persistent-memory recall for one turn. Frugal and honest:

        - top-4 results, each capped, deduplicated against the live
          context window and against each other,
        - retrieval costs zero LLM tokens (ChromaDB embedding search),
        - no ChromaDB → no recall (no fake keyword matching),
        - kill switch: BIGBRAIN_RECALL=0.
        """
        import os
        if os.environ.get("BIGBRAIN_RECALL", "1") == "0":
            return []
        text = (query or "").strip()
        if not text:
            return []
        try:
            # Direct persistent query (both scopes): MemoryManager.recall
            # forces a workspace filter that would exclude global
            # (cross-project) memories — the personal ones matter most.
            results = self.memory.persistent.query(text, limit=4)
        except Exception:
            return []

        # The live window already carries these turns — never re-inject.
        window_heads = set()
        for msg in history:
            content = (msg.get("content") or "").strip()
            if content:
                window_heads.add(content[:80].lower())

        recalled: List[str] = []
        seen: set = set()
        for r in results:
            content = (r.get("content") or "").strip()
            metadata = r.get("metadata") or {}
            role = metadata.get("role")
            if isinstance(role, str) and content.lower().startswith(f"{role}: "):
                content = content[len(role) + 2:].strip()
            head = content[:80].lower()
            if not content or head in window_heads or head in seen:
                continue
            seen.add(head)
            recalled.append(content[:200])
        return recalled

    def _current_project(self) -> str | None:
        """The selected working project, if any (and if web is loaded)."""
        try:
            from ..web.fs_api import get_current_project

            return get_current_project()
        except Exception:
            return None

    async def _llm_respond(self, input_text: str,
                           session_id: Optional[str] = None,
                           llm_content: Any = None) -> str:
        """Generate response using the real LLM with full conversation context.

        The LLM will return either plain text (conversation) or delegation
        JSON (task request). The caller handles both cases. The history
        is the SESSION's history — switching conversations must not leak
        context across sessions.
        """
        # Build system prompt with current context
        focus_status = self.focus_manager.get_focus_status()
        system_prompt = self._build_system_prompt(focus_status)

        messages = [{"role": "system", "content": system_prompt}]

        # The soul: a few consolidated lines about the user — the outcome
        # of openclaw's soul, at a batch cost instead of a per-turn cost.
        if self._soul_enabled and self._soul_store.summary:
            messages.append({"role": "system", "content": (
                "What you remember about this user (consolidated long-term "
                "memory — use silently, never mention this block):\n"
                + self._soul_store.summary)})

        # Project context: the chat knows which project the user works in;
        # generated files land there (the pool's work_dir follows it too).
        project = self._current_project()
        if project:
            messages.append({"role": "system", "content": (
                f"Workspace selection: '{project}' (directory '{project}/'). "
                "This is navigation context, NOT an instruction to reuse this "
                "project for every request. Decide from the user's current "
                "request and this conversation whether they want to modify "
                "the existing project or create a different one. For a NEW "
                "project, preserve the requested subject, choose a distinct "
                "descriptive project name and use its own sibling directory; "
                "never inherit the selected project's name or requirements. "
                "Only edits to the existing project belong in this directory."
            )})
        else:
            messages.append({"role": "system", "content": (
                "No project selected. Generated files land in the 'sandbox' "
                "scratch project. For anything beyond quick experiments, "
                "suggest the user create or select a project."
            )})
        
        # Add conversation history (keep last 20 turns for context)
        history = self._history_for(session_id)[-20:]
        messages.extend(history)
        if llm_content is not None and messages:
            # Persist text only; image bytes exist only in this provider call.
            messages[-1] = {"role": "user", "content": llm_content}
        
        # Semantic recall (memory phase): a handful of PERSISTENT memories
        # relevant to this turn — the "you sent me this months ago" magic.
        # Frugal by design: top-4 capped lines, deduplicated against the
        # live window, zero LLM tokens spent on retrieval.
        recalled = self._recall_relevant(input_text, history)
        if recalled:
            messages.insert(1, {"role": "system", "content": (
                "Older memories that may be relevant to this conversation:\n"
                + "\n".join(f"- {line}" for line in recalled)
                + "\nUse them silently if useful; do not mention them "
                  "unless the user brings them up."
            )})
        
        try:
            # STREAMING: consume the provider's delta stream and broadcast
            # each chunk as chat.delta — the UI shows the reply live.
            # Gate: if the model starts emitting delegation JSON, stop
            # streaming (raw JSON has no business in the chat).
            result = await self.llm_provider.chat_complete(
                messages=messages,
                stream=True,
            )
            if hasattr(result, "__aiter__"):
                parts: list[str] = []
                emitting = False
                async for delta in result:
                    if self._stop_requested:
                        break
                    if not delta:
                        continue
                    parts.append(delta)
                    if not emitting:
                        # Decide once, from the first non-space content.
                        head = "".join(parts).lstrip()[:8]
                        looks_like_json = head.startswith("{") or head.startswith("```json")
                        if looks_like_json:
                            emitting = False
                            continue
                        emitting = True
                    if emitting:
                        await self._emit_chat_delta(delta, session_id=session_id)
                response = "".join(parts)
                self._last_response_streamed = emitting
            else:
                response = str(result)
                self._last_response_streamed = False
            return response
        except Exception as e:
            self._last_response_streamed = False
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

ROUTED DELEGATION (preferred when the request matches ONE known brain capability): use "route" instead of "task". The orchestrator executes it EXACTLY as given, without re-planning:
{{"reply": "brief natural acknowledgment", "route": {{"brain": "<brain>", "payload": {{...}}}}}}

Routable brains and payloads:
- taskboard — add/create a task or todo on the user's persistent board. Payload: {{"type": "board_task", "title": "<short task title>", "description": "<optional details>", "status": "todo"}}. Use status "todo" unless the user explicitly asks for another status.
- researcher — research / web search. Payload: {{"type": "research", "query": "<self-contained search query>"}}
- python_brain — run an existing workspace file. Payload: {{"type": "run_file", "file": "<file path>"}}
- web_app_brain — run an existing verified web project. Payload: {{"type": "run_web_project", "project_name": "<project path>"}}

Use "route" ONLY for these direct single actions. For code generation, multi-step work, or anything combining several actions, use the generic "task" format.

IMPORTANT: Send the ENTIRE request as ONE task. Do NOT break it into subtasks yourself.
The orchestrator will decompose it into subtasks with proper dependencies.
For example, "research sorting algorithms and benchmark them" is ONE task — the orchestrator
will figure out that research must complete before benchmarking can start.

CONVERSATION: For greetings, questions, status, opinions — just respond naturally as plain text (no JSON).

RULES:
- NEVER write code yourself. NEVER. PythonBrain handles Python and WebAppBrain handles browser applications.
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

User: "ajoute une tâche à la taskboard : mettre à jour le README de near_agi"
You: {{"reply": "Ajouté à ta taskboard.", "route": {{"brain": "taskboard", "payload": {{"type": "board_task", "title": "Mettre à jour le README de near_agi", "status": "todo"}}}}}}

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
        text = message.payload.get("text", "").strip()
        session_id = message.payload.get("session_id")
        self._hydrate_session_history(
            session_id, message.payload.get("conversation_history"))

        # Attachments (uploaded via POST /api/attachments): record each
        # file in persistent memory — recall makes it findable months
        # later. The LLM gets an honest note (name/type only — no vision).
        attachments = [
            a for a in (message.payload.get("attachments") or [])
            if isinstance(a, dict) and a.get("name")
        ]
        if not text and not attachments:
            return

        llm_content = None
        if attachments:
            self._remember_attachments(attachments, session_id)
            text, llm_content, vision_error = self._prepare_attachments(text, attachments)
            if vision_error:
                history = self._history_for(session_id)
                history.append({"role": "user", "content": text})
                history.append({"role": "assistant", "content": vision_error})
                self.memory.store_conversation_turn(
                    "user", text,
                    {"type": "web", "session_id": session_id})
                self.memory.store_conversation_turn(
                    "assistant", vision_error, {"session_id": session_id})
                await self._emit_chat_message("assistant", vision_error)
                return

        try:
            # Process through the normal input pipeline
            response = await self.handle_user_input(
                text, input_type="web", session_id=session_id,
                llm_content=llm_content)
            if self._stop_requested:
                await self._emit_chat_done("")
                return
            
            # Try to parse as delegation JSON
            parsed = self._try_parse_delegation(response)
            
            # Routed delegation (tool-call): the Front Brain picked a
            # brain + payload itself. Forward it verbatim — the orchestrator
            # validates the brain name against its registry/pools and
            # falls back to normal planning for unknown names.
            route = parsed.get("route") if isinstance(parsed, dict) else None
            route_brain = route.get("brain") if isinstance(route, dict) else None
            route_payload = route.get("payload") if isinstance(route, dict) else None
            route_valid = (
                isinstance(route_brain, str)
                and bool(route_brain)
                and isinstance(route_payload, dict)
                and bool(route_payload.get("type"))
            )
            
            if parsed and route_valid:
                reply_text = parsed.get("reply", "Working on it...")
                await self._emit_chat_message("assistant", reply_text)
                await self._emit_task_routing(text)
                
                ws = "default"  # Always route to the single orchestrator
                task_data = {
                    **route_payload,
                    "brain": route_brain,
                    "reply_to_ui": True,
                    "user_request": text,
                    "session_id": session_id,
                    "project_path": self._current_project(),
                }
                await self.bus.send_task(
                    source=self.name,
                    target=f"orchestrator_{ws}",
                    task_data=task_data,
                    priority=Priority.NORMAL,
                )
            elif parsed and "task" in parsed:
                # Front Brain wants to delegate — send the reply part to chat
                reply_text = parsed.get("reply", "Working on it...")
                await self._emit_chat_message("assistant", reply_text)
                await self._emit_task_routing(str(parsed["task"]))
                
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
                        "session_id": session_id,
                        "project_path": self._current_project(),
                    },
                    priority=Priority.NORMAL,
                )
            elif parsed and "tasks" in parsed:
                # Legacy multi-task format — merge into single compound request
                reply_text = parsed.get("reply", "Working on it...")
                await self._emit_chat_message("assistant", reply_text)
                await self._emit_task_routing(text)
                
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
                        "session_id": session_id,
                        "project_path": self._current_project(),
                    },
                    priority=Priority.NORMAL,
                )
            else:
                # Plain text response — send to chat. If the reply was
                # already streamed (chat.delta), signal completion only:
                # re-sending the full text would duplicate the bubble.
                if getattr(self, "_last_response_streamed", False):
                    await self._emit_chat_done(response)
                else:
                    await self._emit_chat_message("assistant", response)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            await self._emit_chat_message("system", f"Error: {e}")
    
    def _prepare_attachments(self, text: str, attachments: list) -> tuple:
        """Build persisted text and optional OpenAI multimodal content."""
        images = [a for a in attachments
                  if str(a.get("type") or "").lower().startswith("image/")]
        other = [a for a in attachments if a not in images]
        names = ", ".join(
            f"{a.get('name')} ({a.get('type') or 'file'})"
            for a in attachments)
        display_text = text or "Please describe the attached image."

        entry = getattr(self.llm_provider, "entry", None)
        if images and not bool(getattr(entry, "vision", False)):
            stored = (f"{display_text}\n\n[attached file(s): {names} — saved on "
                      "the server; the selected model cannot see image content]")
            return stored, None, (
                "I can’t see this image with the currently selected front "
                "model. Choose a vision-capable model and try again.")

        blocks = [{"type": "text", "text": display_text}]
        if images:
            from ..llm.openai_compat_provider import image_content_block
            from ..web.attachments import read_attachment
            for image in images:
                path = read_attachment(str(image.get("id") or ""))
                if path is None:
                    stored = (f"{display_text}\n\n[attached file(s): {names} — "
                              "the image could not be read from the server]")
                    return stored, None, (
                        "I couldn’t read the attached image from storage. "
                        "Please upload it again.")
                blocks.append(image_content_block(
                    path.read_bytes(), str(image.get("type")).lower()))

        notes = []
        if images:
            notes.append("image content was sent to the vision model")
        if other:
            notes.append("non-image file content is not visible to the model")
        stored = (f"{display_text}\n\n[attached file(s): {names} — "
                  f"{'; '.join(notes)}]")
        return stored, (blocks if images else None), None

    def _remember_attachments(self, attachments: list,
                              session_id: Optional[str]) -> None:
        """One persistent memory entry per attached file (global scope).

        Never raises: persistence must not break the conversation.
        """
        for attachment in attachments:
            try:
                self.memory.persistent.store(
                    content=(f"The user shared a file: {attachment.get('name')} "
                             f"({attachment.get('type') or 'file'})"),
                    scope="global",
                    brain=self.name,
                    memory_type="attachment",
                    tags="attachment",
                    extra_metadata={
                        "attachment_id": str(attachment.get("id") or ""),
                        "session_id": session_id or "",
                    },
                )
            except Exception:
                pass

    @staticmethod
    def _try_parse_delegation(response: str) -> dict | None:
        """
        Try to parse a Front Brain response as delegation JSON.
        
        Handles:
        - {"reply": "...", "task": "single compound request"}
        - {"reply": "...", "route": {"brain": "...", "payload": {...}}}
        - Legacy format: {"reply": "...", "tasks": [...]}
        - Raw JSON, markdown-fenced JSON, JSON embedded in text
        """
        import json
        
        if not response:
            return None
        
        def _valid(parsed) -> bool:
            return (
                isinstance(parsed, dict)
                and any(k in parsed for k in ("task", "tasks", "route"))
            )
        
        # 1. Try raw JSON
        try:
            parsed = json.loads(response.strip())
            if _valid(parsed):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        
        # 2. Scan for balanced {...} candidates anywhere in the text
        #    (covers markdown fences, prose, and nested route payloads —
        #    a lazy regex stops at the first '}' and misses them).
        for start in (i for i, c in enumerate(response) if c == "{"):
            depth = 0
            for i in range(start, len(response)):
                if response[i] == "{":
                    depth += 1
                elif response[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(response[start:i + 1])
                            if _valid(parsed):
                                return parsed
                        except (json.JSONDecodeError, TypeError):
                            pass
                        break
        
        return None
    
    async def _summarize_result(self, raw_outputs: list, session_id: Optional[str] = None) -> str:
        """Use the LLM to turn raw task output into a conversational answer.
        
        Takes the user's last question + raw stdout/summary and produces
        a natural, direct response. Falls back to brief formatting if
        no LLM is available.
        """
        # Build context from raw outputs
        # Concrete execution evidence must survive even when research is
        # verbose. The old global 3k prefix could omit successful code.
        priority = {"code": 0, "files": 1, "preview": 2,
                    "action": 3, "code_only": 4, "research": 5}
        ordered_outputs = sorted(
            enumerate(raw_outputs),
            key=lambda item: (priority.get(item[1][0], 9), item[0]),
        )
        chunks = []
        per_kind_limit = {"code": 3500, "research": 1500,
                          "code_only": 800}
        for _, (kind, content) in ordered_outputs:
            content = str(content)
            limit = per_kind_limit.get(kind, 1200)
            if len(content) > limit:
                content = content[:limit] + "\n[truncated]"
            if kind == "research":
                chunks.append(f"Research findings:\n{content}")
            elif kind == "code":
                chunks.append(f"Code execution output:\n{content}")
            elif kind == "code_only":
                chunks.append(f"Generated code (no output):\n{content}")
            elif kind == "action":
                chunks.append(f"Action performed:\n{content}")
            elif kind == "preview":
                chunks.append(f"Deployment: {content}")
            elif kind == "files":
                chunks.append(content)
        output_text = "\n\n".join(chunks)
        
        # Find the user's original question from conversation history
        user_question = ""
        for msg in reversed(self._history_for(session_id or self._last_session_id)):
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
                            "- For a generated project with a preview, do not enumerate or reproduce its content; confirm completion in at most 2 sentences and tell the user to use the preview/project controls\n"
                            "- Start with the main answer, then add supporting details\n"
                            "- If output was truncated or incomplete, say so — don't fabricate results\n"
                            "- NEVER invent URLs, domains, or deployment links. Only mention a URL if one appears in the task output\n"
                            "- If a preview_url is provided in the output, use EXACTLY that URL — do not modify it\n"
                            "- If files were written but no preview is running, say the code was generated (not deployed)\n"
                            "- Mention which algorithms/items were actually tested vs what research found\n"
                            "- Report ONLY actions the task output explicitly confirms. NEVER claim a task was created, a board item was added, a file was saved, or a message was sent unless the output says so\n"
                            "- Do not invent file names, storage locations, or record formats not shown in the output (e.g. where or how data was saved)\n"
                            "- If the output does NOT accomplish what the user asked, say honestly what actually happened instead of pretending success"
                        )},
                        {"role": "user", "content": (
                            f"User's question: {user_question}\n\n"
                            f"Task output:\n{output_text[:7000]}"
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

    async def _emit_chat_delta(self, delta: str, session_id: Optional[str] = None) -> None:
        """Stream one text chunk to the UI (chat.delta events)."""
        await self.bus.broadcast_event(
            source=self.name,
            event_type="chat.delta",
            payload={"delta": delta, "session_id": session_id or self._last_session_id},
            priority=Priority.NORMAL,
        )

    async def _emit_chat_done(self, text: str = "") -> None:
        """End of a streamed reply: the UI finalizes the streaming bubble
        WITHOUT re-adding the text as a new message (no duplicate)."""
        await self.bus.broadcast_event(
            source=self.name,
            event_type="chat.done",
            payload={"text": text, "session_id": self._last_session_id},
            priority=Priority.NORMAL,
        )

    async def _emit_chat_message(self, role: str, text: str, session_id: Optional[str] = None) -> None:
        """Emit a chat message event on the bus for the Morphable UI."""
        await self.bus.broadcast_event(
            source=self.name,
            event_type="chat.message",
            payload={
                "role": role,
                "text": text,
                "session_id": session_id or self._last_session_id,
            },
            priority=Priority.NORMAL,
        )

    async def _emit_task_routing(self, description: str) -> None:
        """Keep the initiating conversation visibly busy during planning."""
        await self.bus.broadcast_event(
            source=self.name,
            event_type="task.routing",
            payload={
                "description": description[:140],
                "session_id": self._last_session_id,
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
                    elif data.get("message"):
                        # Structured action results (e.g. the taskboard
                        # brain): the action's own confirmation IS the
                        # output the summarizer must relay.
                        raw_outputs.append(("action", data["message"]))
                    # Capture preview URL if server started
                    if data.get("preview_url") and data.get("server_running"):
                        raw_outputs.append(("preview", f"Preview ready: {data['preview_url']}"))
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
        preview_output = next((str(content) for kind, content in raw_outputs
                               if kind == "preview"), None)
        files_output = next((str(content) for kind, content in raw_outputs
                             if kind == "files"), None)
        if success and preview_output:
            # Project cards own the rich result UI. Keep chat deterministic
            # and compact instead of asking an LLM to retell the application.
            notification = "✅ Projet web terminé. Utilise l’aperçu ou les contrôles du projet ci-dessous."
        elif success and files_output and not any(kind in {"code", "research", "action"}
                                                   for kind, _ in raw_outputs):
            notification = "✅ Fichiers du projet générés. Ouvre le projet pour les consulter."
        elif success and raw_outputs:
            notification = await self._summarize_result(raw_outputs, session_id=result.get("session_id"))
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
        await self._emit_chat_message("assistant", notification, session_id=result.get("session_id"))
        
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
