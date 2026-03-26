"""
Web server for BigBrain's Morphable UI.

aiohttp server providing:
  - Static file serving (HTML/JS/CSS)
  - WebSocket bridge to the Python MessageBus
  - Focus state synchronization
  - Pipeline management endpoints

The server bridges the browser (via WebSocket) to the internal
MessageBus, allowing panels to be autonomous bus subscribers.
"""

import asyncio
import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set, TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from ..bus.bus import MessageBus
    from ..bus.message import BusMessage
    from ..front.focus_manager import FocusManager

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


class WebServer:
    """
    aiohttp web server for the Morphable UI.

    Bridges browser WebSocket connections to the BigBrain MessageBus.
    Each connected browser gets bus events routed to it, and can send
    messages back to the bus.
    """

    def __init__(
        self,
        bus: "MessageBus",
        focus_manager: "Optional[FocusManager]" = None,
        host: str = "0.0.0.0",
        port: int = 8080,
        auth_password: "Optional[str]" = None,
    ):
        """
        Initialize the web server.

        Args:
            bus: BigBrain MessageBus instance
            focus_manager: Focus manager for state sync
            host: Bind address
            port: Bind port
            auth_password: Optional HTTP Basic Auth password (user: bigbrain).
                          If None, checks BIGBRAIN_WEB_PASSWORD env var.
                          If neither set, no auth is required.
        """
        self.bus = bus
        self.focus_manager = focus_manager
        self.host = host
        self.port = port
        self._auth_password = auth_password or os.environ.get("BIGBRAIN_WEB_PASSWORD")

        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._ws_clients: Set[web.WebSocketResponse] = set()
        self._running = False

        # Replay buffer: stores recent important messages so reconnecting
        # clients don't miss results (fixes WS disconnect data loss)
        self._replay_buffer: list = []  # List of (timestamp, serialized_msg)
        self._replay_max_age = 300  # 5 minutes
        self._replay_max_size = 100
        self._REPLAY_TYPES = {"result", "progress"}
        self._REPLAY_EVENTS = {
            "task.received", "task.complete", "task.failed",
            "subtask.started", "subtask.complete", "subtask.failed",
            "brain.started", "brain.complete",
        }

    async def start(self) -> None:
        """Start the web server."""
        if self._running:
            return

        middlewares = []
        if self._auth_password:
            middlewares.append(self._auth_middleware)
            logger.info("WebServer: Basic Auth enabled (user: bigbrain)")

        self._app = web.Application(middlewares=middlewares)
        self._setup_routes()

        # Clear replay buffer on start — stale events from previous runs are invalid
        self._replay_buffer.clear()

        # Subscribe to ALL bus messages to forward to WebSocket clients
        self.bus.subscribe("*", self._on_bus_message)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        self._running = True

        logger.info("WebServer started on http://%s:%d", self.host, self.port)

    async def stop(self) -> None:
        """Stop the web server."""
        if not self._running:
            return

        self._running = False

        # Unsubscribe from bus
        self.bus.unsubscribe("*", self._on_bus_message)

        # Close all WebSocket connections
        for ws in list(self._ws_clients):
            await ws.close(code=1001, message=b"Server shutting down")
        self._ws_clients.clear()

        # Shutdown aiohttp
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

        logger.info("WebServer stopped")

    @property
    def url(self) -> str:
        """Get the server URL."""
        return f"http://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        """Get the WebSocket URL."""
        return f"ws://{self.host}:{self.port}/ws"

    @property
    def client_count(self) -> int:
        """Number of connected WebSocket clients."""
        return len(self._ws_clients)

    # ================================================================
    # ROUTES
    # ================================================================

    # ================================================================
    # AUTH MIDDLEWARE
    # ================================================================

    @web.middleware
    async def _auth_middleware(self, request: web.Request, handler):
        """HTTP Basic Auth middleware. Skips if no password configured."""
        if not self._auth_password:
            return await handler(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                user, passwd = decoded.split(":", 1)
                if user == "bigbrain" and passwd == self._auth_password:
                    return await handler(request)
            except Exception:
                pass

        # WebSocket upgrade requests pass auth via query param (browsers
        # can't set custom headers on WebSocket connections)
        if request.path == "/ws":
            token = request.query.get("token")
            if token == self._auth_password:
                return await handler(request)

        return web.Response(
            status=401,
            headers={"WWW-Authenticate": 'Basic realm="BigBrain"'},
            text="Authentication required",
        )

    def _setup_routes(self) -> None:
        """Configure HTTP routes."""
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_get("/ws", self._handle_websocket)
        self._app.router.add_get("/api/focus", self._handle_focus_get)
        self._app.router.add_post("/api/focus", self._handle_focus_set)
        self._app.router.add_get("/api/status", self._handle_status)

        # Static files (JS, CSS, images) — with no-cache for dev
        if STATIC_DIR.exists():
            self._app.router.add_get("/static/{filename:.+}", self._handle_static)

    async def _handle_static(self, request: web.Request) -> web.FileResponse:
        """Serve static files with no-cache headers."""
        filename = request.match_info["filename"]
        file_path = STATIC_DIR / filename
        if not file_path.exists() or not file_path.is_file():
            return web.Response(status=404, text="Not found")
        headers = {"Cache-Control": "no-cache, must-revalidate"}
        return web.FileResponse(file_path, headers=headers)

    async def _handle_index(self, request: web.Request) -> web.Response:
        """Serve the main HTML page, injecting WS auth token if auth is enabled."""
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            return web.Response(text="BigBrain Morphable UI", content_type="text/html")

        html = index_path.read_text()

        # Inject WS auth token so bus-client.js can authenticate the WebSocket
        if self._auth_password:
            html = html.replace(
                '<body data-focus-mode="normal">',
                f'<body data-focus-mode="normal" data-ws-token="{self._auth_password}">',
            )

        return web.Response(
            text=html, content_type="text/html",
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )

    async def _handle_status(self, request: web.Request) -> web.Response:
        """Server status endpoint."""
        return web.json_response({
            "status": "running",
            "clients": self.client_count,
            "bus_stats": self.bus.get_stats(),
            "focus": self._get_focus_snapshot(),
        })

    async def _handle_focus_get(self, request: web.Request) -> web.Response:
        """Get current focus state."""
        return web.json_response(self._get_focus_snapshot())

    async def _handle_focus_set(self, request: web.Request) -> web.Response:
        """Update focus state from the UI."""
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        workspace = data.get("workspace")
        mode = data.get("mode")

        if self.focus_manager:
            if workspace:
                from ..front.focus_manager import FocusState
                self.focus_manager.set_workspace_focus(
                    workspace, FocusState.ACTIVE, "ui"
                )
            if mode:
                from ..front.focus_manager import FocusMode
                mode_enum = {
                    "deep_focus": FocusMode.DEEP_FOCUS,
                    "normal": FocusMode.NORMAL,
                    "overview": FocusMode.OVERVIEW,
                }.get(mode)
                if mode_enum:
                    self.focus_manager.set_focus_mode(mode_enum, "ui")

        return web.json_response({"ok": True})

    # ================================================================
    # WEBSOCKET HANDLER
    # ================================================================

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """
        Handle a WebSocket connection from the browser.

        Each browser tab gets its own WebSocket. Messages from the bus
        are forwarded to all connected clients. Messages from the client
        are forwarded to the bus.
        """
        ws = web.WebSocketResponse(
            heartbeat=30.0,
            max_msg_size=1024 * 1024,  # 1MB
        )
        await ws.prepare(request)

        self._ws_clients.add(ws)
        logger.info("WebSocket client connected (%d total)", self.client_count)

        # Send initial state
        await self._send_initial_state(ws)

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await self._handle_ws_message(ws, msg.data)
                elif msg.type == web.WSMsgType.ERROR:
                    logger.warning(
                        "WebSocket error: %s", ws.exception()
                    )
        finally:
            self._ws_clients.discard(ws)
            logger.info(
                "WebSocket client disconnected (%d remaining)",
                self.client_count,
            )

        return ws

    async def _send_initial_state(self, ws: web.WebSocketResponse) -> None:
        """Send current system state to a newly connected client."""
        try:
            # Focus state
            await ws.send_json({
                "type": "state",
                "source": "server",
                "target": "morphable_ui",
                "payload": {
                    "event": "focus.initial",
                    **self._get_focus_snapshot(),
                },
            })

            # Bus stats
            await ws.send_json({
                "type": "event",
                "source": "server",
                "target": "morphable_ui",
                "payload": {
                    "event": "system.status",
                    "stats": self.bus.get_stats(),
                },
            })

            # Replay buffered messages (results, task/subtask events, progress)
            # so reconnecting clients don't lose data from WS drops
            replayed = 0
            for _ts, data in self._replay_buffer:
                try:
                    # Mark as replay so client can handle dedup
                    replay_msg = {**data, "_replay": True}
                    await ws.send_json(replay_msg)
                    replayed += 1
                except Exception:
                    break  # Client probably disconnected again
            if replayed:
                logger.info("Replayed %d buffered messages to reconnecting client", replayed)

        except Exception as e:
            logger.warning("Failed to send initial state: %s", e)

    async def _handle_ws_message(
        self, ws: web.WebSocketResponse, raw: str
    ) -> None:
        """
        Handle a message from a WebSocket client.

        Messages from the UI are forwarded to the MessageBus.
        The source is always set to 'morphable_ui' for security.
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON from WebSocket client")
            return

        # Force source to morphable_ui (prevent spoofing)
        data["source"] = "morphable_ui"

        # Create a BusMessage and send it
        from ..bus.message import BusMessage, MessageType, Priority

        try:
            msg_type = MessageType(data.get("type", "event"))
        except ValueError:
            msg_type = MessageType.EVENT

        try:
            priority = Priority(data.get("priority", 1))
        except ValueError:
            priority = Priority.NORMAL

        message = BusMessage(
            type=msg_type,
            source="morphable_ui",
            target=data.get("target", "*"),
            workspace=data.get("workspace"),
            payload=data.get("payload", {}),
            priority=priority,
        )

        await self.bus.send(message)

    # ================================================================
    # BUS → WEBSOCKET BRIDGE
    # ================================================================

    async def _on_bus_message(self, message: "BusMessage") -> None:
        """
        Forward bus messages to all connected WebSocket clients.

        This is the bridge: every message on the Python MessageBus
        gets serialized and sent to every browser tab.
        """
        # Extract metadata for logging and buffering
        msg_type = message.type if isinstance(message.type, str) else message.type.value
        event = (message.payload or {}).get("event", "")
        stage = (message.payload or {}).get("stage", "")

        # Serialize to JSON-safe dict (always — needed for buffering)
        try:
            data = message.to_log_dict()
        except Exception:
            data = {
                "type": str(message.type),
                "source": message.source,
                "target": message.target,
                "payload": message.payload,
                "timestamp": message.timestamp,
            }

        # Buffer important messages BEFORE checking for clients.
        # This ensures events are captured even when no browser is connected,
        # so reconnecting clients get the full replay.
        self._maybe_buffer(msg_type, event, data)

        if not self._ws_clients:
            return
        
        # Debug: log ALL forwarded messages (temporary)
        # Skip noisy focus state broadcasts
        if not (msg_type == "state" and "focus" in event):
            print(f"[WS→{len(self._ws_clients)}] {msg_type:10} {event:25} src={message.source} {f'stage={stage}' if stage else ''}")

        # Broadcast to all clients
        closed = []
        for ws in self._ws_clients:
            try:
                await ws.send_json(data)
            except (ConnectionResetError, RuntimeError):
                closed.append(ws)
            except Exception as e:
                logger.debug("WS send error: %s", e)
                closed.append(ws)

        # Clean up closed connections
        for ws in closed:
            self._ws_clients.discard(ws)

    # ================================================================
    # REPLAY BUFFER
    # ================================================================

    # Events where a later event supersedes the earlier one for the same source.
    # e.g. brain.complete cancels brain.started for the same brain.
    _SUPERSEDE_PAIRS = {
        "brain.complete": "brain.started",
        "brain.started": "brain.complete",  # new task supersedes idle
        "subtask.complete": "subtask.started",
        "subtask.failed": "subtask.started",
        "task.complete": "task.received",
        "task.failed": "task.received",
    }

    def _maybe_buffer(self, msg_type: str, event: str, data: dict) -> None:
        """Store important messages for replay on reconnect.
        
        Uses supersede logic: brain.complete removes buffered brain.started
        for the same source, preventing stale "WORKING" state on reconnect.
        """
        should_buffer = (
            msg_type in self._REPLAY_TYPES
            or event in self._REPLAY_EVENTS
        )
        if not should_buffer:
            return

        now = time.time()

        # Prune old entries
        cutoff = now - self._replay_max_age
        self._replay_buffer = [
            (ts, d) for ts, d in self._replay_buffer if ts > cutoff
        ]

        # Supersede: remove conflicting earlier events for the same source
        supersedes = self._SUPERSEDE_PAIRS.get(event)
        if supersedes:
            source = data.get("source", "")
            self._replay_buffer = [
                (ts, d) for ts, d in self._replay_buffer
                if not (
                    (d.get("payload") or {}).get("event") == supersedes
                    and d.get("source") == source
                )
            ]

        # Trim to max size (drop oldest)
        while len(self._replay_buffer) >= self._replay_max_size:
            self._replay_buffer.pop(0)

        self._replay_buffer.append((now, data))

    # ================================================================
    # HELPERS
    # ================================================================

    def _get_focus_snapshot(self) -> Dict[str, Any]:
        """Get current focus state as a dict."""
        if not self.focus_manager:
            return {"workspaces": {}, "mode": "normal"}

        return self.focus_manager.get_focus_status()
