"""
WebAdapter — UIAdapter implementation for the Morphable Web UI.

Bridges the BigBrain core system to the web-based Morphable UI.
Sends UI updates as bus events that the WebSocket server forwards
to connected browsers.

This is Phase 3 of the UI architecture:
  Phase 1: RichAdapter (terminal)
  Phase 2: TextualAdapter (TUI)
  Phase 3: WebAdapter (browser, Morphable UI)
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..ui.ui_adapter import UIAdapter

if TYPE_CHECKING:
    from ..bus.bus import MessageBus
    from .server import WebServer

logger = logging.getLogger(__name__)


class WebAdapter(UIAdapter):
    """
    Web-based UIAdapter for BigBrain.

    Instead of rendering directly, this adapter sends structured events
    to the MessageBus. The WebSocket server picks them up and forwards
    them to the browser, where the Morphable UI renders them.

    This keeps the adapter thin — the browser does the rendering.
    """

    def __init__(
        self,
        bus: "MessageBus",
        web_server: "WebServer",
        workspace: str = "default",
    ):
        """
        Initialize WebAdapter.

        Args:
            bus: BigBrain MessageBus
            web_server: WebServer instance for connection tracking
            workspace: Current workspace name
        """
        self.bus = bus
        self.web_server = web_server
        self.workspace = workspace
        self._running = False

    async def start(self) -> None:
        """Start the web adapter."""
        self._running = True
        logger.info("WebAdapter started (workspace: %s)", self.workspace)

    async def stop(self) -> None:
        """Stop the web adapter."""
        self._running = False
        logger.info("WebAdapter stopped")

    def is_running(self) -> bool:
        """Check if the adapter is running."""
        return self._running

    # ================================================================
    # UIAdapter INTERFACE IMPLEMENTATION
    # ================================================================

    async def render_message(
        self,
        message: str,
        message_type: str = "info",
        metadata: Dict[str, Any] = None,
    ) -> None:
        """
        Send a message to the UI for display in the chat panel.

        Args:
            message: Message text
            message_type: Type (info, error, success, warning)
            metadata: Additional rendering metadata
        """
        await self._emit_event("chat.message", {
            "role": "system" if message_type != "info" else "assistant",
            "text": message,
            "type": message_type,
            **(metadata or {}),
        })

    async def render_progress(
        self,
        task_name: str,
        progress: float = None,
        status: str = None,
        details: Dict[str, Any] = None,
    ) -> None:
        """Send progress update to the UI."""
        await self._emit_event("task.progress", {
            "task": task_name,
            "progress": progress,
            "status": status,
            **(details or {}),
        })

    async def render_brain_status(
        self, brain_name: str, status: Dict[str, Any]
    ) -> None:
        """Send brain status update to the UI."""
        running = status.get("running", False)
        state = "idle" if running else "offline"
        if status.get("busy"):
            state = "busy"

        await self._emit_state("brain.status", {
            "brain": brain_name,
            "state": state,
            "running": running,
            **status,
        })

    async def render_workspace_overview(
        self, workspaces: Dict[str, Any]
    ) -> None:
        """Send workspace overview to the UI."""
        await self._emit_event("workspace.overview", {
            "workspaces": workspaces,
        })

    async def render_event_stream(
        self, events: List[Dict[str, Any]]
    ) -> None:
        """Send event stream to the UI (for bus monitor panel)."""
        for event in events:
            await self._emit_event("bus.event", event)

    async def get_user_input(self, prompt: str = None) -> str:
        """
        Get user input from the web UI.

        This is async — waits for a message from the WebSocket.
        In practice, the TUI/web handles input directly via the bus,
        so this method is rarely used in the web adapter.
        """
        # In web mode, input comes through the bus, not through this method
        logger.warning(
            "WebAdapter.get_user_input() called — web input comes via bus"
        )
        # Block indefinitely (input comes through bus events)
        await asyncio.Event().wait()
        return ""

    async def show_help(self) -> None:
        """Send help info to the UI."""
        await self.render_message(
            "**BigBrain Morphable UI**\n\n"
            "• Switch workspaces using the tabs above\n"
            "• Click panel title bars to collapse/expand\n"
            "• Type messages in the input box below\n"
            "• Press F1 to toggle focus mode\n"
            "• All panels update in real-time via the MessageBus",
            message_type="info",
        )

    async def show_error(
        self, error: str, details: str = None
    ) -> None:
        """Send error message to the UI."""
        text = f"❌ {error}"
        if details:
            text += f"\n\n{details}"
        await self.render_message(text, message_type="error")

    async def update_status_bar(
        self, status: Dict[str, Any]
    ) -> None:
        """Update the status strip with system info."""
        for key, value in status.items():
            await self._emit_event(f"status.{key}", {
                "data": value if isinstance(value, dict) else {"value": value},
            })

    # ================================================================
    # OPTIONAL METHODS
    # ================================================================

    async def render_code_output(
        self, code: str, output: Dict[str, Any]
    ) -> None:
        """Send code execution results to the UI."""
        await self._emit_event("chat.message", {
            "role": "assistant",
            "text": f"```python\n{code[:1200]}\n```",
            "type": "code",
        })

        if output.get("stdout"):
            await self._emit_event("chat.message", {
                "role": "system",
                "text": f"**Output:**\n```\n{output['stdout'][:1000]}\n```",
                "type": "output",
            })

    async def render_research_results(
        self, query: str, results: Dict[str, Any]
    ) -> None:
        """Send research results to the UI."""
        await self._emit_event("chat.message", {
            "role": "assistant",
            "text": f"Research results for: {query}",
            "type": "research",
            "results": results,
        })

    async def set_focus_mode(
        self, mode: str, workspace: str = None
    ) -> None:
        """
        Update the UI focus mode.

        This sends a focus change event that the Morphable UI
        responds to by adjusting panel proportions and visibility.
        """
        await self._emit_state("focus.mode_changed", {
            "mode": mode,
            "workspace": workspace or self.workspace,
        })

    # ================================================================
    # WORKSPACE CONTROL (agent commands)
    # ================================================================

    async def switch_workspace(self, workspace: str) -> None:
        """
        Command the UI to switch workspace.

        Triggers a FLIP animation in the browser.
        """
        self.workspace = workspace
        await self._emit_event("ui.workspace", {
            "workspace": workspace,
        })

    async def show_panel(
        self,
        slot: str,
        panel_type: str,
        config: Dict[str, Any] = None,
    ) -> None:
        """Command the UI to show a panel in a slot."""
        await self._emit_event("ui.panel.show", {
            "slot": slot,
            "type": panel_type,
            "config": config or {},
        })

    async def hide_panel(self, slot: str) -> None:
        """Command the UI to hide (collapse) a panel."""
        await self._emit_event("ui.panel.hide", {"slot": slot})

    async def swap_panel(
        self,
        slot: str,
        panel_type: str,
        config: Dict[str, Any] = None,
    ) -> None:
        """Command the UI to swap a panel in a slot."""
        await self._emit_event("ui.panel.swap", {
            "slot": slot,
            "type": panel_type,
            "config": config or {},
        })

    async def highlight_panel(
        self, panel_id: str, color: str = None
    ) -> None:
        """Command the UI to highlight a panel."""
        await self._emit_event("ui.highlight", {
            "panel": panel_id,
            "color": color,
        })

    async def create_pipeline(
        self,
        pipeline_id: str,
        definition: Dict[str, Any],
        slot: str,
    ) -> None:
        """
        Command the UI to create a data pipeline.

        Args:
            pipeline_id: Unique pipeline ID
            definition: Pipeline config (source + transform + title)
            slot: Slot to render pipeline output in
        """
        await self._emit_event("ui.pipeline.create", {
            "id": pipeline_id,
            "definition": definition,
            "slot": slot,
        })

    async def destroy_pipeline(self, pipeline_id: str) -> None:
        """Command the UI to destroy a pipeline."""
        await self._emit_event("ui.pipeline.destroy", {
            "id": pipeline_id,
        })

    # ================================================================
    # INTERNAL — Bus emission
    # ================================================================

    async def _emit_event(
        self, event_type: str, payload: Dict[str, Any]
    ) -> None:
        """Emit an event to the bus for UI consumption."""
        from ..bus.message import BusMessage, MessageType, Priority

        message = BusMessage(
            type=MessageType.EVENT,
            source="web_adapter",
            target="morphable_ui",
            workspace=self.workspace,
            payload={"event": event_type, **payload},
            priority=Priority.NORMAL,
        )
        await self.bus.send(message)

    async def _emit_state(
        self, event_type: str, payload: Dict[str, Any]
    ) -> None:
        """Emit a state event to the bus."""
        from ..bus.message import BusMessage, MessageType, Priority

        message = BusMessage(
            type=MessageType.STATE,
            source="web_adapter",
            target="*",
            workspace=self.workspace,
            payload={"event": event_type, **payload},
            priority=Priority.NORMAL,
        )
        await self.bus.send(message)
