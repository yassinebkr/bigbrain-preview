"""Tests for WebAdapter — Morphable UI adapter."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType, Priority
from bigbrain.web.adapter import WebAdapter
from bigbrain.web.server import WebServer


# ================================================================
# FIXTURES
# ================================================================


@pytest.fixture
def bus():
    """Create a MessageBus without auth for testing."""
    return MessageBus(auth=None)


@pytest.fixture
def mock_server(bus):
    """Create a mock WebServer."""
    server = MagicMock(spec=WebServer)
    server.client_count = 0
    return server


@pytest.fixture
def adapter(bus, mock_server):
    """Create a WebAdapter."""
    return WebAdapter(bus=bus, web_server=mock_server, workspace="test")


# ================================================================
# LIFECYCLE
# ================================================================


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self, adapter):
        assert not adapter.is_running()
        await adapter.start()
        assert adapter.is_running()
        await adapter.stop()
        assert not adapter.is_running()

    @pytest.mark.asyncio
    async def test_double_start(self, adapter):
        await adapter.start()
        await adapter.start()  # Should not error
        assert adapter.is_running()
        await adapter.stop()


# ================================================================
# MESSAGE RENDERING
# ================================================================


class TestMessageRendering:
    @pytest.mark.asyncio
    async def test_render_message_emits_event(self, adapter, bus):
        """render_message should send a bus event."""
        await adapter.start()
        received = []
        bus.subscribe("morphable_ui", lambda msg: received.append(msg))

        await adapter.render_message("Hello world", "info")
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].payload["event"] == "chat.message"
        assert received[0].payload["text"] == "Hello world"
        assert received[0].payload["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_render_error_message(self, adapter, bus):
        await adapter.start()
        received = []
        bus.subscribe("morphable_ui", lambda msg: received.append(msg))

        await adapter.render_message("Oops", "error")
        await asyncio.sleep(0.05)

        assert received[0].payload["role"] == "system"

    @pytest.mark.asyncio
    async def test_render_progress(self, adapter, bus):
        await adapter.start()
        received = []
        bus.subscribe("morphable_ui", lambda msg: received.append(msg))

        await adapter.render_progress("my_task", progress=0.5, status="running")
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].payload["event"] == "task.progress"
        assert received[0].payload["progress"] == 0.5

    @pytest.mark.asyncio
    async def test_render_brain_status(self, adapter, bus):
        await adapter.start()
        received = []
        # Brain status uses STATE type, broadcast to *
        bus.subscribe("*", lambda msg: received.append(msg))

        await adapter.render_brain_status("python_brain", {"running": True})
        await asyncio.sleep(0.05)

        state_msgs = [m for m in received if m.payload.get("event") == "brain.status"]
        assert len(state_msgs) == 1
        assert state_msgs[0].payload["brain"] == "python_brain"
        assert state_msgs[0].payload["state"] == "idle"
        assert state_msgs[0].type == "state"

    @pytest.mark.asyncio
    async def test_show_error(self, adapter, bus):
        await adapter.start()
        received = []
        bus.subscribe("morphable_ui", lambda msg: received.append(msg))

        await adapter.show_error("Something broke", "Stack trace here")
        await asyncio.sleep(0.05)

        assert "Something broke" in received[0].payload["text"]
        assert "Stack trace" in received[0].payload["text"]


# ================================================================
# WORKSPACE CONTROL
# ================================================================


class TestWorkspaceControl:
    @pytest.mark.asyncio
    async def test_switch_workspace(self, adapter, bus):
        await adapter.start()
        received = []
        bus.subscribe("morphable_ui", lambda msg: received.append(msg))

        await adapter.switch_workspace("python-dev")
        await asyncio.sleep(0.05)

        assert adapter.workspace == "python-dev"
        ws_msgs = [m for m in received if m.payload.get("event") == "ui.workspace"]
        assert len(ws_msgs) == 1
        assert ws_msgs[0].payload["workspace"] == "python-dev"

    @pytest.mark.asyncio
    async def test_show_panel(self, adapter, bus):
        await adapter.start()
        received = []
        bus.subscribe("morphable_ui", lambda msg: received.append(msg))

        await adapter.show_panel("side-top", "repl", {"title": "Python REPL"})
        await asyncio.sleep(0.05)

        msgs = [m for m in received if m.payload.get("event") == "ui.panel.show"]
        assert len(msgs) == 1
        assert msgs[0].payload["slot"] == "side-top"
        assert msgs[0].payload["type"] == "repl"

    @pytest.mark.asyncio
    async def test_hide_panel(self, adapter, bus):
        await adapter.start()
        received = []
        bus.subscribe("morphable_ui", lambda msg: received.append(msg))

        await adapter.hide_panel("side-bottom")
        await asyncio.sleep(0.05)

        msgs = [m for m in received if m.payload.get("event") == "ui.panel.hide"]
        assert len(msgs) == 1
        assert msgs[0].payload["slot"] == "side-bottom"

    @pytest.mark.asyncio
    async def test_highlight_panel(self, adapter, bus):
        await adapter.start()
        received = []
        bus.subscribe("morphable_ui", lambda msg: received.append(msg))

        await adapter.highlight_panel("my-panel", "#ff0000")
        await asyncio.sleep(0.05)

        msgs = [m for m in received if m.payload.get("event") == "ui.highlight"]
        assert len(msgs) == 1
        assert msgs[0].payload["panel"] == "my-panel"
        assert msgs[0].payload["color"] == "#ff0000"


# ================================================================
# PIPELINE CONTROL
# ================================================================


class TestPipelineControl:
    @pytest.mark.asyncio
    async def test_create_pipeline(self, adapter, bus):
        await adapter.start()
        received = []
        bus.subscribe("morphable_ui", lambda msg: received.append(msg))

        await adapter.create_pipeline(
            "weather-1",
            {
                "source": {"type": "http-poll", "url": "https://api.weather.com/v1"},
                "transform": {"fields": {"temp": "data.temp", "city": "data.city"}},
                "title": "Weather",
            },
            "side-top",
        )
        await asyncio.sleep(0.05)

        msgs = [m for m in received if m.payload.get("event") == "ui.pipeline.create"]
        assert len(msgs) == 1
        assert msgs[0].payload["id"] == "weather-1"
        assert msgs[0].payload["slot"] == "side-top"

    @pytest.mark.asyncio
    async def test_destroy_pipeline(self, adapter, bus):
        await adapter.start()
        received = []
        bus.subscribe("morphable_ui", lambda msg: received.append(msg))

        await adapter.destroy_pipeline("weather-1")
        await asyncio.sleep(0.05)

        msgs = [m for m in received if m.payload.get("event") == "ui.pipeline.destroy"]
        assert len(msgs) == 1
        assert msgs[0].payload["id"] == "weather-1"


# ================================================================
# FOCUS CONTROL
# ================================================================


class TestFocusControl:
    @pytest.mark.asyncio
    async def test_set_focus_mode(self, adapter, bus):
        await adapter.start()
        received = []
        # Focus uses STATE type, broadcast
        bus.subscribe("*", lambda msg: received.append(msg))

        await adapter.set_focus_mode("deep_focus", "python-dev")
        await asyncio.sleep(0.05)

        focus_msgs = [m for m in received if m.payload.get("event") == "focus.mode_changed"]
        assert len(focus_msgs) == 1
        assert focus_msgs[0].payload["mode"] == "deep_focus"
        assert focus_msgs[0].type == "state"
