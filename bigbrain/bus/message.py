"""BusMessage - Core message structure for BigBrain communication."""

import time
import uuid
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """Types of messages that can be sent on the bus."""
    TASK = "task"           # Task request from orchestrator to brain
    RESULT = "result"       # Task completion response
    EVENT = "event"         # General event notification  
    QUERY = "query"         # Information request
    PROGRESS = "progress"   # Progress update during task execution
    CANCEL = "cancel"       # Task cancellation request
    STATE = "state"         # Real-time state streaming


class Priority(int, Enum):
    """Message priority levels for focus filtering."""
    CRITICAL = 3    # P0 - Security, system failure, data loss - always interrupts
    HIGH = 2        # P1 - Task failed, human input needed, urgent deadline
    NORMAL = 1      # P2 - Task complete, significant progress, build passed
    LOW = 0         # P3 - Minor progress, heartbeats, routine updates


class BusMessage(BaseModel):
    """
    Core message structure for BigBrain's CAN bus-style communication.
    
    Every communication between components flows through BusMessages on the MessageBus.
    This decouples components and enables features like logging, filtering, and replay.
    
    The message structure supports both request/response patterns (via reply_to) and
    event streaming (via state/progress types).
    """
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    """Unique message identifier - auto-generated UUID"""
    
    type: MessageType = Field(description="Message type determining handling behavior")
    """What kind of message this is - determines how recipients process it"""
    
    source: str = Field(description="Component that sent this message")
    """Identifies the sender - e.g. 'front_brain', 'orchestrator_webdev', 'python_brain'"""
    
    target: str = Field(description="Recipient component or '*' for broadcast")
    """Who should receive this - specific component name or '*' for all subscribers"""
    
    workspace: Optional[str] = Field(default=None, description="Workspace context")
    """Which workspace this message relates to - enables workspace-scoped filtering"""
    
    project: Optional[str] = Field(default=None, description="Project context")
    """Project identifier for memory scoping and context tracking"""
    
    payload: Dict[str, Any] = Field(default_factory=dict)
    """Message-specific data - structure depends on message type"""
    
    timestamp: float = Field(default_factory=time.time)
    """When the message was created - Unix timestamp for ordering"""
    
    reply_to: Optional[str] = Field(default=None)
    """Links response to original request - enables request/response tracking"""
    
    priority: Priority = Field(default=Priority.NORMAL)
    """Priority level for focus filtering and interrupt management"""

    def is_broadcast(self) -> bool:
        """Check if this is a broadcast message."""
        return self.target == "*"
    
    def is_reply(self) -> bool:
        """Check if this is a reply to another message."""
        return self.reply_to is not None
    
    def create_reply(self, source: str, payload: Dict[str, Any], 
                    msg_type: MessageType = MessageType.RESULT) -> 'BusMessage':
        """Create a reply message to this message."""
        return BusMessage(
            type=msg_type,
            source=source,
            target=self.source,  # Reply goes back to original sender
            workspace=self.workspace,
            project=self.project,
            payload=payload,
            reply_to=self.id,
            priority=self.priority
        )

    def to_log_dict(self) -> Dict[str, Any]:
        """Convert to dictionary suitable for JSONL logging."""
        return {
            "id": self.id,
            "type": self.type if isinstance(self.type, str) else self.type.value,
            "source": self.source,
            "target": self.target,
            "workspace": self.workspace,
            "project": self.project,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "reply_to": self.reply_to,
            "priority": self.priority if isinstance(self.priority, int) else self.priority.value
        }

    class Config:
        """Pydantic configuration."""
        use_enum_values = True  # Store enums as their values