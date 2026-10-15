"""Tests for WebServer — HTTP + WebSocket bridge."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType, Priority
from bigbrain.web.server import WebServer


# ================================================================
# FIXTURES
# ================================================================


@pytest.fixture
def bus():
    """Create a MessageBus without auth for testing."""
    return MessageBus(auth=None)


@pytest.fixture
def server(bus):
    """Create a WebServer (not started)."""
    return WebServer(bus=bus, host="127.0.0.1", port=0)


# ================================================================
# INITIALIZATION
# ================================================================


class TestInit:
    def test_create_server(self, bus):
        srv = WebServer(bus=bus, host="0.0.0.0", port=8080)
        assert srv.bus is bus
        assert srv.host == "0.0.0.0"
        assert srv.port == 8080
        assert srv.client_count == 0

    def test_default_urls(self, server):
        assert "127.0.0.1" in server.url
        assert "ws://" in server.ws_url

    def test_focus_manager_optional(self, bus):
        srv = WebServer(bus=bus)
        assert srv.focus_manager is None


# ================================================================
# BUS MESSAGE FORWARDING
# ================================================================


class TestBusForwarding:
    @pytest.mark.asyncio
    async def test_on_bus_message_no_clients(self, server):
        """Should not error when no clients connected."""
        msg = BusMessage(
            type=MessageType.EVENT,
            source="test",
            target="*",
            payload={"event": "test.event"},
        )
        # Should not raise
        await server._on_bus_message(msg)

    @pytest.mark.asyncio
    async def test_on_bus_message_with_client(self, server):
        """Should forward message to connected client."""
        mock_ws = AsyncMock()
        mock_ws.send_json = AsyncMock()
        server._ws_clients.add(mock_ws)

        msg = BusMessage(
            type=MessageType.EVENT,
            source="test_brain",
            target="*",
            payload={"event": "brain.complete"},
        )

        await server._on_bus_message(msg)

        mock_ws.send_json.assert_called_once()
        sent_data = mock_ws.send_json.call_args[0][0]
        assert sent_data["source"] == "test_brain"
        assert sent_data["payload"]["event"] == "brain.complete"

    @pytest.mark.asyncio
    async def test_on_bus_message_cleans_closed(self, server):
        """Should clean up clients that raise ConnectionResetError."""
        bad_ws = AsyncMock()
        bad_ws.send_json = AsyncMock(side_effect=ConnectionResetError)
        good_ws = AsyncMock()
        good_ws.send_json = AsyncMock()

        server._ws_clients.add(bad_ws)
        server._ws_clients.add(good_ws)

        msg = BusMessage(
            type=MessageType.EVENT,
            source="test",
            target="*",
            payload={},
        )

        await server._on_bus_message(msg)

        # Bad client should be removed
        assert bad_ws not in server._ws_clients
        # Good client should remain
        assert good_ws in server._ws_clients

    @pytest.mark.asyncio
    async def test_multiple_clients_receive(self, server):
        """All connected clients should receive the message."""
        clients = []
        for _ in range(3):
            ws = AsyncMock()
            ws.send_json = AsyncMock()
            server._ws_clients.add(ws)
            clients.append(ws)

        msg = BusMessage(
            type=MessageType.TASK,
            source="orchestrator",
            target="python_brain",
            payload={"type": "execute_code"},
        )

        await server._on_bus_message(msg)

        for ws in clients:
            ws.send_json.assert_called_once()


# ================================================================
# WEBSOCKET MESSAGE HANDLING
# ================================================================


class TestWsMessageHandling:
    @pytest.mark.asyncio
    async def test_handle_ws_message_sends_to_bus(self, server, bus):
        """Messages from WS client should be forwarded to bus."""
        received = []
        bus.subscribe("front_brain", lambda msg: received.append(msg))

        mock_ws = AsyncMock()

        raw = json.dumps({
            "type": "task",
            "source": "should_be_overridden",
            "target": "front_brain",
            "payload": {"type": "user_message", "text": "hello"},
        })

        await server._handle_ws_message(mock_ws, raw)
        await asyncio.sleep(0.05)

        assert len(received) == 1
        # Source should be forced to morphable_ui (security)
        assert received[0].source == "morphable_ui"
        assert received[0].target == "front_brain"
        assert received[0].payload["text"] == "hello"

    @pytest.mark.asyncio
    async def test_handle_ws_invalid_json(self, server):
        """Invalid JSON should be ignored, not crash."""
        mock_ws = AsyncMock()
        await server._handle_ws_message(mock_ws, "not json{{{")
        # Should not raise

    @pytest.mark.asyncio
    async def test_handle_ws_source_forced(self, server, bus):
        """Source is always forced to morphable_ui to prevent spoofing."""
        received = []
        bus.subscribe("*", lambda msg: received.append(msg))

        mock_ws = AsyncMock()
        raw = json.dumps({
            "type": "event",
            "source": "admin",  # Attempted spoof
            "target": "*",
            "payload": {"event": "evil.command"},
        })

        await server._handle_ws_message(mock_ws, raw)
        await asyncio.sleep(0.05)

        # Source should be morphable_ui, not "admin"
        assert all(m.source == "morphable_ui" for m in received)


# ================================================================
# INITIAL STATE
# ================================================================


class TestInitialState:
    @pytest.mark.asyncio
    async def test_send_initial_state(self, server):
        """New clients should receive focus + status."""
        mock_ws = AsyncMock()
        mock_ws.send_json = AsyncMock()

        await server._send_initial_state(mock_ws)

        # Should send at least 2 messages: focus + status
        assert mock_ws.send_json.call_count == 2

        # First message should be focus state
        first = mock_ws.send_json.call_args_list[0][0][0]
        assert first["payload"]["event"] == "focus.initial"

        # Second should be system status
        second = mock_ws.send_json.call_args_list[1][0][0]
        assert second["payload"]["event"] == "system.status"

    @pytest.mark.asyncio
    async def test_send_initial_state_with_focus_manager(self, bus):
        """Focus state should include manager data if available."""
        from bigbrain.front.focus_manager import FocusManager

        fm = FocusManager()
        srv = WebServer(bus=bus, focus_manager=fm)

        mock_ws = AsyncMock()
        mock_ws.send_json = AsyncMock()

        await srv._send_initial_state(mock_ws)

        first = mock_ws.send_json.call_args_list[0][0][0]
        assert "mode" in first["payload"] or "workspaces" in first["payload"]


# ================================================================
# FOCUS ENDPOINT
# ================================================================


class TestFocusEndpoint:
    def test_get_focus_no_manager(self, server):
        """Without FocusManager, should return defaults."""
        result = server._get_focus_snapshot()
        assert result["workspaces"] == {}
        assert result["mode"] == "normal"

    def test_get_focus_with_manager(self, bus):
        from bigbrain.front.focus_manager import FocusManager, FocusMode

        fm = FocusManager()
        fm.set_focus_mode(FocusMode.DEEP_FOCUS, "test")
        srv = WebServer(bus=bus, focus_manager=fm)

        result = srv._get_focus_snapshot()
        assert "focus_mode" in result or "mode" in result


# ================================================================
# CLIENT COUNT
# ================================================================


class TestClientCount:
    def test_empty(self, server):
        assert server.client_count == 0

    def test_with_clients(self, server):
        server._ws_clients.add(MagicMock())
        server._ws_clients.add(MagicMock())
        assert server.client_count == 2


# ================================================================
# APLOT ADAPTER PROTOCOL (étape 2 — docs/WEBUI-APLOT-PORT.md)
# ================================================================


class TestAplotProtocol:
    """Control frames answered by the server without reaching the bus."""

    @pytest.mark.asyncio
    async def test_ping_gets_pong(self, server, bus):
        sent_to_bus = []
        bus.subscribe("*", lambda msg: sent_to_bus.append(msg))
        mock_ws = AsyncMock()

        await server._handle_ws_message(
            mock_ws, json.dumps({"type": "ping"})
        )
        await asyncio.sleep(0.05)

        frames = [c.args[0] for c in mock_ws.send_json.call_args_list]
        assert any(f["type"] == "pong" for f in frames)
        assert sent_to_bus == []  # control frames never reach the bus

    @pytest.mark.asyncio
    async def test_chat_send_routes_to_front_brain_with_acks(self, server, bus):
        received = []
        bus.subscribe("front_brain", lambda msg: received.append(msg))
        mock_ws = AsyncMock()

        raw = json.dumps({
            "type": "chat.send",
            "payload": {"text": "hello bigbrain", "messageId": "m1"},
        })
        await server._handle_ws_message(mock_ws, raw)
        await asyncio.sleep(0.05)

        # Exactly one bus task to front_brain with the legacy user_message shape.
        assert len(received) == 1
        assert received[0].source == "morphable_ui"
        assert received[0].payload == {"type": "user_message", "text": "hello bigbrain"}

        # Acks: queued then sent, in order.
        statuses = [
            c.args[0]["payload"]["status"]
            for c in mock_ws.send_json.call_args_list
            if c.args[0].get("type") == "message.status"
        ]
        assert statuses == ["queued", "sent"]
        assert all(
            c.args[0]["payload"]["messageId"] == "m1"
            for c in mock_ws.send_json.call_args_list
            if c.args[0].get("type") == "message.status"
        )

    @pytest.mark.asyncio
    async def test_chat_send_empty_text_is_ignored(self, server, bus):
        sent_to_bus = []
        bus.subscribe("*", lambda msg: sent_to_bus.append(msg))
        mock_ws = AsyncMock()

        await server._handle_ws_message(
            mock_ws, json.dumps({"type": "chat.send", "payload": {"text": "   "}})
        )
        await asyncio.sleep(0.05)
        assert sent_to_bus == []

    @pytest.mark.asyncio
    async def test_chat_history_request_response(self, server):
        server._append_chat_history("user", "hi")
        server._append_chat_history("assistant", "hello")
        mock_ws = AsyncMock()

        await server._handle_ws_message(
            mock_ws, json.dumps({"type": "req", "id": "r1", "method": "chat.history"})
        )

        frames = [c.args[0] for c in mock_ws.send_json.call_args_list]
        resp = next(f for f in frames if f.get("type") == "resp")
        assert resp["id"] == "r1"
        texts = [m["text"] for m in resp["payload"]["messages"]]
        assert texts == ["hi", "hello"]

    @pytest.mark.asyncio
    async def test_unknown_request_errors(self, server):
        mock_ws = AsyncMock()
        await server._handle_ws_message(
            mock_ws, json.dumps({"type": "req", "id": "r2", "method": "nope"})
        )
        frames = [c.args[0] for c in mock_ws.send_json.call_args_list]
        resp = next(f for f in frames if f.get("type") == "resp")
        assert "unknown method" in resp["error"]

    @pytest.mark.asyncio
    async def test_chat_message_event_captured_in_history(self, server):
        msg = BusMessage(
            type=MessageType.EVENT,
            source="front_brain",
            target="morphable_ui",
            payload={"event": "chat.message", "role": "assistant", "text": "bonjour"},
        )
        await server._on_bus_message(msg)
        assert server._chat_history[-1]["role"] == "assistant"
        assert server._chat_history[-1]["text"] == "bonjour"

    def test_chat_history_bounded(self, server):
        for i in range(250):
            server._append_chat_history("user", f"m{i}")
        assert len(server._chat_history) == 200
        assert server._chat_history[0]["text"] == "m50"


# ================================================================
# WORKSPACE FS API (replaces the UI mock file tree)
# ================================================================


class TestWorkspaceFs:
    @pytest.fixture(autouse=True)
    def _ws_root(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path / "ws"))
        yield tmp_path / "ws"

    def _mk(self, root, rel, content="x"):
        root.mkdir(parents=True, exist_ok=True)
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(content)
        return root / rel

    def test_list_root_and_entries(self, _ws_root):
        from bigbrain.web import fs_api
        self._mk(_ws_root, "notes.md", "hello")
        _ws_root.joinpath("sub").mkdir(parents=True)
        result = fs_api.list_dir("")
        names = {e["name"]: e["type"] for e in result["entries"]}
        assert names == {"notes.md": "file", "sub": "folder"}

    def test_write_read_roundtrip(self, _ws_root):
        from bigbrain.web import fs_api
        fs_api.write_file("docs/readme.txt", "line1\nline2")
        data = fs_api.read_file("docs/readme.txt")
        assert data["content"] == "line1\nline2"
        assert data["binary"] is False

    def test_rename_and_move(self, _ws_root):
        from bigbrain.web import fs_api
        self._mk(_ws_root, "a/old.txt", "v")
        fs_api.mkdir("b")
        fs_api.rename("a/old.txt", "new.txt")
        fs_api.move("a/new.txt", "b")
        data = fs_api.read_file("b/new.txt")
        assert data["content"] == "v"

    def test_delete_file_and_folder(self, _ws_root):
        from bigbrain.web import fs_api
        self._mk(_ws_root, "dir/f.txt", "v")
        fs_api.delete("dir/f.txt")
        fs_api.delete("dir")
        listing = fs_api.list_dir("")
        assert listing["entries"] == []

    def test_path_traversal_refused(self, _ws_root):
        from aiohttp import web as aioweb
        from bigbrain.web import fs_api
        with pytest.raises(aioweb.HTTPBadRequest):
            fs_api.read_file("../secret.txt")
        with pytest.raises(aioweb.HTTPBadRequest):
            fs_api.write_file("../../outside.txt", "nope")
        with pytest.raises(aioweb.HTTPBadRequest):
            fs_api.delete("../..")

    def test_delete_root_refused(self, _ws_root):
        from aiohttp import web as aioweb
        from bigbrain.web import fs_api
        with pytest.raises(aioweb.HTTPBadRequest):
            fs_api.delete("")
        with pytest.raises(aioweb.HTTPBadRequest):
            fs_api.delete(".")

    def test_rename_refuses_slash_and_collision(self, _ws_root):
        from aiohttp import web as aioweb
        from bigbrain.web import fs_api
        self._mk(_ws_root, "one.txt", "a")
        self._mk(_ws_root, "two.txt", "b")
        with pytest.raises(aioweb.HTTPBadRequest):
            fs_api.rename("one.txt", "sub/name.txt")
        with pytest.raises(aioweb.HTTPBadRequest):
            fs_api.rename("one.txt", "two.txt")
