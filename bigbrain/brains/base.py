"""BaseBrain - Abstract base class for BigBrain execution workers."""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..bus.bus import MessageBus
from ..bus.message import BusMessage, MessageType, Priority
from ..bus.participant import BusParticipant


class BaseBrain(BusParticipant, ABC):
    """
    Abstract base class for BigBrain execution workers.
    
    Inherits bus subscribe/unsubscribe plumbing from BusParticipant
    and adds brain-specific lifecycle, task handling, and event broadcasting.
    
    Brain Lifecycle:
    1. Initialize with bus connection and brain name
    2. Start - registers with bus and begins message processing
    3. Handle messages - implement handle_task for brain-specific logic
    4. Stop - cleanup and unregister from bus
    
    Message Flow:
    - Receives TASK messages via handle_message
    - Processes via handle_task (implemented by subclass)
    - Sends RESULT messages back via send_result
    - Publishes STATE/PROGRESS events via send_event
    """
    
    def __init__(self, name: str, bus: MessageBus, workspace: str = None):
        """
        Initialize brain with bus connection.
        
        Args:
            name: Unique identifier for this brain instance
            bus: MessageBus instance for communication
            workspace: Optional workspace this brain belongs to
        """
        super().__init__(name, bus)
        self.workspace = workspace
        self._current_task: Optional[BusMessage] = None
        self._cancelled = False
        self._background_task: Optional[asyncio.Task] = None
        
        # Bind message handler to this instance
        self._message_handler = self._handle_message_wrapper
    
    async def start(self) -> None:
        """
        Start the brain and register with the message bus.
        
        After starting, the brain will receive task messages and
        begin processing them asynchronously.
        """
        if self._running:
            raise RuntimeError(f"Brain {self.name} is already running")
        
        self._running = True
        self._cancelled = False
        
        # Subscribe to messages targeted at this brain (via BusParticipant plumbing)
        self.bus.subscribe(self.name, self._message_handler)
        
        # Announce brain availability
        await self.send_event("brain.started", {
            "brain": self.name,
            "workspace": self.workspace
        }, priority=Priority.LOW)
    
    async def stop(self) -> None:
        """
        Stop the brain and cleanup resources.
        
        Unregisters from the bus and performs any brain-specific cleanup.
        """
        if not self._running:
            return
        
        self._running = False
        
        # Cancel current task gracefully
        if self._current_task:
            await self._cancel_current_task()
        
        # Cancel background task if running
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
            try:
                await self._background_task
            except (asyncio.CancelledError, Exception):
                pass
            self._background_task = None
        
        # Unregister from bus
        self.bus.unsubscribe(self.name, self._message_handler)
        
        # Announce brain shutdown
        await self.send_event("brain.stopped", {
            "brain": self.name,
            "workspace": self.workspace
        }, priority=Priority.LOW)
        
        # Subclass cleanup
        await self.cleanup()
    
    async def _handle_message_wrapper(self, message: BusMessage) -> None:
        """
        Internal message handler that wraps subclass logic.
        
        Handles common message types and delegates task processing
        to the subclass handle_task method.
        """
        # Skip our own messages to prevent broadcast loops
        if message.source == self.name:
            return
        
        try:
            if message.type == MessageType.TASK:
                await self._handle_task_message(message)
            elif message.type == MessageType.CANCEL:
                await self._handle_cancel_message(message)
            else:
                # Let subclass handle other message types
                await self.handle_message(message)
        
        except Exception as e:
            # Send error result back to the caller.
            # NOTE: _current_task may already be None (cleared by _handle_task_message's
            # finally block). For TASK messages, use the message itself as fallback.
            error_reply_to = None
            error_target = None
            
            if self._current_task:
                error_reply_to = self._current_task.id
                error_target = self._current_task.source
                self._current_task = None
            elif message.type == MessageType.TASK:
                # _handle_task_message's finally already cleared _current_task,
                # but we still need to send the error result back.
                error_reply_to = message.id
                error_target = message.source
            
            if error_reply_to:
                await self.bus.send_result(
                    source=self.name,
                    result_data={
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    reply_to=error_reply_to,
                    workspace=self.workspace,
                    target=error_target,
                )
            
            # Also broadcast the error event
            await self.send_event("brain.error", {
                "brain": self.name,
                "error": str(e),
                "message_id": message.id
            }, priority=Priority.HIGH)
    
    async def _handle_task_message(self, message: BusMessage) -> None:
        """Handle incoming task messages.
        
        Spawns task execution as a background coroutine so bus.send()
        returns immediately, enabling parallel dispatch to multiple brains.
        """
        if self._current_task:
            # Brain is busy - reject with busy status.
            # Use bus.send_result with EXPLICIT target (message.source) to avoid
            # the log-search fallback in send_result(), which raises ValueError
            # when the message isn't found — killing the busy rejection silently.
            await self.bus.send_result(
                source=self.name,
                result_data={
                    "success": False,
                    "error": "Brain is busy with another task",
                    "busy": True
                },
                reply_to=message.id,
                workspace=self.workspace,
                target=message.source,
            )
            return
        
        self._current_task = message
        self._cancelled = False
        
        # Spawn task execution in background so bus.send() returns immediately.
        # This is critical for parallel dispatch — without it, the orchestrator's
        # dispatch loop blocks on each task completion.
        self._background_task = asyncio.create_task(
            self._execute_task_background(message),
            name=f"{self.name}:task:{message.id[:8]}"
        )
    
    async def _execute_task_background(self, message: BusMessage) -> None:
        """Execute a task in the background after bus handler returns."""
        try:
            # Announce task start
            await self.send_event("brain.started", {
                "brain": self.name,
                "task_id": message.id,
                "task_type": message.payload.get("type", "unknown")
            })
            
            # Delegate to subclass
            result = await self.handle_task(message)
            
            if not self._cancelled:
                # Send successful result
                await self.send_result({
                    "success": True,
                    "data": result
                }, message.id)
                
                await self.send_event("brain.complete", {
                    "brain": self.name,
                    "task_id": message.id
                })
        
        except Exception as e:
            # Error during background execution — send error result
            await self.send_result({
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }, message.id)
            
            await self.send_event("brain.error", {
                "brain": self.name,
                "error": str(e),
                "message_id": message.id
            }, priority=Priority.HIGH)
        
        finally:
            self._current_task = None
            self._background_task = None
    
    async def _handle_cancel_message(self, message: BusMessage) -> None:
        """Handle task cancellation requests."""
        cancel_mode = message.payload.get("mode", "soft")
        task_id = message.payload.get("task_id")
        
        # Check if we have a matching task to cancel
        if not self._current_task or (task_id and self._current_task.id != task_id):
            return  # Not our task to cancel
        
        if cancel_mode == "hard":
            # Hard cancel - immediate stop
            self._cancelled = True
            await self.send_result({
                "success": False,
                "cancelled": True,
                "mode": "hard"
            }, self._current_task.id)
            self._current_task = None
            
            await self.send_event("brain.cancelled", {
                "brain": self.name,
                "mode": "hard"
            })
        
        else:
            # Soft cancel - set flag for graceful exit
            self._cancelled = True
            await self.send_event("brain.cancelling", {
                "brain": self.name,
                "mode": "soft"
            })
    
    async def _cancel_current_task(self) -> None:
        """Cancel the currently running task gracefully."""
        if self._current_task:
            self._cancelled = True
            await self.send_result({
                "success": False,
                "cancelled": True,
                "mode": "shutdown"
            }, self._current_task.id)
            self._current_task = None
    
    async def send_result(self, result_data: Dict[str, Any], reply_to: str) -> None:
        """
        Send a task result back to the requester.
        
        Passes the target explicitly (from _current_task.source) to avoid
        fragile log-file lookups that fail on busy buses.
        
        Args:
            result_data: Result payload - should include 'success' boolean
            reply_to: Message ID this is a response to
        """
        # Determine target from stored task reference (avoids log search)
        target = None
        if self._current_task and self._current_task.id == reply_to:
            target = self._current_task.source
        
        await self.bus.send_result(
            source=self.name,
            result_data=result_data,
            reply_to=reply_to,
            workspace=self.workspace,
            target=target,
        )
    
    async def send_event(self, event_type: str, payload: Dict[str, Any] = None,
                        priority: Priority = Priority.NORMAL) -> None:
        """
        Send an event broadcast to inform other components of state changes.
        
        Args:
            event_type: Type of event (e.g. 'brain.progress', 'brain.error')
            payload: Event-specific data
            priority: Event priority for focus filtering
        """
        await self.bus.broadcast_event(
            source=self.name,
            event_type=event_type,
            payload=payload or {},
            workspace=self.workspace,
            priority=priority
        )
    
    async def send_progress(self, progress_data: Dict[str, Any]) -> None:
        """
        Send progress update for long-running tasks.
        
        Args:
            progress_data: Progress information (e.g. percentage, current step)
        """
        # Include subtask_id from task payload so UI can correlate
        if self._current_task and self._current_task.payload:
            subtask_id = self._current_task.payload.get("_subtask_id")
            if subtask_id and "subtask_id" not in progress_data:
                progress_data = {**progress_data, "subtask_id": subtask_id}
        
        message = BusMessage(
            type=MessageType.PROGRESS,
            source=self.name,
            target="*",  # Broadcast progress
            workspace=self.workspace,
            payload=progress_data,
            reply_to=self._current_task.id if self._current_task else None,
            priority=Priority.LOW
        )
        await self.bus.send(message)
    
    @abstractmethod
    async def handle_task(self, message: BusMessage) -> Any:
        """
        Process a task message and return the result.
        
        This is the main brain logic that subclasses must implement.
        Should check self._cancelled periodically for graceful cancellation.
        
        Args:
            message: Task message containing work to do
            
        Returns:
            Task result data that will be sent back to requester
        """
        pass
    
    async def handle_message(self, message: BusMessage) -> None:
        """
        Handle non-task messages.
        
        Override in subclasses to handle brain-specific message types.
        Base implementation does nothing.
        """
        pass
    
    async def cleanup(self) -> None:
        """
        Perform brain-specific cleanup when stopping.
        
        Override in subclasses to cleanup resources like temp files,
        subprocess connections, etc.
        """
        pass
    
    def is_running(self) -> bool:
        """Check if the brain is currently running."""
        return self._running
    
    def is_busy(self) -> bool:
        """Check if the brain is currently processing a task."""
        return self._current_task is not None
    
    def get_status(self) -> Dict[str, Any]:
        """Get current brain status for monitoring."""
        return {
            "name": self.name,
            "workspace": self.workspace,
            "running": self._running,
            "busy": self.is_busy(),
            "current_task": self._current_task.id if self._current_task else None,
            "cancelled": self._cancelled
        }