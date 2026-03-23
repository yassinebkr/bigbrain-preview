"""BusParticipant - Base class for anything that connects to the bus."""

from __future__ import annotations

from .bus import MessageBus
from .message import BusMessage


class BusParticipant:
    """Base class for anything that connects to the bus.
    
    Provides common subscribe/unsubscribe lifecycle so that BaseBrain
    and WorkspaceOrchestrator (and future components) don't duplicate
    bus-plumbing code.
    """

    def __init__(self, name: str, bus: MessageBus) -> None:
        self.name = name
        self.bus = bus
        self._running = False

    async def start(self) -> None:
        """Register with the bus and mark as running."""
        if self._running:
            return
        self._running = True
        self.bus.subscribe(self.name, self._on_message)

    async def stop(self) -> None:
        """Unregister from the bus and mark as stopped."""
        self._running = False
        self.bus.unsubscribe(self.name, self._on_message)

    async def _on_message(self, msg: BusMessage) -> None:
        """Override in subclasses to handle incoming messages."""
        pass
