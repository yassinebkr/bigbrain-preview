"""BigBrain - A Multi-Brain AI Agent System

A modular, async AI agent system with 3-layer architecture:
- Front Brain: User-facing intelligence with focus management
- Orchestrator: Task decomposition and routing
- Sub-brains: Specialized execution workers

Built for educational purposes and as a reference implementation.
"""

__version__ = "0.2.0"
__author__ = "BigBrain Team"

from .bus.message import BusMessage, MessageType, Priority
from .bus.bus import MessageBus

__all__ = ["BusMessage", "MessageType", "Priority", "MessageBus"]