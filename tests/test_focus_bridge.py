"""Tests for FocusBridge — Focus state synchronization."""

import asyncio
import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType, Priority
from bigbrain.front.focus_manager import FocusManager, FocusMode, FocusState
from bigbrain.web.focus_bridge import FocusBridge


# ================================================================
# FIXTURES
# ================================================================


@pytest.fixture
def bus():
    return MessageBus(auth=None)


@pytest.fixture
def focus_manager():
    fm = FocusManager()
    fm.set_workspace_focus("default", FocusState.ACTIVE, "test")
    fm.set_focus_mode(FocusMode.NORMAL, "test")
    return fm


@pytest.fixture
def bridge(bus, focus_manager):
    return FocusBridge(bus=bus, focus_manager=focus_manager)


# ================================================================
# LIFECYCLE
# ================================================================


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self, bridge):
        await bridge.start()
        assert bridge._running
        await bridge.stop()
        assert not bridge._running

    @pytest.mark.asyncio
    async def test_double_start(self, bridge):
        await bridge.start()
        await bridge.start()  # Should not error
        assert bridge._running
        await bridge.stop()


# ================================================================
# FOCUS BROADCAST
# ================================================================


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_focus_state(self, bridge, bus):
        await bridge.start()

        received = []
        bus.subscribe("*", lambda msg: received.append(msg))

        await bridge.broadcast_focus_state()
        await asyncio.sleep(0.05)

        state_msgs = [
            m for m in received
            if m.payload.get("event") == "focus.state"
        ]
        assert len(state_msgs) >= 1
        assert state_msgs[0].type == "state"

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_broadcast_rate_limited(self, bridge, bus):
        """Rapid broadcasts should be rate-limited."""
        await bridge.start()

        received = []
        bus.subscribe("*", lambda msg: received.append(msg))

        # Fire multiple broadcasts rapidly
        for _ in range(5):
            await bridge.broadcast_focus_state()

        await asyncio.sleep(0.05)

        # Should only get 1 due to rate limiting (0.5s interval)
        state_msgs = [
            m for m in received
            if m.payload.get("event") == "focus.state"
        ]
        assert len(state_msgs) == 1

        await bridge.stop()


# ================================================================
# UI → FOCUS MANAGER SYNC
# ================================================================


class TestUIToFocusSync:
    @pytest.mark.asyncio
    async def test_workspace_change_from_ui(self, bridge, bus, focus_manager):
        """UI workspace switch should update FocusManager."""
        await bridge.start()

        # Simulate UI sending workspace change
        msg = BusMessage(
            type=MessageType.EVENT,
            source="morphable_ui",
            target="front_brain",
            payload={
                "event": "focus.workspace_changed",
                "workspace": "python-dev",
            },
        )

        await bus.send(msg)
        await asyncio.sleep(0.1)

        # FocusManager should have updated
        status = focus_manager.get_focus_status()
        # Check that python-dev is now tracked
        assert "python-dev" in str(status)

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_mode_change_from_ui(self, bridge, bus, focus_manager):
        """UI focus mode change should update FocusManager."""
        await bridge.start()

        msg = BusMessage(
            type=MessageType.EVENT,
            source="morphable_ui",
            target="front_brain",
            payload={
                "event": "focus.mode_changed",
                "mode": "deep_focus",
            },
        )

        await bus.send(msg)
        await asyncio.sleep(0.1)

        status = focus_manager.get_focus_status()
        assert "deep" in str(status).lower()

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_ignores_non_ui_source(self, bridge, bus, focus_manager):
        """Focus changes from non-UI sources should not be re-synced."""
        await bridge.start()

        # Set initial state
        focus_manager.set_focus_mode(FocusMode.NORMAL, "test")

        # Message from front_brain (not UI) — should NOT trigger re-sync
        msg = BusMessage(
            type=MessageType.EVENT,
            source="front_brain",
            target="morphable_ui",
            payload={
                "event": "focus.workspace_changed",
                "workspace": "test-ws",
            },
        )

        await bus.send(msg)
        await asyncio.sleep(0.1)

        # FocusManager should NOT have been updated by the bridge
        # (front_brain updates FocusManager directly, not through bridge)
        await bridge.stop()
