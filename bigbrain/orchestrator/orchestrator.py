"""WorkspaceOrchestrator - Event-driven task management for BigBrain."""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from ..bus.bus import MessageBus
from ..bus.message import BusMessage, MessageType, Priority
from ..bus.participant import BusParticipant
from .execution_modes import BrainExecutionConfig, ExecutionMode

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Status of a task or subtask."""
    PENDING = "pending"        # Waiting for dependencies
    READY = "ready"           # Dependencies satisfied, ready to execute
    RUNNING = "running"       # Currently being executed by a brain
    COMPLETE = "complete"     # Successfully finished
    FAILED = "failed"         # Failed with error
    CANCELLED = "cancelled"   # Cancelled by user or system


@dataclass
class SubTask:
    """Individual subtask within a larger task plan."""
    id: str
    description: str
    brain_target: str             # Which brain should handle this
    payload: Dict[str, Any]       # Task-specific data
    dependencies: Set[str] = field(default_factory=set)  # SubTask IDs this depends on
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    assigned_brain: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None


@dataclass 
class TaskPlan:
    """
    Complete task plan with subtasks and dependencies.
    
    Represents the decomposition of a high-level task into executable
    subtasks with dependency relationships. Supports ReWOO-style
    variable references between subtasks.
    """
    id: str
    original_task: BusMessage
    subtasks: List[SubTask] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    def get_ready_subtasks(self) -> List[SubTask]:
        """Get subtasks that are ready to execute (dependencies satisfied)."""
        ready = []
        completed_ids = {st.id for st in self.subtasks if st.status == TaskStatus.COMPLETE}
        
        for subtask in self.subtasks:
            if (subtask.status == TaskStatus.PENDING and 
                subtask.dependencies.issubset(completed_ids)):
                ready.append(subtask)
        
        return ready
    
    def is_complete(self) -> bool:
        """Check if all subtasks are complete."""
        return all(st.status in (TaskStatus.COMPLETE, TaskStatus.CANCELLED) 
                  for st in self.subtasks)
    
    def is_failed(self) -> bool:
        """Check if any subtask failed."""
        return any(st.status == TaskStatus.FAILED for st in self.subtasks)
    
    def get_subtask(self, subtask_id: str) -> Optional[SubTask]:
        """Get subtask by ID."""
        for subtask in self.subtasks:
            if subtask.id == subtask_id:
                return subtask
        return None
    
    def get_results(self) -> Dict[str, Any]:
        """Get results from all completed subtasks."""
        results = {}
        for subtask in self.subtasks:
            if subtask.status == TaskStatus.COMPLETE and subtask.result:
                results[subtask.id] = subtask.result
        return results


class WorkspaceOrchestrator(BusParticipant):
    """
    Event-driven orchestrator for a specific workspace.
    
    Inherits bus subscribe/unsubscribe plumbing from BusParticipant
    and adds orchestrator-specific task management.
    
    Manages task decomposition, routing, and execution tracking within
    one workspace domain (e.g. webdev, research, electronics).
    
    Key Features:
    - Event-driven message handling (never blocking)
    - Task decomposition with dependency management
    - Brain registration and load balancing
    - Real-time state streaming
    - Graceful task cancellation
    
    Message Flow:
    - Receives TASK from Front Brain
    - Decomposes into subtasks with dependencies  
    - Dispatches ready subtasks to appropriate brains
    - Tracks progress and updates task state
    - Sends RESULT back when complete
    """
    
    # System prompt for complexity assessment
    COMPLEXITY_SYSTEM_PROMPT = """You are a project complexity assessor. Given a user request, determine if it needs:
1. "script" — a single Python file can handle it (utility, algorithm, simple tool)
2. "project" — multiple files needed (backend+frontend, library+tests, multi-concern app)

Also determine if research is needed before coding (new APIs, best practices, state of the art).

Respond with ONLY a JSON object, no explanation:
{{"mode": "script"|"project", "needs_research": true|false, "research_queries": ["query1"], "reason": "brief reason"}}

Examples:
- "write a fibonacci function" → {{"mode": "script", "needs_research": false, "research_queries": [], "reason": "single algorithm"}}
- "build a chat app with auth and websockets" → {{"mode": "project", "needs_research": true, "research_queries": ["python websocket server best practices 2026", "lightweight python auth JWT"], "reason": "multiple concerns: backend, auth, websockets, frontend"}}
- "create a REST API with database" → {{"mode": "project", "needs_research": false, "research_queries": [], "reason": "multiple files: models, routes, app setup"}}"""

    # System prompt for project file planning (only used in project mode)
    PROJECT_PLANNER_PROMPT = """You are a software architect. Given a user request, plan the file structure for the project.

Rules:
- Each file = one concern. Don't cram everything into one file.
- List dependencies between files (which file needs which other file's exports).
- Use Python standard library only (no numpy, pandas, matplotlib, etc.).
- Keep it practical — 3-8 files for most projects. Don't over-engineer.
- Include a main entry point file that wires everything together.
- For web apps: separate backend, frontend (HTML), and data layer.

Respond with ONLY a JSON object:
{{
  "project_name": "short-name",
  "files": [
    {{"path": "models.py", "purpose": "Database models for users and messages", "exports": ["User", "Message", "init_db"], "dependencies": []}},
    {{"path": "auth.py", "purpose": "JWT authentication middleware", "exports": ["create_token", "verify_token", "auth_required"], "dependencies": ["models.py"]}},
    {{"path": "app.py", "purpose": "FastAPI/Flask routes and WebSocket handlers", "exports": [], "dependencies": ["models.py", "auth.py"]}},
    {{"path": "templates/index.html", "purpose": "Frontend UI", "exports": [], "dependencies": []}},
    {{"path": "main.py", "purpose": "Entry point — starts the server", "exports": [], "dependencies": ["app.py"]}}
  ]
}}"""

    # System prompt for simple single-task planning
    SIMPLE_PLANNER_PROMPT = """You are a task planner for a multi-brain AI system.

Your job: decompose a user's request into concrete subtasks, each assigned to the right brain.

Available brains (use exactly these names as brain_target):
{brain_list}

CRITICAL RULES:
- Each subtask has: id, description, brain_target, payload (with "type" and "user_request"), dependencies
- Use dependencies to enforce ordering when one subtask needs another's output
- For simple code tasks: 1 subtask to python_brain
- The "type" field in payload should be "generate_and_execute" for code tasks, "research" for research tasks
- If research is needed, add a researcher subtask BEFORE the coding subtask with a dependency

Respond with ONLY a JSON array. No explanation, no markdown fences.

Example — single task:
[{{"id": "s1", "description": "Generate fibonacci code", "brain_target": "python_brain", "payload": {{"type": "generate_and_execute", "user_request": "write a fibonacci function"}}, "dependencies": []}}]

Example — research then code:
[{{"id": "s1", "description": "Research WebSocket libraries", "brain_target": "researcher", "payload": {{"type": "research", "query": "python websocket server libraries comparison 2026"}}, "dependencies": []}}, {{"id": "s2", "description": "Build WebSocket server", "brain_target": "python_brain", "payload": {{"type": "generate_and_execute", "user_request": "build a websocket chat server", "context_ref": "#s1"}}, "dependencies": ["s1"]}}]"""

    def __init__(self, workspace: str, bus: MessageBus, llm_provider=None,
                 planner_model: str = None):
        """
        Initialize workspace orchestrator.
        
        Args:
            workspace: Workspace name this orchestrator manages
            bus: MessageBus for communication
            llm_provider: LLM provider for task planning (Opus-class recommended)
            planner_model: Model override for planning calls
        """
        super().__init__(f"orchestrator_{workspace}", bus)
        self.workspace = workspace
        self.llm_provider = llm_provider
        self.planner_model = planner_model
        
        # Task tracking
        self.task_plans: Dict[str, TaskPlan] = {}
        self.active_subtasks: Dict[str, str] = {}  # subtask_id -> plan_id
        
        # Brain registry
        self.registered_brains: Dict[str, Dict[str, Any]] = {}
        self.brain_load: Dict[str, int] = {}  # brain -> active task count
        
        # Execution mode configs per brain
        self.execution_configs: Dict[str, BrainExecutionConfig] = {}
    
    async def start(self) -> None:
        """Start the orchestrator and register with message bus."""
        if self._running:
            raise RuntimeError(f"Orchestrator {self.name} is already running")
        
        self._running = True
        
        # Subscribe to messages
        self.bus.subscribe(self.name, self.handle_message)
        
        # Announce orchestrator availability
        await self.bus.broadcast_event(
            source=self.name,
            event_type="orchestrator.started",
            payload={"workspace": self.workspace},
            workspace=self.workspace,
            priority=Priority.LOW
        )
    
    async def stop(self) -> None:
        """Stop orchestrator and cleanup."""
        if not self._running:
            return
        
        self._running = False
        
        # Cancel all active tasks
        for plan in self.task_plans.values():
            if plan.status == TaskStatus.RUNNING:
                await self._cancel_task(plan.id, "soft")
        
        # Unregister from bus
        self.bus.unsubscribe(self.name, self.handle_message)
        
        # Cleanup state
        self.task_plans.clear()
        self.active_subtasks.clear()
    
    async def handle_message(self, message: BusMessage) -> None:
        """
        Event-driven message handler.
        
        Processes different message types and updates task state accordingly.
        Never blocks - all operations are async and return quickly.
        """
        # Skip our own messages to prevent infinite broadcast loops
        if message.source == self.name:
            return
        
        try:
            if message.type == MessageType.TASK:
                await self._handle_task_request(message)
            
            elif message.type == MessageType.RESULT:
                await self._handle_task_result(message)
            
            elif message.type == MessageType.CANCEL:
                await self._handle_cancel_request(message)
            
            elif message.type == MessageType.QUERY:
                await self._handle_query(message)
            
            # Forward progress/state events
            elif message.type in (MessageType.PROGRESS, MessageType.EVENT):
                await self._forward_brain_event(message)
        
        except Exception as e:
            await self.bus.broadcast_event(
                source=self.name,
                event_type="orchestrator.error",
                payload={
                    "error": str(e),
                    "message_id": message.id,
                    "workspace": self.workspace
                },
                workspace=self.workspace,
                priority=Priority.HIGH
            )
    
    async def _handle_task_request(self, message: BusMessage) -> None:
        """Handle incoming task requests."""
        print(f"[ORCH] _handle_task_request from {message.source} type={message.payload.get('type','?')}")
        task_data = message.payload
        
        # Create task plan
        plan = await self._create_task_plan(message)
        self.task_plans[plan.id] = plan
        
        # Announce task received — include description for UI
        task_desc = message.payload.get("description", "") if message.payload else ""
        await self.bus.broadcast_event(
            source=self.name,
            event_type="task.received",
            payload={
                "task_id": plan.id,
                "description": task_desc or f"{len(plan.subtasks)} subtask(s)",
                "workspace": self.workspace,
                "subtasks_count": len(plan.subtasks)
            },
            workspace=self.workspace,
            priority=Priority.NORMAL
        )
        
        # Start executing ready subtasks
        plan.status = TaskStatus.RUNNING
        await self._execute_ready_subtasks(plan)
    
    async def _create_task_plan(self, message: BusMessage) -> TaskPlan:
        """
        Decompose a task into executable subtasks using LLM planning.
        
        Planning pipeline:
        1. Assess complexity (script vs project, research needed?)
        2. If project mode → plan file structure → build DAG
        3. If script mode → simple single-task routing
        4. Falls back to deterministic routing if no LLM available
        """
        plan_id = str(uuid.uuid4())
        plan = TaskPlan(id=plan_id, original_task=message)
        
        task_data = message.payload
        user_request = (
            task_data.get("user_request")
            or task_data.get("request")
            or task_data.get("query")
            or task_data.get("description")
            or str(task_data)
        )
        
        # Try LLM-powered planning with complexity assessment
        if self.llm_provider:
            try:
                # Step 1: Assess complexity
                assessment = await self._assess_complexity(user_request)
                logger.info("Complexity assessment: mode=%s, research=%s, reason=%s",
                           assessment.get("mode"), assessment.get("needs_research"),
                           assessment.get("reason", ""))
                
                await self.bus.broadcast_event(
                    source=self.name,
                    event_type="planning.assessment",
                    payload={"assessment": assessment, "request": user_request[:100]},
                    workspace=self.workspace,
                    priority=Priority.LOW
                )
                
                mode = assessment.get("mode", "script")
                needs_research = assessment.get("needs_research", False)
                research_queries = assessment.get("research_queries", [])
                
                if mode == "project":
                    # Step 2a: Project mode — plan file structure, build DAG
                    subtasks = await self._plan_project(plan_id, user_request, 
                                                         needs_research, research_queries)
                else:
                    # Step 2b: Script mode — simple decomposition
                    subtasks = await self._llm_decompose(plan_id, user_request, 
                                                          task_data, needs_research,
                                                          research_queries)
                
                if subtasks:
                    plan.subtasks = subtasks
                    return plan
                    
            except Exception as e:
                logger.warning("LLM planning failed, falling back to simple routing: %s", e)
        
        # Fallback: simple deterministic routing
        plan.subtasks = self._simple_decompose(plan_id, task_data)
        return plan
    
    async def _assess_complexity(self, user_request: str) -> dict:
        """Assess task complexity: script vs project, research needed."""
        messages = [
            {"role": "system", "content": self.COMPLEXITY_SYSTEM_PROMPT},
            {"role": "user", "content": user_request},
        ]
        
        raw = await self.llm_provider.chat_complete(
            messages=messages,
            model=self.planner_model,
            stream=False,
            max_tokens=256,
            temperature=0.1,
        )
        
        # Parse JSON response
        text = raw.strip()
        if text.startswith("```"):
            first_nl = text.index("\n")
            text = text[first_nl + 1:]
            if "```" in text:
                text = text[:text.rindex("```")]
            text = text.strip()
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in text
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
            # Default: simple script, no research
            return {"mode": "script", "needs_research": False, "research_queries": [], "reason": "parse error"}
    
    async def _plan_project(self, plan_id: str, user_request: str,
                            needs_research: bool, research_queries: list) -> List[SubTask]:
        """Plan a multi-file project and build a task DAG.
        
        Returns subtasks ordered by dependency:
        1. Research tasks (if needed)
        2. File tasks (ordered by dependency DAG)
        3. Assembler task (wires everything together + runs)
        """
        subtasks = []
        task_idx = 0
        research_dep_ids = []
        
        # Step 1: Add research subtasks if needed
        if needs_research and research_queries:
            for query in research_queries[:3]:  # Cap at 3 research queries
                sid = f"{plan_id}_s{task_idx}"
                subtasks.append(SubTask(
                    id=sid,
                    description=f"Research: {query[:80]}",
                    brain_target="researcher",
                    payload={"type": "research", "query": query},
                    dependencies=set(),
                ))
                research_dep_ids.append(sid)
                task_idx += 1
        
        # Step 2: Plan file structure
        messages = [
            {"role": "system", "content": self.PROJECT_PLANNER_PROMPT},
            {"role": "user", "content": user_request},
        ]
        
        raw = await self.llm_provider.chat_complete(
            messages=messages,
            model=self.planner_model,
            stream=False,
            max_tokens=1024,
            temperature=0.2,
        )
        
        file_plan = self._parse_plan_json_object(raw)
        files = file_plan.get("files", [])
        project_name = file_plan.get("project_name", "project")
        
        if not files:
            raise ValueError("Project planner returned no files")
        
        logger.info("Project plan: %s — %d files", project_name, len(files))
        
        await self.bus.broadcast_event(
            source=self.name,
            event_type="planning.project_structure",
            payload={
                "project_name": project_name,
                "files": [f.get("path") for f in files],
                "total_files": len(files),
            },
            workspace=self.workspace,
            priority=Priority.NORMAL
        )
        
        # Step 3: Build subtask DAG from file dependencies
        # Map file paths to subtask IDs
        file_to_sid = {}
        for f in files:
            sid = f"{plan_id}_s{task_idx}"
            file_to_sid[f["path"]] = sid
            task_idx += 1
        
        # Create file-writing subtasks with proper dependencies
        for f in files:
            sid = file_to_sid[f["path"]]
            
            # Resolve dependencies: file deps + research deps
            deps = set(research_dep_ids)  # All file tasks wait for research
            for dep_path in f.get("dependencies", []):
                dep_sid = file_to_sid.get(dep_path)
                if dep_sid:
                    deps.add(dep_sid)
            
            subtasks.append(SubTask(
                id=sid,
                description=f"Write {f['path']}: {f.get('purpose', '')}",
                brain_target="python_brain",
                payload={
                    "type": "write_project_file",
                    "user_request": user_request,
                    "project_name": project_name,
                    "file_path": f["path"],
                    "purpose": f.get("purpose", ""),
                    "exports": f.get("exports", []),
                    "dependencies": f.get("dependencies", []),
                    "all_files": files,  # Full file tree for context
                },
                dependencies=deps,
            ))
        
        # Step 4: Add assembler task — wires everything together and runs
        all_file_sids = set(file_to_sid.values())
        assembler_sid = f"{plan_id}_s{task_idx}"
        subtasks.append(SubTask(
            id=assembler_sid,
            description=f"Assemble and run {project_name}",
            brain_target="python_brain",
            payload={
                "type": "assemble_and_run",
                "user_request": user_request,
                "project_name": project_name,
                "all_files": files,
            },
            dependencies=all_file_sids,
        ))
        
        return subtasks
    
    def _parse_plan_json_object(self, raw: str) -> dict:
        """Parse LLM output as a JSON object (for project plan)."""
        text = raw.strip()
        if text.startswith("```"):
            first_nl = text.index("\n")
            text = text[first_nl + 1:]
            if "```" in text:
                text = text[:text.rindex("```")]
            text = text.strip()
        
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
        
        start = text.find("{")
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break
        
        raise ValueError(f"Could not parse project plan JSON: {text[:200]}")
    
    async def _llm_decompose(self, plan_id: str, user_request: str,
                             task_data: dict, needs_research: bool = False,
                             research_queries: list = None) -> List[SubTask]:
        """Use LLM to decompose a task into subtasks with dependencies."""
        # Build brain list for the system prompt
        brain_descriptions = []
        for name, caps in self.registered_brains.items():
            desc = caps.get("description", name)
            brain_descriptions.append(f"- {name}: {desc}")
        
        if not brain_descriptions:
            brain_descriptions = [
                "- python_brain: Generates and executes Python code",
                "- researcher: Researches topics, gathers information, analyzes data",
            ]
        
        brain_list = "\n".join(brain_descriptions)
        system = self.SIMPLE_PLANNER_PROMPT.format(brain_list=brain_list)
        
        # If complexity assessment says research is needed, add hint
        if needs_research and research_queries:
            research_hint = "\n\nIMPORTANT: This task needs research first. Add researcher subtask(s) for: " + ", ".join(research_queries[:3])
            user_request = user_request + research_hint
        
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_request},
        ]
        
        # Call planner LLM (non-streaming — we need the full JSON)
        raw = await self.llm_provider.chat_complete(
            messages=messages,
            model=self.planner_model,
            stream=False,
            max_tokens=1024,
            temperature=0.3,  # Low temp for structured planning
        )
        
        # Parse JSON response
        subtask_defs = self._parse_plan_json(raw)
        
        # Convert to SubTask objects
        subtasks = []
        for sd in subtask_defs:
            sid = sd.get("id", f"{plan_id}_{len(subtasks)}")
            # Prefix subtask IDs with plan_id for global uniqueness
            full_id = f"{plan_id}_{sid}"
            
            deps = set()
            for dep in sd.get("dependencies", []):
                deps.add(f"{plan_id}_{dep}")
            
            subtask = SubTask(
                id=full_id,
                description=sd.get("description", ""),
                brain_target=sd.get("brain_target", "python_brain"),
                payload=sd.get("payload", task_data),
                dependencies=deps,
            )
            subtasks.append(subtask)
        
        if not subtasks:
            raise ValueError("LLM returned empty plan")
        
        logger.info("LLM planned %d subtasks for: %s", len(subtasks), user_request[:80])
        return subtasks

    def _parse_plan_json(self, raw: str) -> list:
        """Parse LLM planning output into a list of subtask definitions.
        
        Handles:
        - Clean JSON arrays
        - JSON wrapped in markdown code fences
        - Trailing text after the JSON
        """
        text = raw.strip()
        
        # Strip markdown code fences if present
        if text.startswith("```"):
            # Remove opening fence (possibly with language tag)
            first_newline = text.index("\n")
            text = text[first_newline + 1:]
            # Remove closing fence
            if "```" in text:
                text = text[:text.rindex("```")]
            text = text.strip()
        
        # Try direct parse
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON array in the text
        start = text.find("[")
        if start >= 0:
            # Find matching closing bracket
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "[":
                    depth += 1
                elif text[i] == "]":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break
        
        raise ValueError(f"Could not parse plan JSON from LLM output: {text[:200]}")

    def _simple_decompose(self, plan_id: str, task_data: dict) -> List[SubTask]:
        """Fallback: simple deterministic task routing (no LLM needed)."""
        task_type = task_data.get("type", "unknown")
        
        brain_map = {
            "execute_code": "python_brain",
            "generate_and_execute": "python_brain",
            "research": "researcher",
            "web_search": "researcher",
        }
        
        target = brain_map.get(task_type, self._choose_brain_for_task(task_type))
        
        return [SubTask(
            id=f"{plan_id}_s0",
            description=f"Execute {task_type} task",
            brain_target=target,
            payload=task_data,
        )]

    def _choose_brain_for_task(self, task_type: str) -> str:
        """Choose the best brain for a task type based on load balancing."""
        # Find least loaded registered brain
        if self.registered_brains:
            available = list(self.registered_brains.keys())
            return min(available, key=lambda b: self.brain_load.get(b, 0))
        return "python_brain"  # Last resort fallback
    
    async def _execute_ready_subtasks(self, plan: TaskPlan) -> None:
        """Execute all subtasks that are ready (dependencies satisfied).
        
        Respects brain capacity: only dispatches to brains that aren't at max load.
        Re-checks plan status between dispatches to avoid sending tasks after failure.
        Deferred subtasks (brain busy) are retried on next _execute_ready_subtasks call.
        """
        # Don't dispatch if plan is already complete/failed
        if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED):
            print(f"[ORCH] Skipping _execute_ready_subtasks: plan {plan.id[-8:]} is {plan.status.value}")
            return
        
        # Prevent re-entrant execution (bus delivers synchronously, so a dispatched
        # task can complete and trigger another _execute_ready_subtasks before we return)
        if getattr(plan, '_dispatching', False):
            return
        plan._dispatching = True
        
        try:
            ready_subtasks = plan.get_ready_subtasks()
            print(f"[ORCH] _execute_ready_subtasks: plan={plan.id[-8:]} status={plan.status.value} ready={len(ready_subtasks)} total={len(plan.subtasks)}")
            
            deferred = 0
            for subtask in ready_subtasks:
                # Re-check plan status — a prior dispatch may have caused a failure
                # via synchronous bus delivery (brain rejects → result → plan fails)
                if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    print(f"[ORCH] Stopping dispatch: plan {plan.id[-8:]} became {plan.status.value}")
                    break
                
                # Respect brain capacity — don't dispatch if brain is already busy
                brain = subtask.brain_target
                current_load = self.brain_load.get(brain, 0)
                max_concurrent = 1  # Brains handle 1 task at a time
                if current_load >= max_concurrent:
                    print(f"[ORCH] Deferring {subtask.id[-12:]} — {brain} at capacity ({current_load}/{max_concurrent})")
                    deferred += 1
                    continue
                
                print(f"[ORCH] Dispatching subtask {subtask.id[-12:]} → brain={subtask.brain_target} type={subtask.payload.get('type')} desc={subtask.description[:60]}")
                await self._dispatch_subtask(plan, subtask)
            
            if deferred > 0:
                print(f"[ORCH] {deferred} subtask(s) deferred — will retry when brains free up")
        finally:
            plan._dispatching = False
    
    async def _dispatch_subtask(self, plan: TaskPlan, subtask: SubTask) -> None:
        """Dispatch a subtask to the appropriate brain."""
        import time
        
        # Update subtask status
        subtask.status = TaskStatus.RUNNING
        subtask.start_time = time.time()
        subtask.assigned_brain = subtask.brain_target
        
        # Update brain load
        self.brain_load[subtask.brain_target] = self.brain_load.get(subtask.brain_target, 0) + 1
        
        # Resolve any variable references in payload
        resolved_payload = await self._resolve_payload_references(subtask.payload, plan)
        
        # Send task to brain
        task_message = BusMessage(
            type=MessageType.TASK,
            source=self.name,
            target=subtask.brain_target,
            workspace=self.workspace,
            project=plan.original_task.project,
            payload={**resolved_payload, "_subtask_id": subtask.id},
            reply_to=subtask.id  # Informational — not used for result matching
        )
        
        # Track by BusMessage ID — this is what brain.send_result uses as reply_to
        self.active_subtasks[task_message.id] = plan.id
        # Also map message ID → subtask ID for lookup
        subtask._dispatch_msg_id = task_message.id
        
        # Announce subtask started BEFORE dispatching (bus.send delivers
        # synchronously in-loop, so the brain may complete before we return)
        await self.bus.broadcast_event(
            source=self.name,
            event_type="subtask.started",
            payload={
                "task_id": plan.id,
                "subtask_id": subtask.id,
                "brain": subtask.brain_target,
                "description": subtask.description
            },
            workspace=self.workspace,
            priority=Priority.NORMAL
        )
        
        await self.bus.send(task_message)
    
    async def _resolve_payload_references(self, payload: Dict[str, Any], 
                                        plan: TaskPlan) -> Dict[str, Any]:
        """
        Resolve ReWOO-style variable references and inject upstream context.
        
        1. Replaces references like "#s1" with actual results from completed subtasks
           (handles both raw IDs and plan-prefixed IDs)
        2. Injects all completed subtask results as `upstream_context` so downstream
           brains can use prior results even without explicit references
        """
        resolved = dict(payload)  # shallow copy
        results = plan.get_results()
        
        # Build a lookup that works with both raw and prefixed IDs
        # results keys are like "{plan_id}_s1", but references say "#s1"
        result_lookup = {}
        for full_id, result in results.items():
            result_lookup[full_id] = result
            # Also index by suffix (strip plan_id prefix)
            if "_" in full_id:
                suffix = full_id.split("_", 1)[-1]
                # Handle plan UUIDs: "abc-def_s1" → "s1"
                # Find the last segment that looks like a subtask ID
                parts = full_id.rsplit("_", 1)
                if len(parts) == 2:
                    result_lookup[parts[1]] = result
        
        # Resolve explicit references
        for key, value in payload.items():
            if isinstance(value, str) and value.startswith("#"):
                ref_id = value[1:]  # Remove # prefix
                if ref_id in result_lookup:
                    resolved[key] = result_lookup[ref_id]
        
        # Inject upstream context — all completed subtask results
        # so downstream brains have full picture even without explicit refs
        if results:
            upstream = {}
            for st in plan.subtasks:
                if st.status == TaskStatus.COMPLETE and st.result:
                    # Use a human-readable key
                    brain_name = st.assigned_brain or st.brain_target
                    upstream[f"{brain_name}:{st.description[:80]}"] = st.result
            if upstream:
                resolved["upstream_context"] = upstream
        
        return resolved
    
    async def _handle_task_result(self, message: BusMessage) -> None:
        """Handle result from brain execution.
        
        The brain sends result with reply_to = BusMessage.id (the dispatched
        task message's UUID). We map that back to the subtask/plan.
        """
        import time
        
        dispatch_msg_id = message.reply_to
        if not dispatch_msg_id or dispatch_msg_id not in self.active_subtasks:
            return  # Not our subtask
        
        print(f"[ORCH] Result from {message.source}: success={message.payload.get('success')}, error={message.payload.get('error', 'none')}, reply_to={dispatch_msg_id[:8]}")
        
        plan_id = self.active_subtasks[dispatch_msg_id]
        plan = self.task_plans.get(plan_id)
        if not plan:
            return  # Plan not found
        
        # Find the subtask by its stored dispatch message ID
        subtask = None
        for st in plan.subtasks:
            if getattr(st, '_dispatch_msg_id', None) == dispatch_msg_id:
                subtask = st
                break
        if not subtask:
            return  # Subtask not found
        
        # Check execution mode for this brain
        brain_name = subtask.assigned_brain or subtask.brain_target
        exec_config = self.get_execution_config(brain_name)
        
        # If brain requires V3 cross-check and result was successful, flag it
        if message.payload.get("success", False) and exec_config.should_run_v3():
            # Broadcast event indicating V3 review is needed
            await self.bus.broadcast_event(
                source=self.name,
                event_type="verification.v3_required",
                payload={
                    "task_id": plan.id,
                    "subtask_id": subtask.id,
                    "brain": brain_name,
                    "execution_mode": exec_config.mode.value,
                },
                workspace=self.workspace,
                priority=Priority.NORMAL,
            )
        
        # If brain requires V5 human gate and result was successful, flag it
        if message.payload.get("success", False) and exec_config.should_run_v5():
            await self.bus.broadcast_event(
                source=self.name,
                event_type="verification.v5_required",
                payload={
                    "task_id": plan.id,
                    "subtask_id": subtask.id,
                    "brain": brain_name,
                    "execution_mode": exec_config.mode.value,
                },
                workspace=self.workspace,
                priority=Priority.HIGH,
            )
        
        # ── Handle "busy" rejections: re-queue instead of failing ──
        # Brain was occupied — this isn't a real failure, just bad timing.
        # Reset subtask to PENDING so it gets picked up on next dispatch cycle.
        if (not message.payload.get("success", False) 
                and message.payload.get("busy", False)):
            print(f"[ORCH] Brain {message.source} busy — re-queuing {subtask.id[-12:]}")
            
            # Update brain load BEFORE clearing assigned_brain
            if subtask.assigned_brain:
                current_load = self.brain_load.get(subtask.assigned_brain, 0)
                self.brain_load[subtask.assigned_brain] = max(0, current_load - 1)
            
            # Reset subtask to PENDING for re-dispatch
            subtask.status = TaskStatus.PENDING
            subtask.start_time = None
            subtask.end_time = None
            subtask.assigned_brain = None
            subtask.result = None
            subtask.error = None
            if hasattr(subtask, '_dispatch_msg_id'):
                delattr(subtask, '_dispatch_msg_id')
            
            # Remove from active tracking
            del self.active_subtasks[dispatch_msg_id]
            
            # Don't announce failure or check plan completion — just return.
            # The subtask will be retried when the next subtask completes
            # and triggers _execute_ready_subtasks.
            return
        
        # ── Normal result handling ──
        subtask.end_time = time.time()
        subtask.result = message.payload
        
        if message.payload.get("success", False):
            subtask.status = TaskStatus.COMPLETE
        else:
            subtask.status = TaskStatus.FAILED
            subtask.error = message.payload.get("error", "Unknown error")
        
        # Update brain load
        if subtask.assigned_brain:
            current_load = self.brain_load.get(subtask.assigned_brain, 0)
            self.brain_load[subtask.assigned_brain] = max(0, current_load - 1)
        
        # Remove from active tracking
        del self.active_subtasks[dispatch_msg_id]
        
        # Announce subtask completion
        await self.bus.broadcast_event(
            source=self.name,
            event_type="subtask.complete" if subtask.status == TaskStatus.COMPLETE else "subtask.failed",
            payload={
                "task_id": plan.id,
                "subtask_id": subtask.id,
                "status": subtask.status.value,
                "execution_time": subtask.end_time - subtask.start_time if subtask.start_time else 0
            },
            workspace=self.workspace,
            priority=Priority.NORMAL
        )
        
        # Check if entire plan is complete FIRST (before trying to start more)
        await self._check_plan_completion(plan)
        
        # Start more subtasks if plan is still running
        # (includes previously deferred/busy-rejected subtasks that are now PENDING again)
        if subtask.status == TaskStatus.COMPLETE and plan.status == TaskStatus.RUNNING:
            await self._execute_ready_subtasks(plan)
    
    async def _check_plan_completion(self, plan: TaskPlan) -> None:
        """Check if a task plan is complete and send final result."""
        if plan.is_complete() or plan.is_failed():
            import time
            
            if plan.is_failed():
                plan.status = TaskStatus.FAILED
                plan.error = "One or more subtasks failed"
                failed_subtasks = [st for st in plan.subtasks if st.status == TaskStatus.FAILED]
                plan.result = {
                    "success": False,
                    "error": plan.error,
                    "failed_subtasks": [{"id": st.id, "error": st.error} for st in failed_subtasks]
                }
            else:
                plan.status = TaskStatus.COMPLETE
                plan.result = {
                    "success": True,
                    "results": plan.get_results(),
                    "subtasks_completed": len(plan.subtasks)
                }
            
            # Send final result back to original requester (explicit target)
            await self.bus.send_result(
                source=self.name,
                target=plan.original_task.source,
                result_data=plan.result,
                reply_to=plan.original_task.id,
                workspace=self.workspace,
                project=plan.original_task.project
            )
            
            # Announce plan completion
            await self.bus.broadcast_event(
                source=self.name,
                event_type="task.complete" if plan.status == TaskStatus.COMPLETE else "task.failed",
                payload={
                    "task_id": plan.id,
                    "status": plan.status.value,
                    "workspace": self.workspace,
                    "subtasks_total": len(plan.subtasks)
                },
                workspace=self.workspace,
                priority=Priority.NORMAL
            )
    
    async def _handle_cancel_request(self, message: BusMessage) -> None:
        """Handle task cancellation requests."""
        task_id = message.payload.get("task_id")
        cancel_mode = message.payload.get("mode", "soft")
        
        if task_id:
            await self._cancel_task(task_id, cancel_mode)
        else:
            # Cancel all active tasks
            for plan_id in list(self.task_plans.keys()):
                plan = self.task_plans[plan_id]
                if plan.status == TaskStatus.RUNNING:
                    await self._cancel_task(plan_id, cancel_mode)
    
    async def _cancel_task(self, task_id: str, mode: str) -> None:
        """Cancel a specific task and all its subtasks."""
        plan = self.task_plans.get(task_id)
        if not plan or plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return
        
        plan.status = TaskStatus.CANCELLED
        
        # Cancel active subtasks (keys are dispatch message IDs)
        for dispatch_id in list(self.active_subtasks.keys()):
            if self.active_subtasks[dispatch_id] == task_id:
                # Find subtask by dispatch message ID
                subtask = None
                for st in plan.subtasks:
                    if getattr(st, '_dispatch_msg_id', None) == dispatch_id:
                        subtask = st
                        break
                if subtask and subtask.assigned_brain:
                    # Send cancel to brain
                    cancel_msg = BusMessage(
                        type=MessageType.CANCEL,
                        source=self.name,
                        target=subtask.assigned_brain,
                        payload={"task_id": subtask.id, "mode": mode}
                    )
                    await self.bus.send(cancel_msg)
        
        await self.bus.broadcast_event(
            source=self.name,
            event_type="task.cancelled",
            payload={
                "task_id": task_id,
                "mode": mode,
                "workspace": self.workspace
            },
            workspace=self.workspace,
            priority=Priority.NORMAL
        )
    
    async def _handle_query(self, message: BusMessage) -> None:
        """Handle query requests for orchestrator status."""
        query_type = message.payload.get("type")
        
        if query_type == "status":
            await self.bus.send_result(
                source=self.name,
                result_data=self.get_status(),
                reply_to=message.id,
                workspace=self.workspace
            )
        elif query_type == "tasks":
            await self.bus.send_result(
                source=self.name,
                result_data={
                    "active_tasks": [
                        {
                            "id": plan.id,
                            "status": plan.status.value,
                            "subtasks": len(plan.subtasks),
                            "completed_subtasks": sum(1 for st in plan.subtasks 
                                                    if st.status == TaskStatus.COMPLETE)
                        }
                        for plan in self.task_plans.values()
                    ]
                },
                reply_to=message.id,
                workspace=self.workspace
            )
    
    async def _forward_brain_event(self, message: BusMessage) -> None:
        """Forward brain events to interested parties (like Front Brain).
        
        Note: Disabled in preview to prevent broadcast loops.
        In production, use targeted sends instead of re-broadcasting.
        """
        # Don't re-broadcast — causes infinite loops when multiple
        # components all listen on wildcard and forward events.
        # The original event is already visible to all subscribers.
        pass
    
    def register_brain(self, brain_name: str, capabilities: Dict[str, Any] = None) -> None:
        """Register a brain with this orchestrator."""
        self.registered_brains[brain_name] = capabilities or {}
        self.brain_load[brain_name] = 0
    
    def unregister_brain(self, brain_name: str) -> None:
        """Unregister a brain from this orchestrator."""
        self.registered_brains.pop(brain_name, None)
        self.brain_load.pop(brain_name, None)
    
    def set_execution_mode(self, brain_name: str, mode: ExecutionMode, **kwargs) -> BrainExecutionConfig:
        """
        Set execution mode for a specific brain.
        
        Args:
            brain_name: Name of the brain to configure
            mode: Execution mode to set
            **kwargs: Additional config options (requires_approval, max_retries, verification_levels)
            
        Returns:
            The created/updated BrainExecutionConfig
        """
        config = BrainExecutionConfig(
            brain_name=brain_name,
            mode=mode,
            requires_approval=kwargs.get("requires_approval", mode == ExecutionMode.CONTROL),
            max_retries=kwargs.get("max_retries", 3),
            verification_levels=kwargs.get("verification_levels", None),
        )
        self.execution_configs[brain_name] = config
        return config
    
    def get_execution_config(self, brain_name: str) -> BrainExecutionConfig:
        """
        Get execution config for a brain, defaulting to LIGHTNING if not set.
        
        Args:
            brain_name: Name of the brain
            
        Returns:
            BrainExecutionConfig for the brain
        """
        if brain_name in self.execution_configs:
            return self.execution_configs[brain_name]
        # Default: lightning mode (full auto)
        return BrainExecutionConfig(brain_name=brain_name, mode=ExecutionMode.LIGHTNING)

    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status for monitoring."""
        return {
            "workspace": self.workspace,
            "name": self.name,
            "running": self._running,
            "active_tasks": len([p for p in self.task_plans.values() 
                               if p.status == TaskStatus.RUNNING]),
            "total_tasks": len(self.task_plans),
            "registered_brains": list(self.registered_brains.keys()),
            "brain_load": dict(self.brain_load),
            "active_subtasks": len(self.active_subtasks),
            "execution_configs": {
                name: {"mode": config.mode.value, "requires_approval": config.requires_approval}
                for name, config in self.execution_configs.items()
            }
        }