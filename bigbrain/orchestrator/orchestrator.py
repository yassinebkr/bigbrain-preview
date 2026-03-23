"""WorkspaceOrchestrator - Event-driven task management for BigBrain."""

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from ..bus.bus import MessageBus
from ..bus.message import BusMessage, MessageType, Priority
from ..bus.participant import BusParticipant
from .execution_modes import BrainExecutionConfig, ExecutionMode


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
    
    def __init__(self, workspace: str, bus: MessageBus):
        """
        Initialize workspace orchestrator.
        
        Args:
            workspace: Workspace name this orchestrator manages
            bus: MessageBus for communication
        """
        super().__init__(f"orchestrator_{workspace}", bus)
        self.workspace = workspace
        
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
        task_data = message.payload
        
        # Create task plan
        plan = await self._create_task_plan(message)
        self.task_plans[plan.id] = plan
        
        # Announce task received
        await self.bus.broadcast_event(
            source=self.name,
            event_type="task.received",
            payload={
                "task_id": plan.id,
                "workspace": self.workspace,
                "subtasks_count": len(plan.subtasks)
            },
            workspace=self.workspace,
            priority=Priority.NORMAL
        )
        
        # Start executing ready subtasks
        await self._execute_ready_subtasks(plan)
    
    async def _create_task_plan(self, message: BusMessage) -> TaskPlan:
        """
        Decompose a task into executable subtasks.
        
        For this preview implementation, we use simple task mapping.
        A production system would use LLM-based planning.
        """
        task_data = message.payload
        task_type = task_data.get("type", "unknown")
        
        plan_id = str(uuid.uuid4())
        plan = TaskPlan(id=plan_id, original_task=message)
        
        # Simple task decomposition based on type
        if task_type == "execute_code":
            # Single subtask - execute code
            subtask = SubTask(
                id=f"{plan_id}_code",
                description="Execute Python code",
                brain_target="python_brain",
                payload=task_data
            )
            plan.subtasks.append(subtask)
        
        elif task_type == "research":
            # Multi-step research task (ReWOO pattern)
            # Step 1: Plan research
            plan_subtask = SubTask(
                id=f"{plan_id}_plan",
                description="Plan research approach",
                brain_target="researcher",
                payload={
                    "type": "plan_research",
                    "query": task_data.get("query", ""),
                    "scope": task_data.get("scope", "general")
                }
            )
            
            # Step 2: Execute research (depends on plan)
            research_subtask = SubTask(
                id=f"{plan_id}_search",
                description="Execute research searches",
                brain_target="researcher", 
                payload={
                    "type": "execute_research",
                    "plan_ref": f"#{plan_subtask.id}"  # ReWOO-style reference
                },
                dependencies={plan_subtask.id}
            )
            
            # Step 3: Summarize results
            summary_subtask = SubTask(
                id=f"{plan_id}_summary",
                description="Summarize research findings",
                brain_target="researcher",
                payload={
                    "type": "summarize_research",
                    "results_ref": f"#{research_subtask.id}"
                },
                dependencies={research_subtask.id}
            )
            
            plan.subtasks.extend([plan_subtask, research_subtask, summary_subtask])
        
        else:
            # Default: single subtask to best available brain
            subtask = SubTask(
                id=f"{plan_id}_default",
                description=f"Execute {task_type} task",
                brain_target=self._choose_brain_for_task(task_type),
                payload=task_data
            )
            plan.subtasks.append(subtask)
        
        return plan
    
    def _choose_brain_for_task(self, task_type: str) -> str:
        """Choose the best brain for a task type based on load balancing."""
        # Map task types to brain types
        brain_preferences = {
            "execute_code": ["python_brain"],
            "research": ["researcher"],
            "web_search": ["researcher"],
            "default": ["python_brain"]  # Fallback
        }
        
        preferred_brains = brain_preferences.get(task_type, brain_preferences["default"])
        
        # Find least loaded available brain
        available_brains = [brain for brain in preferred_brains 
                           if brain in self.registered_brains]
        
        if not available_brains:
            # Return first preference as fallback
            return preferred_brains[0]
        
        # Return brain with lowest load
        return min(available_brains, key=lambda b: self.brain_load.get(b, 0))
    
    async def _execute_ready_subtasks(self, plan: TaskPlan) -> None:
        """Execute all subtasks that are ready (dependencies satisfied)."""
        ready_subtasks = plan.get_ready_subtasks()
        
        for subtask in ready_subtasks:
            await self._dispatch_subtask(plan, subtask)
    
    async def _dispatch_subtask(self, plan: TaskPlan, subtask: SubTask) -> None:
        """Dispatch a subtask to the appropriate brain."""
        import time
        
        # Update subtask status
        subtask.status = TaskStatus.RUNNING
        subtask.start_time = time.time()
        subtask.assigned_brain = subtask.brain_target
        
        # Track active subtask
        self.active_subtasks[subtask.id] = plan.id
        
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
            payload=resolved_payload,
            reply_to=subtask.id  # Use subtask ID for result tracking
        )
        
        await self.bus.send(task_message)
        
        # Announce subtask started
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
    
    async def _resolve_payload_references(self, payload: Dict[str, Any], 
                                        plan: TaskPlan) -> Dict[str, Any]:
        """
        Resolve ReWOO-style variable references in subtask payloads.
        
        Replaces references like "#E1" with actual results from completed subtasks.
        """
        resolved = {}
        results = plan.get_results()
        
        for key, value in payload.items():
            if isinstance(value, str) and value.startswith("#"):
                # Variable reference - look up result
                ref_id = value[1:]  # Remove # prefix
                if ref_id in results:
                    resolved[key] = results[ref_id]
                else:
                    # Reference not resolved yet - keep original
                    resolved[key] = value
            else:
                resolved[key] = value
        
        return resolved
    
    async def _handle_task_result(self, message: BusMessage) -> None:
        """Handle result from brain execution.
        
        Checks if the brain's execution mode requires V3/V5 verification
        before accepting the result.
        """
        import time
        
        subtask_id = message.reply_to
        if not subtask_id or subtask_id not in self.active_subtasks:
            return  # Not our subtask
        
        plan_id = self.active_subtasks[subtask_id]
        plan = self.task_plans.get(plan_id)
        if not plan:
            return  # Plan not found
        
        subtask = plan.get_subtask(subtask_id)
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
        
        # Update subtask with result
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
        del self.active_subtasks[subtask_id]
        
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
        
        # Check if we can start more subtasks
        if subtask.status == TaskStatus.COMPLETE:
            await self._execute_ready_subtasks(plan)
        
        # Check if entire plan is complete
        await self._check_plan_completion(plan)
    
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
            
            # Send final result back to original requester
            await self.bus.send_result(
                source=self.name,
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
        
        # Cancel active subtasks
        for subtask_id in list(self.active_subtasks.keys()):
            if self.active_subtasks[subtask_id] == task_id:
                subtask = plan.get_subtask(subtask_id)
                if subtask and subtask.assigned_brain:
                    # Send cancel to brain
                    cancel_msg = BusMessage(
                        type=MessageType.CANCEL,
                        source=self.name,
                        target=subtask.assigned_brain,
                        payload={"task_id": subtask_id, "mode": mode}
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