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
import tempfile
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
# Aplot-based React UI build output (web-ui/; see docs/WEBUI-APLOT-PORT.md).
WEBUI_DIST = Path(__file__).resolve().parents[2] / "web-ui" / "dist"

# Runtime provider-reload hook, set by BigBrainSystem when it wires the
# web server (keeps WebServer free of a system dependency). Mirrored on the
# class for convenient access in tests.
PROVIDER_RELOAD_HOOK = None

# Set when a working project is selected — re-targets agent writes.
PROJECT_CHANGE_HOOK = None

# Set when a plugin is toggled — applies the change at runtime where feasible.
PLUGINS_CHANGE_HOOK = None

# Set when the user hits Stop — cancels the front brain stream and the
# running orchestrated task (chat.cancel frame). Async hook.
CANCEL_HOOK = None


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
        self._chat_tasks: set[asyncio.Task] = set()
        self._running = False

        # Replay buffer: stores recent important messages so reconnecting
        # clients don't miss results (fixes WS disconnect data loss)
        self._replay_buffer: list = []  # List of (timestamp, serialized_msg)
        self._replay_max_age = 300  # 5 minutes
        self._replay_max_size = 100
        self._REPLAY_TYPES = {"result", "progress"}
        self._REPLAY_EVENTS = {
            "task.received", "task.complete", "task.failed", "task.cancelled",
            "subtask.started", "subtask.complete", "subtask.failed",
            "brain.started", "brain.complete",
            "chat.message",  # Front brain summary / chat responses
            "chat.done",    # Final text of a streamed reply
            "task.routing", # Session-scoped pre-orchestrator activity
            # Contract approval proposals are LIVE PENDING STATE — a client
            # reconnecting while a plan awaits approval must see the card.
            "contracts.proposal",
            # NOTE: chat.delta is deliberately absent — transient chunks.
        }

        # Chat history: sessions are the single source of truth
        # (data/sessions/). The legacy in-memory buffer is gone.
        from .sessions import SessionStore
        self._sessions = SessionStore()
        # The session the last chat.send targeted — used to capture
        # chat.done/chat.message replies that don't carry a session id.
        self._active_session_id: str | None = None

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
        tasks = list(self._chat_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
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
        self._app.router.add_get("/", self._handle_root)
        self._app.router.add_get("/ws", self._handle_websocket)
        self._app.router.add_get("/api/focus", self._handle_focus_get)
        self._app.router.add_post("/api/focus", self._handle_focus_set)
        self._app.router.add_post("/api/contracts/approve",
                                  self._handle_contracts_approve)
        self._app.router.add_get("/api/status", self._handle_status)
        self._app.router.add_get("/api/preview-logs", self._handle_preview_logs)

        # Provider registry + connection pipelines (Phase 3/4):
        # the settings "buttons" poll these endpoints.
        self._app.router.add_get("/api/models", self._handle_models)
        self._app.router.add_get("/api/usage", self._handle_usage)
        self._app.router.add_get("/api/auth/codex/status", self._handle_codex_status)
        self._app.router.add_post("/api/auth/codex/login", self._handle_codex_login)
        self._app.router.add_post("/api/auth/mistral/start", self._handle_mistral_start)
        self._app.router.add_get("/api/auth/mistral/poll", self._handle_mistral_poll)
        self._app.router.add_post("/api/auth/mistral/complete", self._handle_mistral_complete)

        # Static files (JS, CSS, images) — with no-cache for dev
        if STATIC_DIR.exists():
            self._app.router.add_get("/static/{filename:.+}", self._handle_static)

        # Aplot React UI build (web-ui/dist): assets + root public files
        # (robot-icon.png, robot-mascot.png…); the root route (_handle_root)
        # serves its index when the build exists.
        if WEBUI_DIST.exists():
            self._app.router.add_get("/assets/{filename:.+}", self._handle_webui_asset)
            self._app.router.add_get("/{filename}", self._handle_webui_public)

        # Real workspace filesystem API (replaces the UI's mock file tree).
        from .fs_api import setup_fs_routes
        setup_fs_routes(self._app)

        # Streaming manual runs: fs_api pushes fs.run_output / fs.run_result
        # through the bus so every connected browser sees them on its WS.
        from .fs_api import set_event_sink
        from ..bus.message import Priority as _Priority

        async def _fs_event_sink(event_type: str, payload: dict) -> None:
            await self.bus.broadcast_event(
                source="morphable_ui",
                event_type=event_type,
                payload=payload,
                priority=_Priority.NORMAL,
            )

        set_event_sink(_fs_event_sink)
        from .evidence_api import setup_evidence_routes
        setup_evidence_routes(self._app)
        from .taskboard import setup_taskboard_routes
        setup_taskboard_routes(self._app)
        from .attachments import setup_attachment_routes
        setup_attachment_routes(self._app)

        # Per-role model lineup (the top-left dropdown) + OpenRouter key.
        self._app.router.add_get("/api/models/roles", self._handle_model_roles)
        self._app.router.add_post("/api/models/roles", self._handle_model_role_set)
        self._app.router.add_post("/api/auth/openrouter/key", self._handle_openrouter_key)
        self._app.router.add_post("/api/auth/mistral-studio/key", self._handle_mistral_studio_key)
        self._app.router.add_post("/api/system/reload-provider", self._handle_reload_provider)
        self._app.router.add_get("/api/fs/current-project", self._handle_current_project_get)
        self._app.router.add_post("/api/fs/current-project", self._handle_current_project_set)
        self._app.router.add_get("/api/plugins", self._handle_plugins)
        self._app.router.add_post("/api/plugins/toggle", self._handle_plugin_toggle)

    async def _handle_models(self, request: web.Request) -> web.Response:
        """List registry models with TRUTHFUL availability (no secrets).

        Availability is the free-probe health (60s cache), not mere env-key
        presence — a stale or invalid key must not show a green pill.
        """
        from ..llm import model_registry
        from ..llm.model_registry import list_models

        health = await model_registry.verify_all()
        models = list_models()
        for model in models:
            model["available"] = health.get(model["key"]) == "ok"
            model["health"] = health.get(model["key"], "unknown")
        return web.json_response({"models": models})

    async def _handle_usage(self, request: web.Request) -> web.Response:
        """Aggregate token/cost ledger (Phase 5) — no message content."""
        from ..llm.usage import get_tracker

        return web.json_response(get_tracker().totals())

    async def _handle_reload_provider(self, request: web.Request) -> web.Response:
        """Rebuild the LLM provider at runtime (after connecting a key).

        Without this, keys added at runtime never reach the chat — the
        provider is built once at system start. The system registers the
        reload hook when it wires the web server.
        """
        from ..llm import model_registry

        hook = PROVIDER_RELOAD_HOOK
        if hook is None:
            return web.json_response(
                {"error": "system not wired for provider reload"}, status=503
            )
        result = hook()
        # Fresh health: the newly connected provider must light up at once.
        model_registry._health_cache.clear()
        return web.json_response(result)

    async def _handle_plugins(self, request: web.Request) -> web.Response:
        """Plugin catalog with live enabled state (docs/BRAIN-PLUGINS.md)."""
        from ..plugins import list_plugins

        return web.json_response(list_plugins())

    async def _handle_plugin_toggle(self, request: web.Request) -> web.Response:
        """Enable/disable a brain plugin; the system hook applies it."""
        from ..plugins import set_enabled

        body = await request.json()
        try:
            result = set_enabled(body.get("id", ""), bool(body.get("enabled")))
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        if PLUGINS_CHANGE_HOOK is not None:
            PLUGINS_CHANGE_HOOK(result["id"], result["enabled"])
        return web.json_response(result)

    async def _handle_current_project_get(self, request: web.Request) -> web.Response:
        """The project the chat/agent is currently working in."""
        from .fs_api import get_current_project

        return web.json_response({"project": get_current_project()})

    async def _handle_current_project_set(self, request: web.Request) -> web.Response:
        """Select the working project; the system hook re-targets agent
        writes (python brain work_dir) and the front brain context."""
        from .fs_api import set_current_project

        body = await request.json()
        try:
            result = set_current_project(body.get("project"))
        except web.HTTPBadRequest as exc:
            return web.json_response({"error": exc.text}, status=400)
        if PROJECT_CHANGE_HOOK is not None:
            PROJECT_CHANGE_HOOK()
        return web.json_response(result)

    async def _handle_model_roles(self, request: web.Request) -> web.Response:
        """Current per-role model lineup (front/planner/code/subagent)."""
        from .model_roles import current_lineup

        return web.json_response({"roles": current_lineup()})

    async def _handle_model_role_set(self, request: web.Request) -> web.Response:
        """Assign a registry key to a role; persisted + mirrored to env."""
        from .model_roles import set_role

        body = await request.json()
        try:
            result = set_role(body.get("role", ""), body.get("key", ""))
        except (ValueError, KeyError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(result)

    async def _handle_openrouter_key(self, request: web.Request) -> web.Response:
        """Connect with OpenRouter (API key): free-probe validate, store, activate.

        The key itself never appears in the response.
        """
        from .openrouter_key import OpenRouterKeyError, connect_key

        body = await request.json()
        try:
            result = await connect_key(body.get("key", ""))
        except OpenRouterKeyError as exc:
            return web.json_response({"error": str(exc)}, status=401)
        return web.json_response(result)

    async def _handle_mistral_studio_key(self, request: web.Request) -> web.Response:
        """Connect a developer API key from Mistral Studio."""
        from .mistral_studio_key import MistralStudioKeyError, connect_key

        body = await request.json()
        try:
            result = await connect_key(body.get("key", ""))
        except MistralStudioKeyError as exc:
            return web.json_response({"error": str(exc)}, status=401)
        return web.json_response(result)

    async def _handle_codex_status(self, request: web.Request) -> web.Response:
        """Who is signed in to the codex app-server (poll target)."""
        from ..llm.codex_provider import codex_auth_status

        return web.json_response(await codex_auth_status())

    async def _handle_codex_login(self, request: web.Request) -> web.Response:
        """Start the Connect-with-ChatGPT flow; returns the authUrl.

        codex owns the OAuth callback and credential storage (~/.codex);
        the UI polls /api/auth/codex/status until the account appears.
        """
        from ..llm.codex_provider import codex_start_login

        body = await request.json() if request.can_read_body else {}
        try:
            result = await codex_start_login(open_browser=body.get("open_browser", True))
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=502)
        return web.json_response(result)

    async def _handle_mistral_start(self, request: web.Request) -> web.Response:
        """Start the PKCE browser sign-in; returns the sign_in_url."""
        from ..auth.mistral_oauth import SetupError, start_browser_sign_in

        try:
            summary = await start_browser_sign_in()
        except SetupError as exc:
            return web.json_response({"error": str(exc)}, status=502)
        return web.json_response(summary)

    async def _handle_mistral_poll(self, request: web.Request) -> web.Response:
        """Poll the in-flight browser sign-in once (client sets cadence)."""
        from ..auth.mistral_oauth import poll_browser_sign_in

        return web.json_response(await poll_browser_sign_in())

    async def _handle_mistral_complete(self, request: web.Request) -> web.Response:
        """Exchange the completed sign-in for an API key and store it.

        The key never appears in the response — only the stored credential's
        health (free GET /v1/models probe).
        """
        from ..auth.mistral_oauth import SetupError, complete_browser_sign_in

        try:
            result = await complete_browser_sign_in()
        except SetupError as exc:
            return web.json_response({"error": str(exc)}, status=409)
        return web.json_response(result)

    async def _handle_static(self, request: web.Request) -> web.FileResponse:
        """Serve static files with no-cache headers."""
        filename = request.match_info["filename"]
        file_path = STATIC_DIR / filename
        if not file_path.exists() or not file_path.is_file():
            return web.Response(status=404, text="Not found")
        headers = {"Cache-Control": "no-cache, must-revalidate"}
        return web.FileResponse(file_path, headers=headers)

    async def _handle_root(self, request: web.Request) -> web.Response:
        """Serve the Aplot React build if present, else the legacy page."""
        dist_index = WEBUI_DIST / "index.html"
        if dist_index.exists():
            return web.FileResponse(
                dist_index,
                headers={"Cache-Control": "no-cache, must-revalidate"},
            )
        return await self._handle_index(request)

    async def _handle_webui_public(self, request: web.Request) -> web.FileResponse:
        """Serve root-level files from the build (public/: robot images…).

        Registered last-resort for single-segment paths; anything not a real
        file in dist/ 404s normally.
        """
        filename = request.match_info["filename"]
        if "/" in filename or filename.startswith("."):
            return web.Response(status=404, text="Not found")
        file_path = (WEBUI_DIST / filename).resolve()
        if not str(file_path).startswith(str(WEBUI_DIST.resolve())):
            return web.Response(status=404, text="Not found")
        if not file_path.is_file():
            return web.Response(status=404, text="Not found")
        return web.FileResponse(file_path, headers={
            "Cache-Control": "no-cache, must-revalidate",
        })

    async def _handle_webui_asset(self, request: web.Request) -> web.FileResponse:
        """Serve built assets from web-ui/dist/assets (immutable hashed files)."""
        filename = request.match_info["filename"]
        file_path = (WEBUI_DIST / "assets" / filename).resolve()
        # Contained path check: no traversal outside dist/assets.
        if not str(file_path).startswith(str((WEBUI_DIST / "assets").resolve())):
            return web.Response(status=404, text="Not found")
        if not file_path.is_file():
            return web.Response(status=404, text="Not found")
        return web.FileResponse(file_path)

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

    async def _handle_preview_logs(self, request: web.Request) -> web.Response:
        """Preview server diagnostics — shows active previews, project files, and errors."""
        from ..brains.python_brain import PythonBrain
        from ..brains.web_app_brain import WebAppBrain
        import glob

        previews = []
        for port, proc in PythonBrain._active_previews.items():
            previews.append({
                "port": port,
                "pid": proc.pid if proc else None,
                "alive": proc.returncode is None if proc else False,
                "exit_code": proc.returncode if proc and proc.returncode is not None else None,
            })
        for port, proc in WebAppBrain._active_previews.items():
            previews.append({
                "kind": "web_app", "port": port,
                "pid": proc.pid if proc else None,
                "alive": proc.returncode is None if proc else False,
                "exit_code": proc.returncode if proc and proc.returncode is not None else None,
            })

        # Scan for project dirs and their files
        projects = []
        pool_dir = Path(tempfile.gettempdir()) / "bigbrain_python_pool"
        if pool_dir.exists():
            for proj in sorted(pool_dir.iterdir()):
                if proj.is_dir() and not proj.name.startswith("."):
                    files = [
                        str(f.relative_to(proj))
                        for f in proj.rglob("*")
                        if f.is_file() and ".venv" not in f.parts
                    ]
                    # Try to read any error logs
                    error_log = ""
                    for log_name in ["chat_app.log", "error.log", "app.log"]:
                        log_file = proj / log_name
                        if log_file.exists():
                            error_log += log_file.read_text(errors="replace")[-3000:]
                    projects.append({
                        "name": proj.name,
                        "files": files,
                        "has_venv": (proj / ".venv").exists(),
                        "error_log": error_log or None,
                    })

        return web.json_response({
            "active_previews": previews,
            "projects": projects,
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

    async def _handle_contracts_approve(self, request: web.Request) -> web.Response:
        """User verdict on a proposed contract set (Phase B approval flow).

        Forwards the decision to the orchestrator over the bus — the
        orchestrator resumes or cancels the paused plan and stamps the
        approval on the DesignSpec (evidence).
        """
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        design_id = data.get("design_id")
        plan_id = data.get("plan_id")
        if not design_id or not plan_id:
            return web.json_response(
                {"error": "design_id and plan_id are required"}, status=400)

        await self.bus.send_task(
            # Source MUST be a bus-authenticated component ("morphable_ui"
            # has an HMAC token, like chat.send) — an unknown source is
            # silently DROPPED by the authenticated bus and the plan would
            # wait forever.
            source="morphable_ui",
            target="orchestrator_default",
            task_data={
                "type": "contracts.approval",
                "design_id": design_id,
                "plan_id": plan_id,
                "approve": bool(data.get("approve")),
            },
        )
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

        # Handshake: the Aplot adapter waits for this before it is
        # 'connected' (same contract as the Scratchy gateway).
        await ws.send_json({
            "type": "welcome",
            "payload": {
                "server": "bigbrain",
                "auth": bool(self._auth_password),
                "version": "0.1.0",
            },
        })

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

        Control frames (Aplot adapter protocol) are answered directly:
        ping → pong, chat.send → bus task + acks, req chat.history → resp.
        Everything else is forwarded to the MessageBus with the source
        forced to 'morphable_ui' (prevents spoofing).
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON from WebSocket client")
            return

        # -- Control frames (never reach the bus) --------------------------
        if data.get("type") == "ping":
            await ws.send_json({"type": "pong", "payload": {}})
            return

        if data.get("type") == "chat.send":
            task = asyncio.create_task(self._handle_chat_send(ws, data))
            self._chat_tasks.add(task)
            task.add_done_callback(self._chat_finished)
            return

        if data.get("type") == "chat.cancel":
            tasks = list(self._chat_tasks)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if CANCEL_HOOK is not None:
                try:
                    result = CANCEL_HOOK()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.warning("chat.cancel hook failed: %s", e)
            await self.bus.broadcast_event(
                source="morphable_ui", event_type="task.cancelled",
                payload={"session_id": self._active_session_id, "mode": "user"})
            return

        if data.get("type") == "req":
            await self._handle_request(ws, data)
            return

        # -- Bus passthrough (legacy protocol) -----------------------------

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

    def _chat_finished(self, task: asyncio.Task) -> None:
        self._chat_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Chat delivery failed: %s", task.exception())

    async def _handle_chat_send(
        self, ws: web.WebSocketResponse, data: dict
    ) -> None:
        """Aplot chat.send: one user message → front brain via the bus.

        Mirrors the legacy UI's frame exactly (task → front_brain with
        payload.type user_message) and adds the message-status acks the
        Aplot adapter expects (queued → sent).
        """
        payload = data.get("payload") or {}
        text = (payload.get("text") or "").strip()
        if not text:
            return
        message_id = payload.get("messageId") or data.get("messageId")

        async def ack(status: str) -> None:
            if not message_id:
                return
            await ws.send_json({
                "type": "message.status",
                "payload": {"messageId": message_id, "status": status},
            })

        await ack("queued")

        # Sessions: the message belongs to the client's session (created
        # lazily if unknown); without a sessionId the active session is
        # used, or a fresh one starts.
        session_id = payload.get("sessionId") or self._active_session_id
        session = self._sessions.ensure(session_id)
        self._active_session_id = session["id"]
        # Exact persisted context before this new turn. The front brain keeps
        # a fast in-memory window, but it must be rehydratable after restart.
        conversation_history = [
            {"role": item.get("role"), "content": item.get("text", "")}
            for item in (session.get("messages") or [])[-20:]
            if item.get("role") in ("user", "assistant") and item.get("text")
        ]
        self._sessions.append_message(session["id"], "user", text)

        from ..bus.message import BusMessage, MessageType, Priority

        # Attachment refs uploaded via POST /api/attachments travel with
        # the message so the front brain can record them in memory.
        attachments = [
            {"id": a.get("id"), "name": a.get("name"), "type": a.get("type")}
            for a in (payload.get("attachments") or [])
            if isinstance(a, dict) and a.get("id")
        ]

        await self.bus.send(BusMessage(
            type=MessageType.TASK,
            source="morphable_ui",
            target="front_brain",
            payload={"type": "user_message", "text": text,
                     "attachments": attachments,
                     "session_id": session["id"],
                     "conversation_history": conversation_history},
            priority=Priority.NORMAL,
        ))

        await ack("sent")

    async def _handle_request(
        self, ws: web.WebSocketResponse, data: dict
    ) -> None:
        """Aplot req/res bridge: chat history + session management."""
        request_id = data.get("id")
        method = data.get("method")
        params = data.get("params") or {}
        if method == "chat.history":
            session_id = params.get("sessionId") or self._active_session_id
            session = self._sessions.get(session_id) if session_id else None
            await ws.send_json({
                "type": "resp",
                "id": request_id,
                "payload": {
                    "messages": (session or {}).get("messages", []),
                    "sessionId": (session or {}).get("id"),
                },
            })
            return
        if method == "sessions.list":
            await ws.send_json({
                "type": "resp", "id": request_id,
                "payload": {"sessions": self._sessions.list()},
            })
            return
        if method == "sessions.create":
            session = self._sessions.create(params.get("title"))
            await ws.send_json({
                "type": "resp", "id": request_id,
                "payload": {"session": {
                    "id": session["id"], "title": session["title"],
                    "updated_at": session["updated_at"], "message_count": 0,
                }},
            })
            return
        if method == "sessions.delete":
            await ws.send_json({
                "type": "resp", "id": request_id,
                "payload": {"deleted": self._sessions.delete(
                    params.get("sessionId", ""))},
            })
            return
        await ws.send_json({
            "type": "resp",
            "id": request_id,
            "error": f"unknown method: {method}",
        })

    def _append_chat_history(self, role: str, text: str) -> None:
        """Compat wrapper: append to the ACTIVE session (creating one if
        none exists). Sessions are the single source of chat history."""
        target = self._active_session_id or self._sessions.ensure(None)["id"]
        self._active_session_id = target
        self._sessions.append_message(target, role, text)

    def _capture_to_session(self, session_id: str | None,
                            role: str, text: str) -> None:
        """Persist a reply into its session.

        Untagged events (system announcements at startup, TUI replies)
        capture into the ACTIVE session when one exists — they must
        never CREATE a session: the old behavior minted junk
        'New conversation' sessions holding only the startup banner.
        """
        target = session_id or self._active_session_id
        if not target:
            return
        self._sessions.append_message(target, role, text)

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

        # Chat history: capture assistant/system messages for chat.history.
        # Sessions: capture assistant/system replies into the session the
        # front brain tags (payload session_id), falling back to the
        # active session. chat.done carries the full text of a STREAMED
        # reply (the deltas themselves are transient and never stored).
        if event == "chat.done":
            payload = message.payload or {}
            text = payload.get("text")
            if isinstance(text, str) and text.strip():
                self._capture_to_session(
                    payload.get("session_id"), "assistant", text)
        elif event == "chat.message":
            payload = message.payload or {}
            role = payload.get("role", "assistant")
            text = payload.get("text")
            if isinstance(text, str) and text.strip() and role in ("assistant", "system", "user"):
                self._capture_to_session(payload.get("session_id"), role, text)

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
        # A terminal task also resolves the pre-orchestrator routing marker.
        # There is only one foreground routed run in the current UI.
        if event in ("task.complete", "task.failed", "task.cancelled"):
            self._replay_buffer = [
                (ts, buffered) for ts, buffered in self._replay_buffer
                if (buffered.get("payload") or {}).get("event") not in (
                    "task.routing", "contracts.proposal")
            ]

        """Store important messages for replay on reconnect.
        
        Uses supersede logic: brain.complete removes buffered brain.started
        for the same source, preventing stale "WORKING" state on reconnect.
        """
        # A contract verdict resolves pending state. Remove its proposal from
        # replay so a newly opened tab cannot resurrect an approved card.
        if event in ("contracts.approved", "contracts.rejected"):
            payload = data.get("payload") or {}
            design_id, plan_id = payload.get("design_id"), payload.get("plan_id")
            self._replay_buffer = [
                (ts, buffered) for ts, buffered in self._replay_buffer
                if not (
                    (buffered.get("payload") or {}).get("event") == "contracts.proposal"
                    and (not design_id or (buffered.get("payload") or {}).get("design_id") == design_id)
                    and (not plan_id or (buffered.get("payload") or {}).get("plan_id") == plan_id)
                )
            ]
            return

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
