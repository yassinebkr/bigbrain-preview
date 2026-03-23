"""MessageBus - Async pub/sub message bus for BigBrain components."""

import asyncio
import logging
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, TYPE_CHECKING

from .logger import BusLogger
from .message import BusMessage, MessageType, Priority

if TYPE_CHECKING:
    from .auth import BusAuth

logger = logging.getLogger(__name__)


class MessageBus:
    """
    Async publish/subscribe message bus for BigBrain.
    
    Implements CAN bus-style decoupled communication between components.
    All inter-component messages flow through this bus, enabling:
    - Full message logging and replay for debugging
    - Focus-based filtering for attention management
    - Wildcard routing for broadcast messages
    - Priority-based message handling
    
    Components register as subscribers with message handlers.
    The bus routes messages based on target field and calls handlers asynchronously.
    """
    
    def __init__(self, log_dir: Path = Path("logs"), auth: "Optional[BusAuth]" = None):
        """Initialize message bus with logging and optional HMAC auth."""
        self.logger = BusLogger(log_dir)
        self.auth = auth
        
        # Subscriber registry: target_name -> set of handler functions
        self._subscribers: Dict[str, Set[Callable[[BusMessage], None]]] = defaultdict(set)
        
        # Wildcard subscribers receive all messages
        self._wildcard_subscribers: Set[Callable[[BusMessage], None]] = set()
        
        # Track active components for debugging
        self._active_components: Set[str] = set()
        
        # Bus statistics
        self._stats = {
            "messages_sent": 0,
            "messages_delivered": 0,
            "delivery_errors": 0
        }
    
    async def send(self, message: BusMessage) -> None:
        """
        Send a message on the bus.
        
        The message will be logged and then delivered to all matching subscribers.
        Broadcast messages (target="*") are delivered to all subscribers.
        Specific targets are delivered only to subscribers registered for that target.
        """
        # Auto-sign if auth is configured and source has a token
        if self.auth is not None and message.signature is None:
            token = self.auth.get_token(message.source)
            if token is not None:
                message.signature = self.auth.sign_message(token, message)

        # Log the message first for full audit trail
        await self.logger.log_message(message)
        self._stats["messages_sent"] += 1
        
        # Track active components
        self._active_components.add(message.source)
        if message.target != "*":
            self._active_components.add(message.target)
        
        # Collect all handlers that should receive this message
        handlers = set()
        
        # Always include wildcard subscribers
        handlers.update(self._wildcard_subscribers)
        
        # Include specific target subscribers
        if message.is_broadcast():
            # Broadcast: send to all registered subscribers
            for target_handlers in self._subscribers.values():
                handlers.update(target_handlers)
        else:
            # Specific target: send only to that target's subscribers
            handlers.update(self._subscribers.get(message.target, set()))
        
        # Verify signature if auth is configured
        if self.auth is not None:
            if message.signature is None:
                logger.warning(
                    "MessageBus: Dropping unsigned message %s from %s (auth enabled)",
                    message.id, message.source,
                )
                return
            if not self.auth.verify_message(message.source, message, message.signature):
                logger.warning(
                    "MessageBus: Dropping message %s from %s — invalid signature",
                    message.id, message.source,
                )
                return

        # Deliver to all collected handlers concurrently
        if handlers:
            await asyncio.gather(
                *[self._deliver_to_handler(handler, message) for handler in handlers],
                return_exceptions=True
            )
    
    async def _deliver_to_handler(self, handler: Callable[[BusMessage], None], 
                                message: BusMessage) -> None:
        """
        Deliver message to a single handler with error handling.
        
        Handlers are called asynchronously. If a handler fails, the error
        is logged but doesn't affect delivery to other handlers.
        """
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(message)
            else:
                # Run sync handler in thread pool to avoid blocking
                await asyncio.get_event_loop().run_in_executor(None, handler, message)
            
            self._stats["messages_delivered"] += 1
            
        except Exception as e:
            self._stats["delivery_errors"] += 1
            # Log error but don't let one handler failure break others
            import sys
            print(f"MessageBus: Handler error for message {message.id}: {e}", file=sys.stderr)
    
    def subscribe(self, target: str, handler: Callable[[BusMessage], None]) -> None:
        """
        Subscribe to messages for a specific target.
        
        Args:
            target: Component name to subscribe to, or "*" for all messages
            handler: Async or sync function that accepts BusMessage
        """
        if target == "*":
            self._wildcard_subscribers.add(handler)
        else:
            self._subscribers[target].add(handler)
    
    def unsubscribe(self, target: str, handler: Callable[[BusMessage], None]) -> None:
        """
        Unsubscribe a handler from the specified target.
        
        Args:
            target: Component name to unsubscribe from
            handler: Handler function to remove
        """
        if target == "*":
            self._wildcard_subscribers.discard(handler)
        else:
            self._subscribers[target].discard(handler)
            # Clean up empty target entries
            if not self._subscribers[target]:
                del self._subscribers[target]
    
    def list_subscribers(self) -> Dict[str, int]:
        """Get current subscriber counts by target."""
        result = {}
        for target, handlers in self._subscribers.items():
            result[target] = len(handlers)
        if self._wildcard_subscribers:
            result["*"] = len(self._wildcard_subscribers)
        return result
    
    def get_stats(self) -> Dict[str, any]:
        """Get bus statistics for monitoring."""
        return {
            **self._stats,
            "active_components": list(self._active_components),
            "subscriber_counts": self.list_subscribers()
        }
    
    async def broadcast_event(self, source: str, event_type: str, 
                            payload: Dict = None, workspace: str = None,
                            priority: Priority = Priority.NORMAL) -> None:
        """
        Convenience method for broadcasting events.
        
        Used by components to publish state changes or notifications
        that any other component might be interested in.
        """
        message = BusMessage(
            type=MessageType.EVENT,
            source=source,
            target="*",
            workspace=workspace,
            payload={"event": event_type, **(payload or {})},
            priority=priority
        )
        await self.send(message)
    
    async def send_task(self, source: str, target: str, task_data: Dict,
                       workspace: str = None, project: str = None,
                       priority: Priority = Priority.NORMAL) -> BusMessage:
        """
        Convenience method for sending task messages.
        
        Returns the message object so caller can track replies via message.id.
        """
        message = BusMessage(
            type=MessageType.TASK,
            source=source,
            target=target,
            workspace=workspace,
            project=project,
            payload=task_data,
            priority=priority
        )
        await self.send(message)
        return message
    
    async def send_result(self, source: str, result_data: Dict, 
                         reply_to: str, workspace: str = None,
                         project: str = None, target: str = None) -> None:
        """
        Convenience method for sending task results.
        
        Delivers the result back to the original task sender.
        
        Args:
            source: Source component name
            result_data: Result payload
            reply_to: Original message ID this is a response to
            workspace: Workspace name
            project: Project name
            target: Explicit target. If None, searches the log for the
                    original message's source (fragile — prefer passing target).
        """
        if target is None:
            # Fallback: search log for original message's source
            async for msg in self.logger.read_messages(limit=1000):
                if msg.id == reply_to:
                    target = msg.source
                    break
            
            if target is None:
                raise ValueError(f"Cannot find original message {reply_to} to reply to")
        
        message = BusMessage(
            type=MessageType.RESULT,
            source=source,
            target=target,
            workspace=workspace,
            project=project,
            payload=result_data,
            reply_to=reply_to
        )
        await self.send(message)
    
    async def close(self) -> None:
        """Close the bus and cleanup resources."""
        await self.logger.close()
        self._subscribers.clear()
        self._wildcard_subscribers.clear()
        self._active_components.clear()