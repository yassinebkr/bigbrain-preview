"""WorkspaceOrchestrator - Event-driven task management for BigBrain."""

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from ..bus.bus import MessageBus
from ..bus.message import BusMessage, MessageType, Priority
from ..bus.participant import BusParticipant
from ..bus.results import result_data
from ..llm.conversation import scoped_conversation
from .architect import ArchitectPhase, ProjectSpec
from ..execution_target import ExecutionTarget, FILE_TASKS, resolve_target
from .execution_modes import BrainExecutionConfig, ExecutionMode
from .task_tracker import TaskTracker
from .checkpoint import FileCheckpoint
from .risk import classify_risk, RiskLevel, get_risk_description
from ..verification.contracts import (
    approval_flow_enabled as _contracts_approval_flow_enabled,
    plan_needs_approval as _plan_needs_approval,
)

logger = logging.getLogger(__name__)
PLANNING_HEARTBEAT_SECONDS = 5.0


class PlanningError(ValueError):
    """A failed planning stage, never permission to switch worker families."""

    def __init__(self, stage: str, detail: str, plan_id: str = ""):
        self.stage = stage
        self.plan_id = plan_id
        super().__init__(f"Planning failed ({stage}): {detail[:500]}")


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
    tracker: Optional['TaskTracker'] = None
    execution_mode: str = "dag"  # "todo" or "dag"
    # Contract approval gate (Phase B): a plan that writes code waits for
    # the user to approve its contracts before any subtask is dispatched.
    awaiting_approval: bool = False
    approval_design_id: Optional[str] = None
    project_spec: Optional[ProjectSpec] = None
    execution_target: Optional[ExecutionTarget] = None
    inspection: Optional[dict] = None
    transaction: Optional[str] = None
    local_project: Optional[dict] = None
    source_transmission: Optional[dict] = None
    
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
                results[subtask.id] = result_data(subtask.result)
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
    
    # System prompt for complexity assessment (year injected at runtime)
    COMPLEXITY_SYSTEM_PROMPT = """The current year is {current_year}. Always use {current_year} in research queries.

You are a project complexity assessor. Given a user request, determine if it needs:
1. "script" — a single source file can handle it
2. "project" — multiple files needed

Also select the deliverable from the requested user experience:
- "python" for Python scripts, CLI, libraries, services or automation
- "web_app" for an interactive browser application

Also determine if research is needed before coding (new APIs, best practices, state of the art).

Respond with ONLY a JSON object, no explanation:
{{"mode": "script"|"project", "deliverable_type": "python"|"web_app", "needs_research": true|false, "research_queries": ["query1"], "reason": "brief reason"}}

Examples:
- "write a fibonacci function" → {{"mode": "script", "deliverable_type": "python", "needs_research": false, "research_queries": [], "reason": "single algorithm"}}
- "build a browser task tracker" → {{"mode": "project", "deliverable_type": "web_app", "needs_research": false, "research_queries": [], "reason": "interactive browser UI with persistent state"}}
- "create a REST API with database" → {{"mode": "project", "deliverable_type": "python", "needs_research": false, "research_queries": [], "reason": "backend service with models, routes and app setup"}}"""

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
    SIMPLE_PLANNER_PROMPT = """The current year is {current_year}.

You are a task planner for a multi-brain AI system.

Your job: decompose a user's request into concrete subtasks, each assigned to the right brain.

Available brains (use exactly these names as brain_target):
{brain_list}

CRITICAL RULES:
- Each subtask has: id, description, brain_target, payload (with "type" and "user_request"), dependencies
- Use dependencies to enforce ordering when one subtask needs another's output
- For simple code tasks: 1 subtask to python_brain
- The "type" field in payload should be "generate_and_execute" for code tasks, "research" for research tasks
- To RUN an existing file (e.g. "run hello.py"), use type "run_file" with payload {{"type": "run_file", "file": "hello.py"}} — the file must already exist in the project
- To ADD A TASK to the user's task board, use brain_target "taskboard" with payload {{"type": "board_task", "title": "<short task title>", "description": "<details>", "status": "todo"}} — a requested task is a TO-DO unless the user explicitly says it is done or in progress
- If research is needed, add a researcher subtask BEFORE the coding subtask with a dependency

Respond with ONLY a JSON array. No explanation, no markdown fences.

Example — single task:
[{{"id": "s1", "description": "Generate fibonacci code", "brain_target": "python_brain", "payload": {{"type": "generate_and_execute", "user_request": "write a fibonacci function"}}, "dependencies": []}}]

Example — research then code:
[{{"id": "s1", "description": "Research WebSocket libraries", "brain_target": "researcher", "payload": {{"type": "research", "query": "python websocket server libraries comparison 2026"}}, "dependencies": []}}, {{"id": "s2", "description": "Build WebSocket server", "brain_target": "python_brain", "payload": {{"type": "generate_and_execute", "user_request": "build a websocket chat server", "context_ref": "#s1"}}, "dependencies": ["s1"]}}]

Example — the user asks to ADD A TASK to their task board (taskboard brain, NOT a code task):
User: "ajoute une tâche à la taskboard : mettre à jour le README de near_agi"
[{{"id": "s1", "description": "Add board task", "brain_target": "taskboard", "payload": {{"type": "board_task", "title": "mettre à jour le README de near_agi", "status": "todo"}}, "dependencies": []}}]"""

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
        
        # Brain pools: logical name → list of worker names
        # e.g. "python_brain" → ["python_brain_0", "python_brain_1", "python_brain_2"]
        self.brain_pools: Dict[str, List[str]] = {}
        
        # Track which brains are alive (responded to start or sent events recently)
        self._alive_brains: set = set()
        
        # Execution mode configs per brain
        self.execution_configs: Dict[str, BrainExecutionConfig] = {}
        
        # File checkpointing system
        self.checkpoint_manager = FileCheckpoint(max_checkpoints=10)
    
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
        import sys
        print(f"[ORCH] handle_message: type={message.type} source={message.source} target={message.target}", flush=True, file=sys.stderr)
        
        # Skip our own messages to prevent infinite broadcast loops
        if message.source == self.name:
            return
        
        try:
            # Track brain liveness — any message from a brain means it's alive
            if message.source and message.source != self.name:
                self._alive_brains.add(message.source)
            
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
            import sys, traceback
            print(f"[ORCH] ERROR in handle_message: {e}", flush=True, file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
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

        # Contract approval verdict from the UI (approve/reject buttons)
        if task_data.get("type") == "contracts.approval":
            await self._handle_contracts_approval(task_data)
            return

        # Create task plan
        try:
            plan = await self._create_task_plan(message)
        except PlanningError as exc:
            await self._report_planning_failure(message, exc)
            return
        self.task_plans[plan.id] = plan
        plan.status = TaskStatus.RUNNING
        
        # Announce task received — include description for UI
        task_desc = (message.payload.get("user_request") or message.payload.get("description", "")) if message.payload else ""
        await self.bus.broadcast_event(
            source=self.name,
            event_type="task.received",
            payload={
                "task_id": plan.id,
                "description": task_desc or f"{len(plan.subtasks)} subtask(s)",
                "workspace": self.workspace,
                "subtasks_count": len(plan.subtasks),
                "session_id": task_data.get("session_id"),
                "project_path": plan.execution_target.path if plan.execution_target else None,
            },
            workspace=self.workspace,
            priority=Priority.NORMAL
        )
        
        # Auto-checkpoint before execution (for file-based projects)
        await self._auto_checkpoint_before_execution(plan)
        
        # Contract gate (Phase B): plans that WRITE code propose their
        # contracts and wait for explicit user approval. Kill switch:
        # BIGBRAIN_CONTRACTS=0 disables the gate entirely.
        if (plan.subtasks and plan.awaiting_approval is False
                and _contracts_approval_flow_enabled()
                and _plan_needs_approval(plan.subtasks)):
            user_request = (
                task_data.get("user_request")
                or task_data.get("request")
                or task_data.get("query")
                or task_data.get("description")
                or str(task_data)
            )
            started = time.monotonic()
            await self._planning_progress("contracts", "running", task_data.get("session_id"), task_id=plan.id)
            try:
                spec = await asyncio.wait_for(self._propose_contracts(plan, user_request), timeout=20)
                if spec is None:
                    raise ValueError("Proposal was not recorded")
            except Exception as exc:
                await self._report_planning_failure(message, PlanningError(
                    "contracts", str(exc) or type(exc).__name__, plan.id))
                return
            await self._planning_progress("contracts", "done", task_data.get("session_id"), started, task_id=plan.id)
            return  # subtasks dispatch only after approval
        
        # Start executing ready subtasks
        plan.status = TaskStatus.RUNNING
        await self._execute_ready_subtasks(plan)

    async def _propose_contracts(self, plan: TaskPlan,
                                 user_request: str):
        """Draft contracts, persist the spec, notify the UI. Returns the
        DesignSpec (None if the proposal could not be persisted)."""
        from ..verification.contracts import (
            build_proposal_spec,
            draft_contracts,
        )
        from ..verification.evidence import ImmutableRunError, default_repository

        contracts = await draft_contracts(
            self.llm_provider, user_request, project_spec=plan.project_spec)
        maintenance = any(st.payload.get('type') == 'maintain_project' for st in plan.subtasks)
        if maintenance:
            contracts.append('Maintenance du projet existant : inspection progressive, corrections ciblées des sources dans le projet approuvé, sans remplacement du projet. Tests existants et comportement attendu inchangés sauf décision explicitement approuvée ci-dessous. Maximum 40 actions / 600 secondes ; livraison uniquement après vérification indépendante.')
            for decision in plan.project_spec.test_changes:
                contracts.append(f"Modification de validation {decision['path']} : {decision['reason']} — comportement attendu : {decision['expected_behavior']} — fondement : {decision['authority']}")
        if plan.inspection and plan.project_spec:
            changes = [f'{"modifier" if fs.operation == "modify" else "créer"} {fs.path}' for fs in plan.project_spec.file_specs if fs.operation != 'keep']
            contracts.append('Périmètre des changements approuvés : ' + (' ; '.join(changes) or 'vérification seule, aucun fichier à modifier'))
            for decision in plan.project_spec.test_changes:
                contracts.append(f"Modification des tests {decision['path']} : {decision['reason']} — comportement attendu : {decision['expected_behavior']} — fondement : {decision['authority']}")
        if plan.status == TaskStatus.CANCELLED:
            raise asyncio.CancelledError
        if not any(not item.startswith("[Stack]") for item in contracts):
            raise ValueError("No verifiable acceptance contracts were produced; execution remains blocked")
        spec = build_proposal_spec(user_request, contracts)
        spec.metadata['business_criteria'] = list(plan.project_spec.acceptance_contracts) if plan.project_spec else list(contracts)
        if plan.project_spec:
            spec.metadata['execution'] = {'interaction_mode': plan.project_spec.interaction_mode}
            spec.metadata['delivery'] = {
                'deliverable_type': plan.project_spec.deliverable_type,
                'executable': plan.project_spec.executable,
                'entry_point': plan.project_spec.entry_point if plan.project_spec.executable else None,
                'web_stack': plan.project_spec.web_stack}
        elif plan.execution_target and plan.execution_target.mode == 'new' and any(
                st.payload.get('type') == 'generate_and_execute' for st in plan.subtasks):
            script = next(st for st in plan.subtasks if st.payload.get('type') == 'generate_and_execute')
            executable = script.payload.get('executable', True) is not False
            spec.metadata['execution'] = {'interaction_mode': script.payload.get('interaction_mode') or
                ('cli' if executable else 'library')}
            spec.metadata['delivery'] = {'deliverable_type': 'python', 'executable': executable,
                'entry_point': script.payload.get('entry_point') or 'main.py' if executable else None, 'web_stack': 'static'}
            spec.contracts.append('Livraison Python : point d’entrée ' + str(spec.metadata['delivery']['entry_point'])
                + ' ; tests et critères approuvés vérifiés avant livraison, réparation bornée si nécessaire.')
        if maintenance:
            # Runtime capability derives from the recorded user-approved proposal,
            # never from a worker's tool action or an arbitrary payload flag.
            spec.metadata['maintenance'] = {'protocol': 'bigbrain-maintenance/1',
                'test_changes': plan.project_spec.test_changes}
        if plan.local_project:
            spec.metadata['local_project'] = dict(plan.local_project)
            spec.metadata['source_transmission'] = plan.source_transmission
        if plan.execution_target is not None:
            spec.metadata["execution_target"] = plan.execution_target.public()
        if plan.inspection:
            spec.metadata['inspection'] = {k: plan.inspection[k] for k in ('inventory', 'limits', 'limited')}
            spec.metadata['baseline_diagnostic'] = plan.inspection.get('baseline')
        try:
            default_repository().save_spec(spec)
        except ImmutableRunError:
            # Repeated wording must not resurrect a different old contract.
            stored = default_repository().load_latest_spec(spec.design_id)
            if stored is None:
                raise ValueError("Existing proposal could not be loaded")
            if (stored.contracts == spec.contracts and "approval" not in stored.metadata
                    and stored.metadata.get("execution_target") == spec.metadata.get("execution_target")
                    and stored.metadata.get('delivery') == spec.metadata.get('delivery')
                    and stored.metadata.get('execution') == spec.metadata.get('execution')
                    and stored.metadata.get('business_criteria') == spec.metadata.get('business_criteria')
                    and stored.metadata.get('inspection') == spec.metadata.get('inspection')
                    and stored.metadata.get('local_project') == spec.metadata.get('local_project')
                    and stored.metadata.get('source_transmission') == spec.metadata.get('source_transmission')):
                spec = stored
            else:
                spec = spec.model_copy(update={"revision": stored.revision + 1})
                default_repository().save_spec(spec)
        plan.approval_design_id = spec.design_id
        for subtask in plan.subtasks:
            subtask.payload['acceptance_contracts'] = list(spec.contracts)
            subtask.payload['contract_revision'] = {'design_id': spec.design_id, 'revision': spec.revision}
        plan.awaiting_approval = True
        plan.status = TaskStatus.RUNNING
        await self.bus.broadcast_event(
            source=self.name,
            event_type="contracts.proposal",
            payload={
                "design_id": spec.design_id,
                "plan_id": plan.id,
                "user_request": user_request,
                "contracts": list(spec.contracts),
                "local_project": plan.local_project,
                "source_transmission": plan.source_transmission,
                "project_target": plan.execution_target.public() if plan.execution_target else None,
                "session_id": (plan.original_task.payload or {}).get("session_id"),
            },
            workspace=self.workspace,
            priority=Priority.NORMAL,
        )
        return spec

    async def _handle_contracts_approval(self, task_data: dict) -> None:
        """Resume or cancel a plan after the user's verdict."""
        from ..verification.evidence import default_repository

        plan_id = task_data.get("plan_id")
        design_id = task_data.get("design_id")
        approved = bool(task_data.get("approve"))
        plan = self.task_plans.get(plan_id)
        if plan is None:
            await self.bus.broadcast_event(
                source=self.name, event_type='contracts.approval_failed',
                payload={'plan_id': plan_id, 'error': 'Proposition expirée ou serveur redémarré. Relance la demande.'},
                workspace=self.workspace, priority=Priority.NORMAL)
            return
        if not plan.awaiting_approval:
            return  # already-resolved proposal: idempotent

        if (task_data.get("design_id") != plan.approval_design_id
                or not isinstance(task_data.get("approve"), bool)
                or plan.status != TaskStatus.RUNNING):
            await self.bus.broadcast_event(
                source=self.name, event_type="contracts.approval_failed",
                payload={"plan_id": plan.id, "error": "Invalid or stale contract decision",
                         "session_id": (plan.original_task.payload or {}).get("session_id")},
                workspace=self.workspace, priority=Priority.NORMAL)
            return
        try:
            if plan.execution_target is not None:
                plan.execution_target.validate()
                proposal = default_repository().load_latest_spec(design_id)
                if proposal is None or proposal.metadata.get("execution_target") != plan.execution_target.public():
                    raise ValueError("La destination du plan ne correspond plus au contrat")
            stamped = default_repository().approve_spec(
                design_id or plan.approval_design_id or "",
                plan_id=plan.id,
                decision="approved" if approved else "rejected",
            )
            if stamped is None:
                raise ValueError("Contract evidence was not found")
        except Exception as e:
            logger.warning("Contract approval persistence failed: %s", e)
            await self.bus.broadcast_event(
                source=self.name, event_type="contracts.approval_failed",
                payload={"plan_id": plan.id, "error": "Approval could not be recorded; execution remains paused",
                         "session_id": (plan.original_task.payload or {}).get("session_id")},
                workspace=self.workspace, priority=Priority.NORMAL)
            return

        plan.awaiting_approval = False

        if approved:
            for subtask in plan.subtasks:
                subtask.payload['acceptance_contracts'] = list(stamped.contracts)
                subtask.payload['business_contracts'] = stamped.metadata.get('business_criteria', [])
                subtask.payload['contract_revision'] = {'design_id': stamped.design_id, 'revision': stamped.revision}
                if subtask.payload.get('type') == 'maintain_project':
                    subtask.payload['_approved_test_paths'] = [d['path'] for d in
                        stamped.metadata.get('maintenance', {}).get('test_changes', [])]
            await self.bus.broadcast_event(
                source=self.name,
                event_type="contracts.approved",
                payload={
                    "design_id": design_id, "plan_id": plan.id,
                    "session_id": (plan.original_task.payload or {}).get("session_id"),
                },
                workspace=self.workspace,
                priority=Priority.NORMAL,
            )
            await self._execute_ready_subtasks(plan)
        else:
            await self.bus.broadcast_event(
                source=self.name,
                event_type="contracts.rejected",
                payload={
                    "design_id": design_id, "plan_id": plan.id,
                    "session_id": (plan.original_task.payload or {}).get("session_id"),
                },
                workspace=self.workspace,
                priority=Priority.NORMAL,
            )
            await self._cancel_task(plan.id, "soft")
    
    @scoped_conversation('planner', message_argument='message')
    async def _create_task_plan(self, message: BusMessage) -> TaskPlan:
        plan = await self._create_unbound_task_plan(message)
        if plan.local_project:
            # Attached work owns its registry-bound transaction and scratch copy.
            if any(st.payload.get('local_project') != plan.local_project for st in plan.subtasks):
                raise PlanningError('destination', 'Attached project scope differs between subtasks', plan.id)
            return plan
        try:
            from ..memory.shared import SharedMemory
            log_dir = getattr(getattr(self.bus, 'logger', None), 'log_dir', None)
            target = resolve_target(
                plan.id, message.payload or {}, plan.subtasks, plan.project_spec,
                partial_project_check=lambda path: bool(log_dir) and SharedMemory(log_dir).owns_partial_project(
                    (message.payload or {}).get("session_id"), path))
            if plan.execution_target:
                plan.execution_target.validate()  # retain the identity inspected before planning
                if target is None or target.public() != plan.execution_target.public():
                    raise ValueError('Execution destination changed after inspection')
            else:
                plan.execution_target = target
            if target and target.mode == 'existing' and not plan.inspection and any(
                    s.payload.get('type') in {'edit_file', 'write_project_file', 'write_web_file'} for s in plan.subtasks):
                from ..project_inspection import inspect_project, diagnose_project
                plan.inspection = await asyncio.to_thread(inspect_project, target)
                plan.inspection['baseline'] = await diagnose_project(target, plan.inspection)
                for subtask in plan.subtasks:
                    if subtask.payload.get('type') not in {'edit_file', 'write_project_file', 'write_web_file'}:
                        continue
                    path = subtask.payload.get('file_path', '')
                    if path.startswith(target.path + '/'):
                        path = path[len(target.path) + 1:]
                    original = plan.inspection['sources'].get(path)
                    if target.file(path).exists():
                        if not original or not original['complete']:
                            raise ValueError(f'{path}: existing file was not completely inspected')
                        subtask.payload['_existing_source'] = original
                    else:
                        subtask.payload['_create_only'] = True
            if plan.inspection:
                writers = [st for st in plan.subtasks if st.payload.get('type') in
                           {'edit_file', 'write_project_file', 'write_web_file'}]
                if writers and not any(st.payload.get('type') in {'assemble_and_run', 'assemble_and_preview'} for st in plan.subtasks):
                    manifest = target.file('.project.json')
                    if not manifest.is_file():
                        raise ValueError('Native modification needs an existing entry-point manifest; use an architect project plan to recover it')
                    metadata = json.loads(manifest.read_text())
                    entry = metadata.get('entry_point')
                    if not isinstance(entry, str):
                        raise ValueError('Existing project has no declared entry point for post-edit validation')
                    target.file(entry)
                    web = metadata.get('deliverable_type') == 'web_app'
                    plan.subtasks.append(SubTask(id=plan.id + '_validation', description='Verify modified project',
                        brain_target='web_app_brain' if web else 'python_brain',
                        payload={'type': 'assemble_and_preview' if web else 'assemble_and_run',
                            'project_name': target.directory.name, 'entry_point': entry,
                            'web_stack': metadata.get('web_stack', 'static'),
                            'user_request': writers[0].payload.get('user_request', ''),
                            'all_files': [{'path': path} for path in sorted(
                                {p for p, source in plan.inspection['sources'].items() if source['complete']} |
                                {st.payload['file_path'].removeprefix(target.path + '/') for st in writers})],
                            '_editable_paths': [st.payload['file_path'].removeprefix(target.path + '/') for st in writers]},
                        dependencies={st.id for st in writers}))
                for subtask in plan.subtasks:
                    subtask.payload['baseline_diagnostic'] = plan.inspection.get('baseline')
        except ValueError as exc:
            raise PlanningError("destination", str(exc), plan.id) from exc
        return plan

    async def _create_unbound_task_plan(self, message: BusMessage) -> TaskPlan:
        """
        Decompose a task into executable subtasks using LLM planning.
        
        Planning pipeline:
        1. Assess complexity (script vs project, research needed?)
        2. If project mode → plan file structure → build DAG
        3. If script mode → simple single-task routing
        4. Falls back to deterministic routing if no LLM available
        """
        plan_id = str(message.payload.get("_ui_run_id") or uuid.uuid4())
        plan = TaskPlan(id=plan_id, original_task=message)
        
        task_data = message.payload
        user_request = (
            task_data.get("user_request")
            or task_data.get("request")
            or task_data.get("query")
            or task_data.get("description")
            or str(task_data)
        )
        
        # Explicit route from the Front Brain (LLM tool-call): the LLM
        # already picked the brain and payload — execute them verbatim,
        # no re-planning and no decomposition. Unknown brain names fall
        # through to the normal planning pipeline.
        routed_brain = task_data.get("brain")
        if task_data.get('type') == 'maintain_project':
            deliverable = task_data.get('deliverable_type')
            if deliverable not in {'python', 'web_app'}:
                raise PlanningError('maintenance', 'Explicit specialist deliverable required', plan_id)
            expected_brain = 'web_app_brain' if deliverable == 'web_app' else 'python_brain'
            if routed_brain and routed_brain != expected_brain:
                raise PlanningError('maintenance', 'Explicit route and deliverable disagree', plan_id)
            plan.subtasks = await self._plan_maintenance(plan, user_request, deliverable)
            plan.tracker = TaskTracker.create_from_plan(plan.subtasks)
            return plan
        if routed_brain and (
            routed_brain in self.registered_brains
            or routed_brain in self.brain_pools
        ):
            payload = {k: v for k, v in task_data.items() if k != "brain"}
            payload["user_request"] = payload.get("user_request") or user_request
            subtasks = [SubTask(
                id=f"{plan_id}_s0",
                description=f"Execute {payload.get('type', 'routed')} task",
                brain_target=routed_brain,
                payload=payload,
            )]
            plan.subtasks = subtasks
            plan.execution_mode = self._analyze_execution_mode(subtasks, user_request)
            plan.tracker = TaskTracker.create_from_plan(subtasks)
            return plan
        
        # LLM decisions are authoritative: a malformed plan is not Python.
        stage = "assessment"
        if self.llm_provider:
            try:
                # Step 1: Assess complexity
                started = time.monotonic()
                await self._planning_progress(stage, "running", task_data.get("session_id"), task_id=plan_id)
                assessment = await asyncio.wait_for(self._assess_complexity(user_request), timeout=20)
                await self._planning_progress(stage, "done", task_data.get("session_id"), started, task_id=plan_id)
                logger.info("Complexity assessment: mode=%s, research=%s, reason=%s",
                           assessment.get("mode"), assessment.get("needs_research"),
                           assessment.get("reason", ""))
                
                await self.bus.broadcast_event(
                    source=self.name,
                    event_type="planning.assessment",
                    payload={"assessment": assessment, "request": user_request[:100],
                             "session_id": task_data.get("session_id"),
                             "elapsed_ms": round((time.monotonic() - started) * 1000)},
                    workspace=self.workspace,
                    priority=Priority.LOW
                )
                
                mode = assessment.get("mode", "script")
                needs_research = assessment.get("needs_research", False)
                research_queries = assessment.get("research_queries", [])
                
                choice = task_data.get('project_target') or {}
                maintenance = bool(task_data.get('project_path') or choice.get('mode') == 'existing')
                if maintenance or mode == "project" or assessment["deliverable_type"] == "web_app":
                    stage = 'maintenance' if maintenance else 'architect'
                    started = time.monotonic()
                    await self._planning_progress(stage, "running", task_data.get("session_id"), task_id=plan_id)
                    # Step 2a: Project mode — plan file structure, build DAG
                    if maintenance:
                        subtasks = await self._plan_maintenance(plan, user_request, assessment['deliverable_type'])
                    else:
                        subtasks = await self._plan_project(plan_id, user_request,
                                                         needs_research, research_queries,
                                                         deliverable_type=assessment["deliverable_type"],
                                                         session_id=task_data.get("session_id"),
                                                         plan=plan)
                else:
                    stage = "decomposition"
                    started = time.monotonic()
                    await self._planning_progress(stage, "running", task_data.get("session_id"), task_id=plan_id)
                    # Step 2b: Script mode — simple decomposition
                    subtasks = await asyncio.wait_for(
                        self._llm_decompose(plan_id, user_request, task_data,
                                            needs_research, research_queries), timeout=20)
                
                if subtasks:
                    await self._planning_progress(stage, "done", task_data.get("session_id"), started, task_id=plan_id)
                    plan.subtasks = subtasks
                    # Analyze complexity and choose execution mode
                    plan.execution_mode = self._analyze_execution_mode(subtasks, user_request)
                    # Create TaskTracker from subtasks
                    plan.tracker = TaskTracker.create_from_plan(subtasks)
                    return plan
                    
            except PlanningError:
                raise
            except Exception as e:
                # Preserve an explicitly typed direct action if the planner
                # is unavailable. Generic/compound work must fail closed.
                if stage == "assessment" and task_data.get("type") not in {"compound", "unknown", None}:
                    try:
                        plan.subtasks = self._simple_decompose(plan_id, task_data)
                    except ValueError:
                        pass
                    else:
                        plan.tracker = TaskTracker.create_from_plan(plan.subtasks)
                        return plan
                raise PlanningError(stage, str(e) or type(e).__name__, plan_id) from e
        
        # Fallback: simple deterministic routing
        try:
            plan.subtasks = self._simple_decompose(plan_id, task_data)
        except ValueError as exc:
            raise PlanningError("assessment", "No planning provider available for this request", plan_id) from exc
        # Analyze complexity and choose execution mode
        plan.execution_mode = self._analyze_execution_mode(plan.subtasks, user_request)
        # Create TaskTracker from subtasks
        plan.tracker = TaskTracker.create_from_plan(plan.subtasks)
        return plan

    async def _planning_progress(self, stage: str, status: str,
                                 session_id: Optional[str], started: Optional[float] = None,
                                 task_id: Optional[str] = None) -> None:
        labels = {"maintenance": "Préparation de la maintenance", "inspection": "Inspection du projet existant", "assessment": "Analyse de la demande", "architect": "Architecture et critères d’acceptation",
                  "decomposition": "Préparation des étapes", "contracts": "Enregistrement de la proposition"}
        await self.bus.broadcast_event(
            source=self.name, event_type="planning.stage",
            payload={"stage": stage, "status": status, "session_id": session_id, "task_id": task_id,
                     "description": labels[stage],
                     "elapsed_ms": round((time.monotonic() - started) * 1000) if started else None},
            workspace=self.workspace, priority=Priority.NORMAL)

    async def _report_planning_failure(self, message: BusMessage, error: PlanningError) -> None:
        """Close preparation visibly without a contract or worker dispatch."""
        plan_id = error.plan_id or str(uuid.uuid4())
        if plan_id in self.task_plans and self.task_plans[plan_id].status == TaskStatus.CANCELLED:
            return
        self.task_plans[plan_id] = TaskPlan(
            id=plan_id, original_task=message, status=TaskStatus.FAILED,
            error=str(error), result={"success": False, "error": str(error)})
        payload = {"task_id": plan_id, "session_id": message.payload.get("session_id"),
                   "error": str(error), "stage": error.stage, "runnable": False}
        target = message.payload.get("project_target")
        if isinstance(target, dict) and target.get("mode") == "existing":
            payload["project_path"] = target.get("path")
        await self.bus.broadcast_event(
            source=self.name, event_type="task.received",
            payload={**payload, "description": message.payload.get("user_request", "Preparation"),
                     "subtasks_count": 0}, workspace=self.workspace, priority=Priority.NORMAL)
        await self.bus.broadcast_event(
            source=self.name, event_type="planning.failed", payload=payload,
            workspace=self.workspace, priority=Priority.NORMAL)
        await self.bus.send_result(
            source=self.name, target=message.source, reply_to=message.id,
            result_data={**payload, "success": False}, workspace=self.workspace)
        await self.bus.broadcast_event(
            source=self.name, event_type="task.failed", payload=payload,
            workspace=self.workspace, priority=Priority.NORMAL)
    
    async def _assess_complexity(self, user_request: str) -> dict:
        """Assess task complexity: script vs project, research needed."""
        messages = [
            {"role": "system", "content": self.COMPLEXITY_SYSTEM_PROMPT.format(
                current_year=datetime.now().year)},
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
        
        result = self._parse_plan_json_object(text)
        if result.get("mode") not in {"script", "project"}:
            raise ValueError("assessment requires mode=script|project")
        if result.get("deliverable_type") not in {"python", "web_app"}:
            raise ValueError("assessment requires deliverable_type=python|web_app")
        if not isinstance(result.get("needs_research"), bool):
            raise ValueError("assessment requires boolean needs_research")
        queries = result.get("research_queries", [])
        if not isinstance(queries, list) or not all(isinstance(q, str) and q.strip() for q in queries):
            raise ValueError("assessment requires an array of research queries")
        return {**result, "research_queries": queries[:3]}
    
    async def _plan_maintenance(self, plan, user_request, deliverable):
        """Approve the repair objective, not an architect's guessed file list."""
        from ..memory.shared import SharedMemory
        from ..project_inspection import digest
        from ..verification.contracts import draft_contracts
        data = plan.original_task.payload
        if data.get('local_project') is not None:
            return await self._plan_attached_maintenance(plan, user_request, deliverable)
        log_dir = getattr(getattr(self.bus, 'logger', None), 'log_dir', None)
        marker = SubTask(id=plan.id + '_maintenance', description='Inspect and maintain existing project',
            brain_target='web_app_brain' if deliverable == 'web_app' else 'python_brain',
            payload={'type': 'maintain_project', 'user_request': user_request})
        target = resolve_target(plan.id, data, [marker], partial_project_check=lambda path:
            bool(log_dir) and SharedMemory(log_dir).owns_partial_project(data.get('session_id'), path))
        if not target or target.mode != 'existing':
            raise ValueError('Maintenance requires an explicit existing project')
        manifest_path = target.file('.project.json')
        raw = manifest_path.read_text() if manifest_path.is_file() else '{}'
        manifest = json.loads(raw)
        declared = manifest.get('deliverable_type')
        if declared and declared != deliverable:
            raise ValueError('Requested specialist differs from existing project deliverable; explicit migration required')
        entry = manifest.get('entry_point')
        if entry is not None:
            target.file(entry)
        decisions = data.get('test_changes', [])
        if not isinstance(decisions, list) or len(decisions) > 20:
            raise ValueError('Invalid proposed validation changes')
        from ..maintenance import ProjectTools, protected_test
        for decision in decisions:
            if not isinstance(decision, dict) or not all(isinstance(decision.get(k), str) and decision[k].strip()
                    for k in ('path', 'reason', 'expected_behavior', 'authority')):
                raise ValueError('Validation changes require path, reason, expected_behavior and authority')
            ProjectTools(target).path(decision['path'])
            if not protected_test(decision['path']):
                raise ValueError('Validation decision must identify a validation file')
        spec = ProjectSpec(project_name=target.directory.name, description=user_request,
            deliverable_type=deliverable, entry_point=entry,
            interaction_mode=manifest.get('interaction_mode', 'browser' if deliverable == 'web_app' else 'cli'),
            web_stack=manifest.get('web_stack', 'static'),
            executable=manifest.get('interaction_mode') != 'library',
            tech_decisions=['Preserve existing project stack; investigate before choosing implementation changes'],
            execution_strategy='Reproduce, patch minimally, run project checks and independent acceptance review',
            test_changes=decisions)
        proposed = await draft_contracts(self.llm_provider, user_request, project_spec=spec)
        spec.acceptance_contracts = [c for c in proposed if not c.startswith('[Stack]')]
        if not spec.acceptance_contracts:
            raise ValueError('No checkable maintenance objective; do not execute')
        marker.payload.update(project_name=spec.project_name, entry_point=entry, executable=spec.executable,
            deliverable_type=deliverable, web_stack=spec.web_stack, interaction_mode=spec.interaction_mode,
            _maintenance_manifest_sha=digest(raw))
        plan.execution_target, plan.project_spec = target, spec
        return [marker]

    async def _plan_attached_maintenance(self, plan, user_request, deliverable):
        """Prepare local inventory consent before specialist source inspection."""
        from ..local_projects import default_registry, ProjectAccessError
        from ..local_project_transmission import prepare_source_consent, provider_recipient
        from ..verification.contracts import draft_contracts
        if deliverable != 'python':
            raise ProjectAccessError('Attached web specialist integration is pending')
        data = plan.original_task.payload
        scope = data['local_project']
        if (not isinstance(scope, dict) or set(scope) != {'project_id', 'revision'}
                or not isinstance(scope['project_id'], str) or type(scope['revision']) is not int):
            raise ProjectAccessError('An attached project ID and grant revision are required')
        registry = default_registry()
        for right in ('read', 'write', 'execute', 'transmit'):
            with registry.access(scope['project_id'], scope['revision'], right):
                pass
        resolver = getattr(self, 'specialist_provider', None)
        provider = resolver('python_brain') if resolver else None
        consent = prepare_source_consent(registry, scope['project_id'], scope['revision'],
                                         provider_recipient(provider))
        entry = data.get('entry_point')
        if not isinstance(entry, str) or entry not in consent['source_versions']:
            raise ProjectAccessError('Select an entry point from the attached source inventory')
        if data.get('test_changes'):
            raise ProjectAccessError('Attached validation changes require a dedicated approval proposal')
        project = registry.get(scope['project_id'])
        spec = ProjectSpec(project_name=project['name'], description=user_request,
            deliverable_type='python', entry_point=entry, interaction_mode='cli', executable=True,
            tech_decisions=['Preserve existing stack and source behavior'],
            execution_strategy='Reproduce, repair and independently verify in an isolated copy')
        contracts = await draft_contracts(self.llm_provider, user_request, project_spec=spec)
        spec.acceptance_contracts = [c for c in contracts if not c.startswith('[Stack]')]
        if not spec.acceptance_contracts:
            raise ProjectAccessError('Attached maintenance requires checkable acceptance criteria')
        plan.local_project, plan.source_transmission, plan.project_spec = dict(scope), consent, spec
        return [SubTask(id=plan.id + '_maintenance', description='Inspect and repair attached Python project',
            brain_target='python_brain', payload={'type': 'maintain_project', 'user_request': user_request,
                'local_project': dict(scope), 'deliverable_type': 'python', 'entry_point': entry,
                'executable': True, 'interaction_mode': 'cli'})]

    async def _plan_project(self, plan_id: str, user_request: str,
                            needs_research: bool, research_queries: list,
                            deliverable_type: Optional[str] = None,
                            session_id: Optional[str] = None,
                            plan: Optional[TaskPlan] = None) -> List[SubTask]:
        """Plan a multi-file project using the Architect Phase and build a task DAG.
        
        Pipeline:
        1. Research tasks (if needed) — dispatched to researcher brain
        2. Architect Phase — produces detailed ProjectSpec with data models,
           interface contracts, and per-file specs
        3. File-writing tasks — each worker gets rich context (its FileSpec +
           upstream dependency specs rendered as readable text)
        4. Assembler task — wires everything together and runs

        The architect phase is the key improvement: instead of telling a worker
        "write auth.py with purpose: authentication", we tell it exactly which
        functions to implement, what signatures they need, what data models
        exist, and what the upstream dependencies export.
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
        
        # Step 2: Architect Phase — produce detailed ProjectSpec
        # NOTE: Research results are not available yet at planning time
        # (they're async subtasks). The architect works from the user request.
        # Future: two-phase planning where research feeds into architect.
        architect = ArchitectPhase(
            llm_provider=self.llm_provider,
            model=self.planner_model,
        )

        await self.bus.broadcast_event(
            source=self.name,
            event_type="planning.architect_started",
            payload={"request": user_request[:200], "session_id": session_id},
            workspace=self.workspace,
            priority=Priority.NORMAL,
        )

        started = time.monotonic()
        if plan:
            task_data = plan.original_task.payload or {}
            choice = task_data.get('project_target')
            if task_data.get('project_path') or isinstance(choice, dict) and choice.get('mode') == 'existing':
                from ..memory.shared import SharedMemory
                from ..project_inspection import inspect_project, diagnose_project
                log_dir = getattr(getattr(self.bus, 'logger', None), 'log_dir', None)
                try:
                    target = resolve_target(plan_id, task_data,
                        [SubTask(id='inspect', description='Inspect existing project', brain_target='python_brain', payload={'type': 'search_project'})],
                        partial_project_check=lambda path: bool(log_dir) and SharedMemory(log_dir).owns_partial_project(session_id, path))
                    plan.execution_target = target
                    await self._planning_progress('inspection', 'running', session_id, task_id=plan_id)
                    plan.inspection = await asyncio.to_thread(inspect_project, target)
                    plan.inspection['baseline'] = await diagnose_project(target, plan.inspection)
                    await self._planning_progress('inspection', 'done', session_id, started, task_id=plan_id)
                except (ValueError, OSError) as exc:
                    raise PlanningError('inspection', str(exc), plan_id) from exc
        # The architect owns ONE total deadline, including its optional repair.
        # Report real elapsed waiting time, never fictional percentage progress.
        design_task = asyncio.create_task(
            architect.design(user_request, expected_deliverable=deliverable_type,
                **({'existing_project': plan.inspection} if plan and plan.inspection else {})))
        try:
            while True:
                done, _ = await asyncio.wait({design_task}, timeout=PLANNING_HEARTBEAT_SECONDS)
                if done:
                    spec: ProjectSpec = design_task.result()
                    break
                await self._planning_progress("architect", "running", session_id, started, task_id=plan_id)
        finally:
            if not design_task.done():
                design_task.cancel()
            await asyncio.gather(design_task, return_exceptions=True)

        project_name = spec.project_name
        if spec.workspace_widgets:
            from .widget_proposals import widget_proposal
            await self.bus.broadcast_event(
                source=self.name, event_type='workspace.proposal',
                payload={'session_id': session_id, 'task_id': plan_id,
                         'producer': 'architect', 'proposal': widget_proposal(spec.workspace_widgets)},
                workspace=self.workspace, priority=Priority.NORMAL)
        worker_brain = "web_app_brain" if spec.deliverable_type == "web_app" else "python_brain"
        
        logger.info("Architect spec: %s — %d files, %d data models",
                     project_name, len(spec.file_specs), len(spec.data_models))
        
        await self.bus.broadcast_event(
            source=self.name,
            event_type="planning.project_structure",
            payload={
                "project_name": project_name,
                "files": [fs.path for fs in spec.file_specs],
                "total_files": len(spec.file_specs),
                "data_models": [dm.name for dm in spec.data_models],
                "tech_decisions": spec.tech_decisions,
                "executable": spec.executable,
                "entry_point": spec.entry_point,
                "deliverable_type": spec.deliverable_type,
                "interaction_mode": spec.interaction_mode,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            },
            workspace=self.workspace,
            priority=Priority.NORMAL,
        )
        
        # Step 3: Build subtask DAG from architect spec
        # Use topological order so dependencies are dispatched first
        ordered_specs = spec.dependency_order()
        kept_hashes = {fs.path: plan.inspection['sources'][fs.path]['sha256']
            for fs in ordered_specs if fs.operation == 'keep' and plan and plan.inspection}

        # Map file paths to subtask IDs
        file_to_sid = {}
        for fs in ordered_specs:
            if fs.operation == 'keep':
                continue
            sid = f"{plan_id}_s{task_idx}"
            file_to_sid[fs.path] = sid
            task_idx += 1
        
        # Create file-writing subtasks with RICH context from architect
        for fs in ordered_specs:
            if fs.operation == 'keep':
                continue
            sid = file_to_sid[fs.path]
            
            # Resolve dependencies: file deps + research deps
            deps = set(research_dep_ids)  # All file tasks wait for research
            for dep_path in fs.dependencies:
                dep_sid = file_to_sid.get(dep_path)
                if dep_sid:
                    deps.add(dep_sid)
            
            # Render rich worker prompt from the FileSpec + upstream specs
            upstream_specs = spec.get_upstream_specs(fs)
            worker_spec_text = fs.render_for_worker(upstream_specs=upstream_specs)

            # Build all_files summary for backward compat with PythonBrain
            all_files = [
                {
                    "path": f.path,
                    "purpose": f.purpose,
                    "exports": [e.name for e in f.exports],
                    "dependencies": f.dependencies,
                }
                for f in spec.file_specs
            ]

            subtasks.append(SubTask(
                id=sid,
                description=f"Write {fs.path}: {fs.purpose}",
                brain_target=worker_brain,
                payload={
                    "type": "write_web_file" if spec.deliverable_type == "web_app" else "write_project_file",
                    "web_stack": spec.web_stack,
                    "user_request": user_request,
                    "project_name": project_name,
                    "file_path": fs.path,
                    "purpose": fs.purpose,
                    "exports": [e.name for e in fs.exports],
                    "dependencies": fs.dependencies,
                    "all_files": all_files,
                    # NEW: rich architect spec for the worker
                    "architect_spec": worker_spec_text,
                    "implementation_notes": fs.implementation_notes,
                    "edge_cases": fs.edge_cases,
                    "acceptance_contracts": list(spec.acceptance_contracts),
                    "_existing_source": plan.inspection['sources'].get(fs.path) if plan and plan.inspection and fs.operation == 'modify' else None,
                    "_create_only": bool(plan and plan.inspection and fs.operation == 'create'),
                    "_kept_hashes": kept_hashes,
                    "_existing_dependencies": {p: {'file_path': p, 'file_content': plan.inspection['sources'][p]['content']}
                        for p in fs.dependencies if plan and plan.inspection and p in plan.inspection['sources']
                        and plan.inspection['sources'][p]['complete']},
                },
                dependencies=deps,
            ))
        
        # Step 4: Add assembler task — wires everything together and runs
        all_file_sids = set(file_to_sid.values())
        assembler_sid = f"{plan_id}_s{task_idx}"

        all_files_summary = [
            {"path": f.path, "purpose": f.purpose, "dependencies": f.dependencies}
            for f in spec.file_specs
        ]

        subtasks.append(SubTask(
            id=assembler_sid,
            description=f"Assemble and {'run' if spec.executable else 'validate'} {project_name}",
            brain_target=worker_brain,
            payload={
                "type": "assemble_and_preview" if spec.deliverable_type == "web_app" else "assemble_and_run",
                "web_stack": spec.web_stack,
                "user_request": user_request,
                "project_name": project_name,
                "all_files": all_files_summary,
                "executable": spec.executable,
                "entry_point": spec.entry_point,
                "execution_strategy": spec.execution_strategy,
                "deliverable_type": spec.deliverable_type,
                "interaction_mode": spec.interaction_mode,
                "_editable_paths": [fs.path for fs in spec.file_specs if fs.operation != 'keep'] if plan and plan.inspection else None,
                "_kept_hashes": kept_hashes,
                "acceptance_contracts": list(spec.acceptance_contracts) + [f"Test decision: {json.dumps(item, ensure_ascii=False)}" for item in spec.test_changes],
                "baseline_diagnostic": plan.inspection.get('baseline') if plan and plan.inspection else None,
            },
            dependencies=all_file_sids,
        ))
        
        # Store spec on the plan for later reference (integration/review phases)
        # Attached as instance attribute on the plan after creation in caller
        if plan is not None:
            plan.project_spec = spec
        
        return subtasks

    async def _plan_project_legacy(self, plan_id: str, user_request: str,
                                    needs_research: bool, research_queries: list,
                                    task_idx: int = 0,
                                    research_dep_ids: list = None,
                                    existing_subtasks: list = None) -> List[SubTask]:
        """Legacy project planner (fallback if architect phase fails).
        
        Uses the simpler PROJECT_PLANNER_PROMPT that only produces
        file paths + purposes without detailed interface contracts.
        """
        if research_dep_ids is None:
            research_dep_ids = []
        # Carry over research subtasks created by _plan_project before fallback
        subtasks = list(existing_subtasks) if existing_subtasks else []

        # Plan file structure (legacy prompt)
        messages = [
            {"role": "system", "content": self.PROJECT_PLANNER_PROMPT},
            {"role": "user", "content": f"[Current year: {datetime.now().year}] {user_request}"},
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
            raise ValueError("Legacy project planner returned no files")
        
        logger.info("Legacy project plan: %s — %d files", project_name, len(files))
        
        await self.bus.broadcast_event(
            source=self.name,
            event_type="planning.project_structure",
            payload={
                "project_name": project_name,
                "files": [f.get("path") for f in files],
                "total_files": len(files),
            },
            workspace=self.workspace,
            priority=Priority.NORMAL,
        )
        
        # Build subtask DAG
        file_to_sid = {}
        for f in files:
            sid = f"{plan_id}_s{task_idx}"
            file_to_sid[f["path"]] = sid
            task_idx += 1
        
        for f in files:
            sid = file_to_sid[f["path"]]
            deps = set(research_dep_ids)
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
                    "all_files": files,
                },
                dependencies=deps,
            ))
        
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
        # Build brain list for the system prompt.
        # Show logical pool names (e.g. "python_brain") not individual workers
        # so the planner uses the pool name and the orchestrator resolves to a worker.
        brain_descriptions = []
        pool_logicals_shown = set()
        
        for name, caps in self.registered_brains.items():
            # Check if this brain belongs to a pool
            pool_logical = None
            for logical, workers in self.brain_pools.items():
                if name in workers:
                    pool_logical = logical
                    break
            
            if pool_logical:
                # Only show the logical name once, with pool size hint
                if pool_logical not in pool_logicals_shown:
                    desc = caps.get("description", pool_logical)
                    pool_size = len(self.brain_pools[pool_logical])
                    brain_descriptions.append(f"- {pool_logical}: {desc} (pool of {pool_size} — can handle {pool_size} tasks in parallel)")
                    pool_logicals_shown.add(pool_logical)
            else:
                desc = caps.get("description", name)
                brain_descriptions.append(f"- {name}: {desc}")
        
        if not brain_descriptions:
            brain_descriptions = [
                "- python_brain: Generates and executes Python code",
                "- researcher: Researches topics, gathers information, analyzes data",
            ]
        
        brain_list = "\n".join(brain_descriptions)
        system = self.SIMPLE_PLANNER_PROMPT.format(
            brain_list=brain_list, current_year=datetime.now().year)
        
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
            if (not isinstance(sd, dict) or not isinstance(sd.get("brain_target"), str)
                    or not sd["brain_target"] or not isinstance(sd.get("payload"), dict)
                    or not sd["payload"].get("type")):
                raise ValueError("Every planned action requires an explicit brain and typed payload")
            sid = sd.get("id", f"{plan_id}_{len(subtasks)}")
            # Prefix subtask IDs with plan_id for global uniqueness
            full_id = f"{plan_id}_{sid}"
            
            deps = set()
            for dep in sd.get("dependencies", []):
                deps.add(f"{plan_id}_{dep}")
            
            subtask = SubTask(
                id=full_id,
                description=sd.get("description", ""),
                brain_target=sd["brain_target"],
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
        """Fallback: simple deterministic task routing (no LLM needed).

        Only explicit action types are safe without planning. Never infer
        Python from an unknown or compound request.
        """
        task_type = task_data.get("type", "unknown")
        
        brain_map = {
            "execute_code": "python_brain",
            "generate_and_execute": "python_brain",
            "run_file": "python_brain",
            "run_web_project": "web_app_brain",
            "research": "researcher",
            "web_search": "researcher",
            "board_task": "taskboard",
            "create_task": "taskboard",
        }
        
        if task_type in brain_map:
            target = brain_map[task_type]
            payload = task_data
        else:
            raise ValueError(f"No explicit action route for {task_type!r}")
        
        return [SubTask(
            id=f"{plan_id}_s0",
            description=f"Execute {payload.get('type', task_type)} task",
            brain_target=target,
            payload=payload,
        )]

    def _choose_brain_for_task(self, task_type: str) -> str:
        """Choose the best brain for a task type based on load balancing."""
        # Find least loaded registered brain
        if self.registered_brains:
            available = list(self.registered_brains.keys())
            return min(available, key=lambda b: self.brain_load.get(b, 0))
        return "python_brain"  # Last resort fallback
    
    async def _execute_ready_subtasks(self, plan: TaskPlan, _depth: int = 0) -> None:
        """Execute all subtasks that are ready (dependencies satisfied).
        
        Respects brain capacity: only dispatches to brains that aren't at max load.
        Re-checks plan status between dispatches to avoid sending tasks after failure.
        Deferred subtasks (brain busy) are retried on next _execute_ready_subtasks call.
        """
        # Don't dispatch if plan is already complete/failed
        if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED):
            print(f"[ORCH] Skipping _execute_ready_subtasks: plan {plan.id[-8:]} is {plan.status.value}")
            return
        
        # Contract gate: nothing dispatches until the user approves.
        if plan.awaiting_approval:
            print(f"[ORCH] Plan {plan.id[-8:]} awaits contract approval — not dispatching")
            return

        if plan.execution_target is not None:
            try:
                plan.execution_target = plan.execution_target.prepare()
                if not plan.transaction and self._requires_new_delivery(plan):
                    from ..project_transaction import ProjectTransaction
                    paths = {f.path for f in plan.project_spec.file_specs} if plan.project_spec else set()
                    for st in plan.subtasks:
                        if st.payload.get('file_path'):
                            paths.add(st.payload['file_path'].removeprefix(plan.execution_target.path + '/'))
                        if st.payload.get('type') == 'batch_write_files':
                            paths.update(f['path'] for f in st.payload.get('files', []) if isinstance(f, dict))
                        if st.payload.get('type') == 'generate_and_execute':
                            from ..verification.evidence import default_repository
                            ref = st.payload.get('contract_revision', {})
                            approved = default_repository().load_spec(ref.get('design_id', ''), ref.get('revision', 0))
                            if not approved or 'delivery' not in approved.metadata:
                                raise ValueError('Code generation requires an approved delivery architecture')
                            paths.add(approved.metadata['delivery'].get('entry_point') or st.payload.get('file_path') or 'main.py')
                    plan.transaction = str(ProjectTransaction.begin(plan.execution_target, sorted(paths)).journal)
                if not plan.transaction and plan.execution_target.mode == 'existing':
                    paths = [st.payload['file_path'].removeprefix(plan.execution_target.path + '/') for st in plan.subtasks
                             if st.payload.get('type') in {'edit_file', 'write_project_file', 'write_web_file'}
                             and st.payload.get('file_path')]
                    if paths or any(st.payload.get('type') == 'maintain_project' for st in plan.subtasks):
                        from ..project_transaction import ProjectTransaction
                        plan.transaction = str(ProjectTransaction.begin(plan.execution_target, paths).journal)
            except (ValueError, OSError) as exc:
                pending = next((st for st in plan.subtasks if st.status in {TaskStatus.PENDING, TaskStatus.RUNNING}), None)
                if pending is not None:
                    pending.status = TaskStatus.FAILED
                    pending.error = f"Destination invalide : {exc}"
                    await self._check_plan_completion(plan)
                return
        
        # Prevent re-entrant execution (bus delivers synchronously, so a dispatched
        # task can complete and trigger another _execute_ready_subtasks before we return)
        if getattr(plan, '_dispatching', False):
            return
        plan._dispatching = True
        
        try:
            ready_subtasks = plan.get_ready_subtasks()
            print(f"[ORCH] _execute_ready_subtasks: plan={plan.id[-8:]} status={plan.status.value} ready={len(ready_subtasks)} total={len(plan.subtasks)}")
            
            # Handle execution mode: "todo" mode executes sequentially (one task at a time)
            if plan.execution_mode == "todo" and ready_subtasks:
                # In todo mode: respect dependency order but don't parallelize
                # Only dispatch the first ready task (or one that's already running)
                running_count = sum(1 for st in plan.subtasks if st.status == TaskStatus.RUNNING)
                if running_count > 0:
                    print(f"[ORCH] Todo mode: {running_count} task(s) running, waiting for completion")
                    return  # Wait for current task to finish
                ready_subtasks = ready_subtasks[:1]  # Only first ready task
                print(f"[ORCH] Todo mode: dispatching single task: {ready_subtasks[0].description[:60]}")
            
            deferred = 0
            busy_rejected = 0  # Track dispatches that got busy-rejected (synchronous)
            for subtask in ready_subtasks:
                # Re-check plan status — a prior dispatch may have caused a failure
                # via synchronous bus delivery (brain rejects → result → plan fails)
                if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    print(f"[ORCH] Stopping dispatch: plan {plan.id[-8:]} became {plan.status.value}")
                    break
                
                # Resolve logical brain name to actual worker (pool-aware).
                # Use the ORIGINAL logical name (stored on first encounter) so we
                # always resolve fresh against the pool, not a previously assigned worker.
                logical_name = getattr(subtask, '_logical_brain', None) or subtask.brain_target
                if not hasattr(subtask, '_logical_brain'):
                    subtask._logical_brain = subtask.brain_target
                
                resolved_brain = self._resolve_brain_target(logical_name)
                
                # For pool workers: skip dead brains to avoid dispatching into the void.
                # Only applies to pools — direct brain targets are trusted.
                if (logical_name in self.brain_pools and 
                    self._alive_brains and 
                    resolved_brain not in self._alive_brains):
                    # Try other alive workers in the pool
                    found_alive = False
                    for w in self.brain_pools[logical_name]:
                        if w in self._alive_brains and self.brain_load.get(w, 0) < 1:
                            resolved_brain = w
                            found_alive = True
                            break
                    if not found_alive:
                        print(f"[ORCH] Deferring {subtask.id[-12:]} — no alive {logical_name} workers available")
                        deferred += 1
                        continue
                
                # Respect brain capacity — don't dispatch if this worker is busy
                current_load = self.brain_load.get(resolved_brain, 0)
                max_concurrent = 1  # Each worker handles 1 task at a time
                if current_load >= max_concurrent:
                    # Try other workers in the pool before deferring
                    if logical_name in self.brain_pools:
                        found_free = False
                        for w in self.brain_pools[logical_name]:
                            if (w in self._alive_brains or not self._alive_brains) and \
                               self.brain_load.get(w, 0) < max_concurrent:
                                resolved_brain = w
                                found_free = True
                                break
                        if not found_free:
                            print(f"[ORCH] Deferring {subtask.id[-12:]} — all {logical_name} workers busy")
                            deferred += 1
                            continue
                    else:
                        print(f"[ORCH] Deferring {subtask.id[-12:]} — {resolved_brain} at capacity ({current_load}/{max_concurrent})")
                        deferred += 1
                        continue
                
                # Set the resolved worker for dispatch
                subtask.brain_target = resolved_brain
                
                print(f"[ORCH] Dispatching subtask {subtask.id[-12:]} → brain={resolved_brain} type={subtask.payload.get('type')} desc={subtask.description[:60]}")
                await self._dispatch_subtask(plan, subtask)
                
                # Check if the subtask was busy-rejected (synchronous bus delivery
                # means the busy handler already reset it to PENDING before we get here)
                if subtask.status == TaskStatus.PENDING:
                    busy_rejected += 1
            
            if deferred > 0:
                print(f"[ORCH] {deferred} subtask(s) deferred — will retry when brains free up")
            if busy_rejected > 0:
                print(f"[ORCH] {busy_rejected} subtask(s) busy-rejected — will retry when brains free up")
        finally:
            plan._dispatching = False
        
        # Synchronous bus delivery means subtasks may have completed DURING the
        # loop above (via re-entrant result handlers that were blocked by the guard).
        # Their completions may have unlocked NEW ready subtasks. Re-check once.
        # BUT: only re-check if we actually dispatched something (not all deferred
        # or busy-rejected). Otherwise we spin forever trying to dispatch to busy brains.
        # Safety: limit recursion depth to 3 to prevent infinite busy→re-queue loops
        # (can happen if _current_task clear races with result delivery).
        dispatched_count = len(ready_subtasks) - deferred - busy_rejected
        if plan.status == TaskStatus.RUNNING and dispatched_count > 0 and _depth < 3:
            new_ready = plan.get_ready_subtasks()
            if new_ready:
                print(f"[ORCH] Post-loop: {len(new_ready)} new subtask(s) became ready during dispatch")
                await self._execute_ready_subtasks(plan, _depth=_depth + 1)
    
    async def _dispatch_subtask(self, plan: TaskPlan, subtask: SubTask) -> None:
        """Dispatch a subtask to the appropriate brain.
        
        Only broadcasts subtask.started once per subtask (not on re-dispatch
        after busy rejection). This prevents WS flooding when a brain is busy
        and the orchestrator retries in a tight loop.
        """
        import time
        
        # Update subtask status
        subtask.status = TaskStatus.RUNNING
        subtask.start_time = time.time()
        subtask.assigned_brain = subtask.brain_target
        
        # Classify risk level
        risk_level = classify_risk(subtask.payload)
        risk_description = get_risk_description(risk_level)
        
        logger.info("Subtask %s risk level: %s (%s)", subtask.id[-12:], risk_level.value, risk_description)
        
        # Update TaskTracker
        if plan.tracker:
            from .task_tracker import TaskStatus as TrackerStatus
            plan.tracker.update_status(subtask.id, TrackerStatus.IN_PROGRESS)
        
        # Update brain load
        self.brain_load[subtask.brain_target] = self.brain_load.get(subtask.brain_target, 0) + 1
        
        # Resolve any variable references in payload
        resolved_payload = await self._resolve_payload_references(subtask.payload, plan)
        resolved_payload.pop('_transaction', None)  # runtime-owned, never an LLM capability
        resolved_payload.pop('_approved_test_paths', None)
        for runtime_only in ('_maintenance_runtime_evidence', '_maintenance_mode', '_diagnostic_only'):
            resolved_payload.pop(runtime_only, None)
        if subtask.payload.get('type') == 'maintain_project' and plan.approval_design_id:
            from ..verification.evidence import default_repository
            ref = subtask.payload.get('contract_revision', {})
            approved = default_repository().load_spec(ref.get('design_id', ''), ref.get('revision', 0))
            if approved and approved.metadata.get('approval', {}).get('decision') == 'approved':
                resolved_payload['_approved_test_paths'] = [d['path'] for d in
                    approved.metadata.get('maintenance', {}).get('test_changes', [])]
        if subtask.payload.get("type") in FILE_TASKS and plan.execution_target is not None:
            resolved_payload["_execution_target"] = plan.execution_target.to_payload()
            if plan.transaction:
                resolved_payload['_transaction'] = plan.transaction
        if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED):
            self.brain_load[subtask.brain_target] = max(0, self.brain_load.get(subtask.brain_target, 0) - 1)
            return
        
        # Inject current task tracker state so brain knows full context
        if plan.tracker:
            resolved_payload["_task_state"] = plan.tracker.render_for_prompt()
        
        # Inject user interjections if any
        if hasattr(plan, "user_interjections") and plan.user_interjections:
            # Include most recent interjection
            latest_interjection = plan.user_interjections[-1]["message"]
            resolved_payload["_user_interjection"] = latest_interjection
            # Clear interjections after inclusion
            plan.user_interjections.clear()
        
        # Send task to brain
        task_message = BusMessage(
            type=MessageType.TASK,
            source=self.name,
            target=subtask.brain_target,
            workspace=self.workspace,
            project=plan.original_task.project,
            payload={**resolved_payload, "_subtask_id": subtask.id, "_plan_id": plan.id,
                     "session_id": (plan.original_task.payload or {}).get('session_id')},
            reply_to=subtask.id  # Informational — not used for result matching
        )
        
        # Track by BusMessage ID — this is what brain.send_result uses as reply_to
        self.active_subtasks[task_message.id] = plan.id
        # Also map message ID → subtask ID for lookup
        subtask._dispatch_msg_id = task_message.id
        
        # Only broadcast subtask.started ONCE per subtask. Re-dispatches after
        # busy rejection should NOT re-announce — otherwise the WS client gets
        # flooded with thousands of started events in a tight retry loop.
        if not getattr(subtask, '_started_announced', False):
            subtask._started_announced = True
            await self.bus.broadcast_event(
                source=self.name,
                event_type="subtask.started",
                payload={
                    "task_id": plan.id,
                    "subtask_id": subtask.id,
                    "session_id": (plan.original_task.payload or {}).get('session_id'),
                    "brain": subtask.brain_target,
                    "description": subtask.description,
                    "risk_level": risk_level.value,
                    "risk_description": risk_description
                },
                workspace=self.workspace,
                priority=Priority.NORMAL
            )
        
        if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED):
            if self.active_subtasks.pop(task_message.id, None) is not None:
                self.brain_load[subtask.brain_target] = max(0, self.brain_load.get(subtask.brain_target, 0) - 1)
            return
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
        # so downstream brains have full picture even without explicit refs.
        # Key by file_path when available (for write_project_file results)
        # so PythonBrain can match upstream code to dependency file paths.
        if results:
            upstream = {}
            for st in plan.subtasks:
                if st.status == TaskStatus.COMPLETE and st.result:
                    result = result_data(st.result)
                    # Use file_path as key if available (file-writing tasks)
                    key = None
                    if isinstance(result, dict) and result.get("file_path"):
                        key = result["file_path"]
                    if not key:
                        # Fallback: brain_name:description
                        brain_name = st.assigned_brain or st.brain_target
                        key = f"{brain_name}:{st.description[:80]}"
                    upstream[key] = result
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
            
            # Update TaskTracker - reset to PENDING
            if plan.tracker:
                from .task_tracker import TaskStatus as TrackerStatus
                plan.tracker.update_status(subtask.id, TrackerStatus.PENDING)
            
            # Remove from active tracking
            del self.active_subtasks[dispatch_msg_id]
            
            # Don't announce failure or check plan completion — just return.
            # The subtask will be retried when the next subtask completes
            # and triggers _execute_ready_subtasks.
            return
        
        # ── Normal result handling ──
        subtask.end_time = time.time()
        subtask.result = result_data(message.payload)
        
        if subtask.result.get("success", False):
            subtask.status = TaskStatus.COMPLETE
        else:
            subtask.status = TaskStatus.FAILED
            subtask.error = subtask.result.get("error", "Unknown error")
        
        # Update TaskTracker
        if plan.tracker:
            from .task_tracker import TaskStatus as TrackerStatus
            if subtask.status == TaskStatus.COMPLETE:
                result_summary = None
                if subtask.result and isinstance(subtask.result, dict):
                    if 'stdout' in subtask.result:
                        result_summary = subtask.result['stdout'][:100] if subtask.result['stdout'] else "completed"
                    elif 'file_path' in subtask.result:
                        result_summary = f"wrote {subtask.result['file_path']}"
                    else:
                        result_summary = "completed"
                plan.tracker.update_status(subtask.id, TrackerStatus.COMPLETE, result_summary)
            else:
                plan.tracker.update_status(subtask.id, TrackerStatus.FAILED, subtask.error)
            
            # Broadcast task tracker update for UI
            await self.bus.broadcast_event(
                source=self.name,
                event_type="task_tracker.updated",
                payload=plan.tracker.to_ws_event()["data"],
                workspace=self.workspace,
                priority=Priority.LOW
            )
        
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
                "session_id": (plan.original_task.payload or {}).get('session_id'),
                "status": subtask.status.value,
                "execution_time": subtask.end_time - subtask.start_time if subtask.start_time else 0
            },
            workspace=self.workspace,
            priority=Priority.NORMAL
        )
        
        # Check context limits and compact if needed
        self._check_context_limits(plan)
        
        # Check if entire plan is complete FIRST (before trying to start more)
        await self._check_plan_completion(plan)
        
        # Start more subtasks if plan is still running
        # (includes previously deferred/busy-rejected subtasks that are now PENDING again)
        if subtask.status == TaskStatus.COMPLETE and plan.status == TaskStatus.RUNNING:
            await self._execute_ready_subtasks(plan)
        
        # Also check OTHER running plans — a freed worker may unblock deferred
        # subtasks in plans that were starved while this brain was busy.
        for other_plan in list(self.task_plans.values()):
            if other_plan.id == plan.id:
                continue
            if other_plan.status != TaskStatus.RUNNING:
                continue
            other_ready = other_plan.get_ready_subtasks()
            if other_ready:
                await self._execute_ready_subtasks(other_plan)
    
    @staticmethod
    def _requires_new_delivery(plan: TaskPlan) -> bool:
        return bool(plan.execution_target and plan.execution_target.mode == 'new' and
            (plan.project_spec or any(st.payload.get('type') in {
                'write_project_file', 'batch_write_files', 'write_web_file',
                'assemble_and_run', 'assemble_and_preview', 'generate_and_execute'} for st in plan.subtasks)))

    def _append_delivery_gate(self, plan: TaskPlan) -> None:
        """File generation is an intermediate step, including native plans."""
        from ..verification.evidence import default_repository
        ref = next((st.payload['contract_revision'] for st in plan.subtasks if st.payload.get('contract_revision')), None)
        if not ref:
            raise ValueError('New project needs an approved contract before delivery verification')
        approved = default_repository().load_spec(ref['design_id'], ref['revision'])
        if not approved or approved.metadata.get('approval', {}).get('decision') != 'approved':
            raise ValueError('New project contract is not approved')
        declaration = approved.metadata.get('delivery', {})
        kind = declaration.get('deliverable_type') or (
            'web_app' if any(st.payload.get('type') == 'write_web_file' for st in plan.subtasks) else 'python')
        executable = declaration.get('executable', True)
        entry = declaration.get('entry_point') or next((st.payload.get('entry_point') for st in plan.subtasks
                                                       if st.payload.get('entry_point')), None)
        if executable and not entry:
            raise ValueError('New project has no approved runnable entry point')
        paths = {f.path for f in plan.project_spec.file_specs} if plan.project_spec else set()
        for st in plan.subtasks:
            if st.payload.get('file_path'):
                paths.add(st.payload['file_path'].removeprefix(plan.execution_target.path + '/'))
            if st.payload.get('type') == 'batch_write_files':
                paths.update(f['path'] for f in st.payload.get('files', []) if isinstance(f, dict))
        plan.subtasks.append(SubTask(id=plan.id + '_delivery', description='Vérifier et finaliser le livrable',
            brain_target='web_app_brain' if kind == 'web_app' else 'python_brain',
            payload={'type': 'assemble_and_preview' if kind == 'web_app' else 'assemble_and_run',
                'project_name': plan.execution_target.directory.name, 'user_request': approved.user_request,
                'contract_revision': ref, 'business_contracts': approved.metadata.get('business_criteria', []),
                'deliverable_type': kind, 'executable': executable, 'entry_point': entry,
                'web_stack': declaration.get('web_stack', 'static'),
                'interaction_mode': approved.metadata.get('execution', {}).get('interaction_mode') or
                    ('browser' if kind == 'web_app' else 'cli' if executable else 'library'),
                'all_files': [{'path': p} for p in sorted(paths)]},
            dependencies={st.id for st in plan.subtasks}))
        if plan.tracker:
            from .task_tracker import TaskTracker
            plan.tracker.tasks.update(TaskTracker.create_from_plan([plan.subtasks[-1]]).tasks)

    async def _check_plan_completion(self, plan: TaskPlan) -> None:
        """Check if a task plan is complete and send final result."""
        # Other in-flight workers can finish after the first fatal failure.
        # A terminal plan must emit exactly one result/terminal event.
        if plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return
        if plan.is_complete() or plan.is_failed():
            delivery = None
            if self._requires_new_delivery(plan) and not plan.is_failed():
                try:
                    gates = [st for st in plan.subtasks if st.payload.get('type') in
                             {'assemble_and_run', 'assemble_and_preview', 'generate_and_execute'}]
                    if not gates:
                        self._append_delivery_gate(plan)
                        await self._execute_ready_subtasks(plan)
                        return
                    gate = gates[-1]
                    from ..verification.delivery import validate
                    delivery = validate(plan.execution_target, gate.payload, result_data(gate.result or {}))
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    plan.subtasks[-1].status = TaskStatus.FAILED
                    plan.subtasks[-1].error = f'Projet incomplet : {exc}'
            import time
            transaction_outcome = None
            if plan.transaction:
                from ..project_transaction import ProjectTransaction
                transaction = ProjectTransaction(plan.transaction)
                try:
                    transaction_outcome = transaction.finish(commit=not plan.is_failed())
                    if transaction_outcome['state'] == 'conflict' and not plan.is_failed():
                        plan.subtasks[-1].status = TaskStatus.FAILED
                        plan.subtasks[-1].error = 'Concurrent project changes prevent transaction commit'
                        transaction_outcome = transaction.finish(commit=False)
                except (OSError, ValueError) as exc:
                    plan.subtasks[-1].status = TaskStatus.FAILED
                    plan.subtasks[-1].error = f'Project transaction recovery required: {exc}'
                    transaction_outcome = {'state': 'recovery_required', 'journal': plan.transaction}
            
            if plan.is_failed():
                plan.status = TaskStatus.FAILED
                # Journal is already fenced/rolled back. Stop sibling workers
                # rather than paying for results that can no longer be committed.
                for dispatch_id, owner in list(self.active_subtasks.items()):
                    if owner != plan.id:
                        continue
                    sibling = next((st for st in plan.subtasks if getattr(st, '_dispatch_msg_id', None) == dispatch_id), None)
                    if sibling and sibling.assigned_brain:
                        await self.bus.send(BusMessage(type=MessageType.CANCEL, source=self.name,
                            target=sibling.assigned_brain, payload={'task_id': dispatch_id, 'mode': 'soft'}))
                        self.brain_load[sibling.assigned_brain] = max(0, self.brain_load.get(sibling.assigned_brain, 0) - 1)
                        sibling.status = TaskStatus.CANCELLED
                    self.active_subtasks.pop(dispatch_id, None)
                failed_subtasks = [st for st in plan.subtasks if st.status == TaskStatus.FAILED]
                plan.error = "; ".join(dict.fromkeys(st.error or "Unknown error" for st in failed_subtasks))[:2000]
                plan.result = {
                    "success": False,
                    "error": plan.error,
                    "failed_subtasks": [{"id": st.id, "error": st.error,
                        "verification": (st.result or {}).get('verification'),
                        "repair_error": (st.result or {}).get('repair_error')}
                        for st in failed_subtasks]
                }
                research_messages = []
                for failed in failed_subtasks:
                    data = result_data(failed.result or {})
                    public = data.get('public_message')
                    if data.get('research_status') == 'partial' and isinstance(public, str) and len(public) <= 3500:
                        research_messages.append(public)
                if research_messages:
                    plan.result['research_messages'] = research_messages[:3]
            else:
                plan.status = TaskStatus.COMPLETE
                plan.result = {
                    "success": True,
                    "results": plan.get_results(),
                    "subtasks_completed": len(plan.subtasks)
                }
            if self._requires_new_delivery(plan):
                plan.result.update(delivery_status='ready' if plan.status == TaskStatus.COMPLETE else 'incomplete',
                                   verified=plan.status == TaskStatus.COMPLETE, runnable=False)
                if delivery and plan.status == TaskStatus.COMPLETE:
                    plan.result.update(delivery, project_delivery=delivery)
            
            # Send final result back to original requester (explicit target)
            if transaction_outcome:
                plan.result['transaction'] = transaction_outcome
            await self.bus.send_result(
                source=self.name,
                target=plan.original_task.source,
                result_data={**plan.result, "session_id": (plan.original_task.payload or {}).get("session_id")},
                reply_to=plan.original_task.id,
                workspace=self.workspace,
                project=plan.original_task.project
            )
            
            # Extract learnings from the completed plan
            await self._extract_learnings(plan)
            
            # Announce plan completion. On failure, carry the real error
            # detail — the UI surfaces it in the chat instead of a bare
            # "Task failed" with no cause.
            fail_payload = {}
            if plan.status == TaskStatus.FAILED:
                failed_subtasks = [st for st in plan.subtasks if st.status == TaskStatus.FAILED]
                fail_payload = {
                    "error": plan.error or "Unknown error",
                    "failed_subtasks": [
                        {"id": st.id, "error": st.error or "Unknown error"}
                        for st in failed_subtasks
                    ][:3],
                }
            await self.bus.broadcast_event(
                source=self.name,
                event_type="task.complete" if plan.status == TaskStatus.COMPLETE else "task.failed",
                payload={
                    "task_id": plan.id,
                    "status": plan.status.value,
                    "workspace": self.workspace,
                    "subtasks_total": len(plan.subtasks),
                    "session_id": (plan.original_task.payload or {}).get("session_id"),
                    **self._project_result_metadata(plan),
                    **fail_payload,
                },
                workspace=self.workspace,
                priority=Priority.NORMAL
            )
    
    @staticmethod
    def _project_result_metadata(plan: TaskPlan) -> dict:
        """Expose only launch/navigation metadata from completed subtasks."""
        if WorkspaceOrchestrator._requires_new_delivery(plan):
            return ((plan.result or {}).get('project_delivery') if plan.status == TaskStatus.COMPLETE else None) or {
                'runnable': False, 'verified': False, 'delivery_status': 'incomplete'}
        if plan.status == TaskStatus.FAILED:
            # A selected older project is not evidence for a failed new run.
            return {"runnable": False}
        if any(st.brain_target == "taskboard" or st.payload.get("type") == "board_task"
               for st in plan.subtasks):
            return {"result_kind": "taskboard", "runnable": False}
        if plan.execution_target is None:
            return {"runnable": False}
        candidates = []
        has_file_output = False
        for result in plan.get_results().values():
            if not isinstance(result, dict):
                continue
            data = result.get("data", result)
            if not isinstance(data, dict):
                continue
            has_file_output |= isinstance(data.get("file_path"), str) and bool(data["file_path"])
            if data.get("project_name") and data.get("entry_point"):
                metadata = {
                    "project_name": data["project_name"],
                    **({"project_path": data["project_path"]} if data.get("project_path") else {}),
                    "entry_point": data["entry_point"],
                    **({"deliverable_type": data["deliverable_type"]}
                       if data.get("deliverable_type") else {}),
                    **({"preview_url": data["preview_url"]}
                       if data.get("preview_url") else {}),
                    "runnable": bool(data.get("success") and (
                        data.get("runnable") is True
                        or data.get("stdout", "").strip()
                        or data.get("server_running") is True
                    )),
                }
                score = (
                    int(metadata["runnable"]),
                    int(bool(data.get("preview_url"))),
                    int(bool(data.get("verification"))),
                )
                candidates.append((score, metadata))
        if candidates:
            metadata = max(candidates, key=lambda item: item[0])[1]
            if plan.execution_target is not None:
                try:
                    plan.execution_target.file(metadata["entry_point"])
                except ValueError:
                    return {"runnable": False}
                metadata.update(project_path=plan.execution_target.path,
                                project_name=plan.execution_target.directory.name)
            return metadata
        if not has_file_output and not any(st.payload.get("type") in {
            "edit_file", "run_file", "write_project_file", "assemble_and_run",
            "batch_write_files", "generate_and_execute",
        } for st in plan.subtasks):
            return {"runnable": False}
        project_path = plan.execution_target.path if plan.execution_target else None
        if isinstance(project_path, str) and project_path.strip():
            try:
                plan.execution_target.validate()
                root = Path(plan.execution_target.root)
                project_dir = plan.execution_target.directory
                if root not in project_dir.parents:
                    return {}
                manifest = json.loads(
                    plan.execution_target.file(".project.json").read_text(encoding="utf-8"))
                entry_point = manifest.get("entry_point")
                if entry_point:
                    plan.execution_target.file(entry_point)
                    return {
                        "project_name": project_dir.name,
                        "project_path": project_dir.relative_to(root).as_posix(),
                        "entry_point": entry_point,
                        "runnable": bool(manifest.get("run")),
                    }
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        return {}

    async def _handle_cancel_request(self, message: BusMessage) -> None:
        """Handle task cancellation requests."""
        task_id = message.payload.get("task_id")
        cancel_mode = message.payload.get("mode", "soft")
        session_id = message.payload.get("session_id")
        
        if task_id:
            plan = self.task_plans.get(task_id)
            if session_id and plan and (plan.original_task.payload or {}).get('session_id') != session_id:
                return
            await self._cancel_task(task_id, cancel_mode)
        else:
            # Cancel all active tasks
            for plan_id in list(self.task_plans.keys()):
                plan = self.task_plans[plan_id]
                if session_id and (plan.original_task.payload or {}).get('session_id') != session_id:
                    continue
                if plan.status not in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    await self._cancel_task(plan_id, cancel_mode)
    
    async def _cancel_task(self, task_id: str, mode: str) -> None:
        """Cancel a specific task and all its subtasks."""
        plan = self.task_plans.get(task_id)
        if not plan or plan.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return
        
        plan.status = TaskStatus.CANCELLED
        if plan.transaction:
            from ..project_transaction import ProjectTransaction
            try:
                ProjectTransaction(plan.transaction).fence()
            except (OSError, ValueError) as exc:
                plan.rollback = {'state': 'recovery_required', 'error': str(exc), 'journal': plan.transaction}
        
        # Cancel active subtasks (keys are dispatch message IDs)
        for dispatch_id in list(self.active_subtasks.keys()):
            if self.active_subtasks.get(dispatch_id) == task_id:
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
                        payload={"task_id": dispatch_id, "mode": mode}
                    )
                    await self.bus.send(cancel_msg)
                    brain = subtask.assigned_brain
                    self.brain_load[brain] = max(0, self.brain_load.get(brain, 0) - 1)
                self.active_subtasks.pop(dispatch_id, None)
        if plan.transaction:
            try:
                # Workers/process groups have stopped; only now restore the build.
                plan.rollback = ProjectTransaction(plan.transaction).finish(commit=False)
            except (OSError, ValueError) as exc:
                plan.rollback = {'state': 'recovery_required', 'error': str(exc), 'journal': plan.transaction}
        for subtask in plan.subtasks:
            if subtask.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                subtask.status = TaskStatus.CANCELLED
        plan.awaiting_approval = False
        
        await self.bus.broadcast_event(
            source=self.name,
            event_type="task.cancelled",
            payload={
                "task_id": task_id,
                "mode": mode,
                "session_id": (plan.original_task.payload or {}).get("session_id"),
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
        """Forward brain events and track brain liveness.
        
        Note: Re-broadcasting disabled to prevent loops.
        But we track alive/stopped brains for pool resilience.
        """
        event_type = message.payload.get("event_type") or ""
        # Also check the BusMessage metadata for event type
        if not event_type and hasattr(message, 'type') and message.type == MessageType.EVENT:
            event_type = message.payload.get("event_type", "")
        
        # Track brain liveness from events
        brain_name = message.source
        if brain_name and brain_name != self.name:
            event_name = (message.payload or {}).get("event", "")
            if event_name == "brain.stopped":
                self._alive_brains.discard(brain_name)
            else:
                self._alive_brains.add(brain_name)
    
    def register_brain(self, brain_name: str, capabilities: Dict[str, Any] = None) -> None:
        """Register a brain with this orchestrator."""
        self.registered_brains[brain_name] = capabilities or {}
        self.brain_load[brain_name] = 0
        self._alive_brains.add(brain_name)
    
    def unregister_brain(self, brain_name: str) -> None:
        """Unregister a brain from this orchestrator."""
        self.registered_brains.pop(brain_name, None)
        self.brain_load.pop(brain_name, None)
        self._alive_brains.discard(brain_name)
    
    def register_brain_pool(self, logical_name: str, worker_names: List[str]) -> None:
        """Register a pool of workers under a logical brain name.
        
        When the LLM planner targets 'python_brain', the orchestrator resolves
        it to the least-loaded worker from the pool. This enables parallel
        execution of independent subtasks (e.g. writing 5 files at once).
        
        Args:
            logical_name: The name the planner uses (e.g. "python_brain")
            worker_names: List of actual worker names (e.g. ["python_brain_0", ...])
        """
        self.brain_pools[logical_name] = list(worker_names)
        # Assume all registered pool workers are alive until proven otherwise
        for w in worker_names:
            self._alive_brains.add(w)
        print(f"[ORCH] Brain pool '{logical_name}' → {worker_names}")
    
    def _resolve_brain_target(self, logical_name: str) -> str:
        """Resolve a logical brain name to the least-loaded worker from its pool.
        
        If the name isn't in a pool, returns it unchanged.
        Prefers alive workers. If all workers are dead, falls back to least-loaded.
        """
        if logical_name not in self.brain_pools:
            return logical_name
        
        workers = self.brain_pools[logical_name]
        if not workers:
            return logical_name
        
        # Filter to alive workers if we have liveness info
        alive_workers = [w for w in workers if w in self._alive_brains]
        candidates = alive_workers if alive_workers else workers
        
        # Pick the worker with the lowest load
        best = candidates[0]
        best_load = self.brain_load.get(best, 0)
        for w in candidates[1:]:
            load = self.brain_load.get(w, 0)
            if load < best_load:
                best = w
                best_load = load
        
        return best
    
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
    
    async def _auto_checkpoint_before_execution(self, plan: TaskPlan) -> None:
        """
        Auto-checkpoint project directory before executing subtasks.
        
        Creates a snapshot for file-based projects so we can recover from errors
        or compare changes after task completion.
        """
        # Only checkpoint for projects that will write files
        has_file_tasks = any(
            subtask.payload.get("type") in (
                "write_project_file", "assemble_and_run",
                "write_web_file", "assemble_and_preview",
            )
            for subtask in plan.subtasks
        )
        
        if not has_file_tasks:
            return  # Skip checkpoint for code-only tasks
        
        if plan.execution_target is None:
            return
        project_dir = plan.execution_target.directory
        project_name = project_dir.name
        
        if not project_dir.exists():
            return  # Project directory doesn't exist yet
        
        try:
            checkpoint_id = self.checkpoint_manager.snapshot(project_dir)
            
            # Store checkpoint info on the plan for later reference
            if not hasattr(plan, 'metadata'):
                plan.metadata = {}
            plan.metadata['pre_execution_checkpoint'] = checkpoint_id
            
            await self.bus.broadcast_event(
                source=self.name,
                event_type="checkpoint.created",
                payload={
                    "task_id": plan.id,
                    "checkpoint_id": checkpoint_id,
                    "project_name": project_name,
                    "type": "pre_execution"
                },
                workspace=self.workspace,
                priority=Priority.LOW
            )
            
            logger.info("Created pre-execution checkpoint %s for project %s", 
                       checkpoint_id[:8], project_name)
            
        except Exception as e:
            # Don't fail task execution if checkpointing fails
            logger.warning("Failed to create pre-execution checkpoint for %s: %s", 
                          project_name, e)
            
            await self.bus.broadcast_event(
                source=self.name,
                event_type="checkpoint.failed",
                payload={
                    "task_id": plan.id,
                    "project_name": project_name,
                    "error": str(e),
                    "type": "pre_execution"
                },
                workspace=self.workspace,
                priority=Priority.LOW
            )
    
    def _analyze_execution_mode(self, subtasks: List[SubTask], user_request: str) -> str:
        """
        Analyze task complexity and choose execution mode.

        - A plan WITH dependency structure is a DAG by construction
          (projects: file writes then assembly) -> "dag": independent
          subtasks dispatch to the worker pool IN PARALLEL, dependent
          ones wait. Size alone must not serialize a project.
        - A flat list of small independent tasks stays "todo"
          (sequential — order matters to the user, overhead is lower).
        - >2 independent AND >4 total -> "dag" (genuine parallel win).

        Args:
            subtasks: List of planned subtasks
            user_request: Original user request for context

        Returns:
            "todo" or "dag" execution mode
        """
        if not subtasks:
            return "todo"

        total_tasks = len(subtasks)

        # Count independent tasks (no dependencies)
        independent_count = sum(1 for st in subtasks if not st.dependencies)

        # A subtask with dependencies means the plan is a real DAG.
        has_dependencies = any(st.dependencies for st in subtasks)

        # Apply decision rules
        if has_dependencies or (independent_count > 2 and total_tasks > 4):
            mode = "dag"
            reason = (f"{independent_count} independent, {total_tasks} total, "
                      f"has_dependencies={has_dependencies}")
        else:
            mode = "todo"
            reason = f"{independent_count} independent tasks, {total_tasks} total (flat small list)"
        logger.info("Execution mode: %s (%s)", mode, reason)
        
        # Emit planning event with mode selection (best-effort)
        try:
            asyncio.get_running_loop().create_task(self.bus.broadcast_event(
                source=self.name,
                event_type="planning.mode_selected",
                payload={
                    "mode": mode,
                    "reasoning": reason,
                    "independent_tasks": independent_count,
                    "total_tasks": total_tasks,
                    "request_summary": user_request[:100] if user_request else ""
                },
                workspace=self.workspace,
                priority=Priority.LOW
            ))
        except RuntimeError:
            pass  # No event loop — testing or non-async context
        
        return mode

    
    def inject_user_message(self, plan_id: str, message: str) -> bool:
        """
        Inject a user message into an active task plan.
        
        The message will be included in the payload of the next dispatched subtask
        as _user_interjection, allowing the brain to see and respond to user input
        mid-execution.
        
        Args:
            plan_id: ID of the task plan to inject message into
            message: User message to inject
            
        Returns:
            True if message was injected, False if plan not found or not active
        """
        plan = self.task_plans.get(plan_id)
        if not plan or plan.status != TaskStatus.RUNNING:
            return False
        
        # Store the message on the plan
        if not hasattr(plan, "user_interjections"):
            plan.user_interjections = []
        
        plan.user_interjections.append({
            "message": message,
            "timestamp": time.time(),
            "injected_at": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        
        logger.info("Injected user message into plan %s: %s", plan_id[:8], message[:100])
        
        # Broadcast event (best-effort)
        try:
            asyncio.get_running_loop().create_task(self.bus.broadcast_event(
                source=self.name,
                event_type="task.user_interjection",
                payload={
                    "task_id": plan_id,
                    "message": message,
                    "timestamp": time.time()
                },
                workspace=self.workspace,
                priority=Priority.NORMAL
            ))
        except RuntimeError:
            pass  # No event loop — testing or non-async context
        
        return True

    
    def _check_context_limits(self, plan: TaskPlan) -> None:
        """
        Check if context window is approaching limits and trigger compaction.
        
        This is a lightweight implementation that tracks message history length
        and compacts when approaching 92% of estimated context window.
        """
        # Simple estimation: count total characters in subtask payloads and results
        total_chars = 0
        
        for subtask in plan.subtasks:
            # Count payload size
            if subtask.payload:
                total_chars += len(str(subtask.payload))
            # Count result size
            if subtask.result:
                total_chars += len(str(subtask.result))
        
        # Rough context limit estimation (assuming ~4 chars per token, 100k token limit)
        CONTEXT_LIMIT = 400000  # chars
        COMPACTION_THRESHOLD = int(CONTEXT_LIMIT * 0.92)  # 92%
        
        if total_chars > COMPACTION_THRESHOLD:
            logger.info("Context approaching limit (%d chars > %d), triggering compaction", 
                       total_chars, COMPACTION_THRESHOLD)
            self._compact_plan_context(plan)
    
    def _compact_plan_context(self, plan: TaskPlan) -> None:
        """
        Compact plan context by summarizing completed subtask results.
        
        Replaces verbose results with concise summaries to free up context space.
        """
        compacted_count = 0
        
        for subtask in plan.subtasks:
            if (subtask.status == TaskStatus.COMPLETE and 
                subtask.result and 
                not (isinstance(subtask.result, dict) and subtask.result.get("_compacted", False))):
                
                # Extract key information for summary
                result = result_data(subtask.result)
                # Source results are dependency artifacts, not conversational
                # prose. Compaction must never replace them with summaries.
                if isinstance(result, dict) and result.get('file_content') is not None:
                    continue
                if isinstance(result, dict):
                    from ..bus.delivery import archive_delivery
                    try:
                        delivery = archive_delivery(result, task_id=plan.id,
                            subtask_id=subtask.id,
                            session_id=plan.original_task.payload.get('session_id'))
                    except (OSError, ValueError, TypeError) as exc:
                        logger.warning('Compaction retained the worker result because archival failed: %s', exc)
                        continue
                    summary = {
                        "success": result.get("success", False),
                        "status": "completed",
                        "type": subtask.payload.get("type", "unknown"),
                        "delivery": delivery,
                    }
                    
                    # Preserve key outputs but truncate verbose content
                    if "file_path" in result:
                        summary["file_path"] = result["file_path"]
                    if "stdout" in result:
                        summary["stdout"] = result["stdout"][:100] + "..." if len(result.get("stdout", "")) > 100 else result.get("stdout", "")
                    if "lines" in result:
                        summary["lines"] = result["lines"]
                    
                    # Mark as compacted and replace
                    summary["_compacted"] = True
                    subtask.result = summary
                    compacted_count += 1
        
        if compacted_count > 0:
            logger.info("Compacted %d subtask results for plan %s", 
                       compacted_count, plan.id[:8])

    
    async def _extract_learnings(self, plan: TaskPlan) -> None:
        """
        Extract learnings from completed task plan.
        
        Analyzes failed and successful subtasks to extract patterns and insights
        for future task planning improvements.
        """
        if not plan.subtasks:
            return
        
        learnings = []
        
        # Analyze failed subtasks for common error patterns
        failed_subtasks = [st for st in plan.subtasks if st.status == TaskStatus.FAILED]
        for subtask in failed_subtasks:
            if subtask.error:
                error_type = self._classify_error_type(subtask.error)
                learning = {
                    "type": "failure_pattern",
                    "pattern": error_type,
                    "context": subtask.description[:100],
                    "error": subtask.error[:200],
                    "timestamp": time.time()
                }
                learnings.append(learning)
        
        # Analyze successful patterns
        successful_subtasks = [st for st in plan.subtasks if st.status == TaskStatus.COMPLETE]
        if len(successful_subtasks) > 0:
            # Extract successful strategies
            task_types = {}
            for subtask in successful_subtasks:
                task_type = subtask.payload.get("type", "unknown")
                if task_type not in task_types:
                    task_types[task_type] = 0
                task_types[task_type] += 1
            
            # Record successful task type patterns
            for task_type, count in task_types.items():
                if count > 1:  # Multiple successes indicate a good pattern
                    learning = {
                        "type": "success_pattern",
                        "pattern": f"{task_type}_works_well",
                        "context": f"Successfully completed {count} {task_type} tasks",
                        "timestamp": time.time()
                    }
                    learnings.append(learning)
        
        # Save learnings if any were extracted
        if learnings:
            await self._save_learnings(learnings)
    
    def _classify_error_type(self, error: str) -> str:
        """Classify error into common patterns."""
        error_lower = error.lower()
        
        if "syntax" in error_lower or "syntaxerror" in error_lower:
            return "syntax_error"
        elif "import" in error_lower or "modulenotfounderror" in error_lower:
            return "import_error" 
        elif "permission" in error_lower or "access" in error_lower:
            return "permission_error"
        elif "timeout" in error_lower or "timed out" in error_lower:
            return "timeout_error"
        elif "file not found" in error_lower or "no such file" in error_lower:
            return "file_not_found"
        else:
            return "other_error"
    
    async def _save_learnings(self, learnings: List[Dict[str, Any]]) -> None:
        """Save learnings to persistent storage."""
        try:
            import json
            
            # Create memory directory structure
            from ..memory.paths import legacy_storage_dir
            memory_dir = legacy_storage_dir('long_term')
            memory_dir.mkdir(parents=True, exist_ok=True)
            
            learnings_file = memory_dir / "learnings.json"
            
            # Load existing learnings
            existing_learnings = []
            if learnings_file.exists():
                with open(learnings_file, "r", encoding="utf-8") as f:
                    existing_learnings = json.load(f)
            
            # Add new learnings
            existing_learnings.extend(learnings)
            
            # Keep only the most recent 50 learnings (FIFO)
            MAX_LEARNINGS = 50
            if len(existing_learnings) > MAX_LEARNINGS:
                # Sort by timestamp and keep the newest ones
                existing_learnings.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
                existing_learnings = existing_learnings[:MAX_LEARNINGS]
            
            # Save back to file
            with open(learnings_file, "w", encoding="utf-8") as f:
                json.dump(existing_learnings, f, indent=2)
            
            logger.info("Saved %d learnings to %s", len(learnings), learnings_file)
            
        except Exception as e:
            logger.warning("Failed to save learnings: %s", e)
    
    def load_learnings(self) -> List[Dict[str, Any]]:
        """Load learnings for brain startup."""
        try:
            import json
            
            from ..memory.paths import legacy_storage_dir
            learnings_file = legacy_storage_dir('long_term') / 'learnings.json'
            if learnings_file.exists():
                with open(learnings_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            return []
            
        except Exception as e:
            logger.warning("Failed to load learnings: %s", e)
            return []
