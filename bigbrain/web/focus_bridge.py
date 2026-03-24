"""
Focus Bridge — Synchronizes FocusState between Front Brain and Morphable UI.

The Focus State is the shared boundary (architecture decision):
  - Front Brain reads/writes it (decides what to pay attention to)
  - Morphable UI reads/writes it (user clicks workspace tab → focus changes)
  - Both react to changes from the other

This bridge subscribes to bus events and keeps the FocusManager in sync
with UI-initiated changes, and broadcasts FocusManager changes to the UI.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..bus.bus import MessageBus
    from ..bus.message import BusMessage
    from ..front.focus_manager import FocusManager

logger = logging.getLogger(__name__)


class FocusBridge:
    """
    Bridges the FocusManager ↔ Morphable UI via the MessageBus.

    Listens for:
      - UI focus changes (workspace switch, mode toggle)
      - FocusManager state changes (from Front Brain decisions)

    Broadcasts:
      - Focus state updates to all bus subscribers
    """

    def __init__(
        self,
        bus: "MessageBus",
        focus_manager: "FocusManager",
    ):
        self.bus = bus
        self.focus_manager = focus_manager
        self._running = False
        self._last_broadcast: Dict[str, float] = {}
        self._min_broadcast_interval = 0.5  # seconds, anti-spam

    async def start(self) -> None:
        """Start listening for focus events."""
        if self._running:
            return

        self._running = True

        # Listen for UI-initiated focus changes
        self.bus.subscribe("front_brain", self._on_ui_focus_event)
        self.bus.subscribe("morphable_ui", self._on_ui_focus_event)

        # Set up periodic focus state broadcast (for late-joining clients)
        self._broadcast_task = asyncio.create_task(self._periodic_broadcast())

        logger.info("FocusBridge started")

    async def stop(self) -> None:
        """Stop the bridge."""
        self._running = False

        self.bus.unsubscribe("front_brain", self._on_ui_focus_event)
        self.bus.unsubscribe("morphable_ui", self._on_ui_focus_event)

        if hasattr(self, "_broadcast_task"):
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass

        logger.info("FocusBridge stopped")

    async def broadcast_focus_state(self) -> None:
        """Broadcast the current focus state to all bus subscribers."""
        now = time.time()
        last = self._last_broadcast.get("focus", 0)
        if now - last < self._min_broadcast_interval:
            return

        self._last_broadcast["focus"] = now

        from ..bus.message import BusMessage, MessageType, Priority

        state = self.focus_manager.get_focus_status()

        message = BusMessage(
            type=MessageType.STATE,
            source="focus_bridge",
            target="*",
            payload={
                "event": "focus.state",
                **state,
            },
            priority=Priority.NORMAL,
        )
        await self.bus.send(message)

    # ================================================================
    # EVENT HANDLERS
    # ================================================================

    async def _on_ui_focus_event(self, message: "BusMessage") -> None:
        """Handle focus-related events from the UI or Front Brain."""
        event = message.payload.get("event", "")

        if event == "focus.workspace_changed":
            workspace = message.payload.get("workspace")
            if workspace and message.source == "morphable_ui":
                # UI initiated workspace switch → update FocusManager
                from ..front.focus_manager import FocusState

                self.focus_manager.set_workspace_focus(
                    workspace, FocusState.ACTIVE, "ui"
                )
                # Broadcast the change so Front Brain knows
                await self.broadcast_focus_state()

        elif event == "focus.mode_changed":
            mode_str = message.payload.get("mode")
            if mode_str and message.source == "morphable_ui":
                from ..front.focus_manager import FocusMode

                mode_map = {
                    "deep_focus": FocusMode.DEEP_FOCUS,
                    "normal": FocusMode.NORMAL,
                    "overview": FocusMode.OVERVIEW,
                }
                mode = mode_map.get(mode_str)
                if mode:
                    self.focus_manager.set_focus_mode(mode, "ui")
                    await self.broadcast_focus_state()

    async def _periodic_broadcast(self) -> None:
        """Periodically broadcast focus state for late-joining clients."""
        while self._running:
            await asyncio.sleep(10)  # Every 10 seconds
            if self._running:
                try:
                    await self.broadcast_focus_state()
                except Exception as e:
                    logger.debug("Focus broadcast error: %s", e)
