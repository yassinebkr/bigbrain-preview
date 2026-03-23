"""Tests for BusParticipant base class and inheritance."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType, Priority
from bigbrain.bus.participant import BusParticipant
from bigbrain.brains.base import BaseBrain
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator


class TestBusParticipant:
    """Test BusParticipant lifecycle."""

    @pytest.fixture
    def mock_bus(self):
        bus = Mock()
        bus.subscribe = Mock()
        bus.unsubscribe = Mock()
        return bus

    @pytest.mark.asyncio
    async def test_init(self, mock_bus):
        """Participant stores name, bus, and starts not running."""
        p = BusParticipant("comp1", mock_bus)
        assert p.name == "comp1"
        assert p.bus is mock_bus
        assert p._running is False

    @pytest.mark.asyncio
    async def test_start(self, mock_bus):
        """Start subscribes to bus and sets running flag."""
        p = BusParticipant("comp1", mock_bus)
        await p.start()

        assert p._running is True
        mock_bus.subscribe.assert_called_once_with("comp1", p._on_message)

    @pytest.mark.asyncio
    async def test_start_idempotent(self, mock_bus):
        """Starting twice doesn't double-subscribe."""
        p = BusParticipant("comp1", mock_bus)
        await p.start()
        await p.start()

        assert mock_bus.subscribe.call_count == 1

    @pytest.mark.asyncio
    async def test_stop(self, mock_bus):
        """Stop unsubscribes from bus and clears running flag."""
        p = BusParticipant("comp1", mock_bus)
        await p.start()
        await p.stop()

        assert p._running is False
        mock_bus.unsubscribe.assert_called_once_with("comp1", p._on_message)

    @pytest.mark.asyncio
    async def test_on_message_default_noop(self, mock_bus):
        """Default _on_message does nothing."""
        p = BusParticipant("comp1", mock_bus)
        msg = BusMessage(type=MessageType.EVENT, source="x", target="comp1")
        await p._on_message(msg)  # should not raise

    @pytest.mark.asyncio
    async def test_custom_on_message(self, mock_bus):
        """Subclass can override _on_message."""
        received = []

        class MyParticipant(BusParticipant):
            async def _on_message(self, msg: BusMessage) -> None:
                received.append(msg)

        p = MyParticipant("comp1", mock_bus)
        msg = BusMessage(type=MessageType.EVENT, source="x", target="comp1")
        await p._on_message(msg)

        assert len(received) == 1
        assert received[0] is msg


class TestBaseBrainInheritsBusParticipant:
    """Verify BaseBrain inherits from BusParticipant."""

    def test_isinstance(self):
        """BaseBrain instances are BusParticipant."""
        class ConcreteBrain(BaseBrain):
            async def handle_task(self, message):
                return {}

        bus = Mock()
        bus.subscribe = Mock()
        bus.unsubscribe = Mock()
        bus.send = AsyncMock()
        bus.send_result = AsyncMock()
        bus.broadcast_event = AsyncMock()

        brain = ConcreteBrain("test", bus)
        assert isinstance(brain, BusParticipant)

    def test_mro(self):
        """BusParticipant is in BaseBrain's MRO."""
        assert BusParticipant in BaseBrain.__mro__

    @pytest.mark.asyncio
    async def test_brain_start_subscribes(self):
        """Brain.start() subscribes to bus (inherited plumbing)."""
        class ConcreteBrain(BaseBrain):
            async def handle_task(self, message):
                return {}

        bus = Mock()
        bus.subscribe = Mock()
        bus.unsubscribe = Mock()
        bus.send = AsyncMock()
        bus.send_result = AsyncMock()
        bus.broadcast_event = AsyncMock()

        brain = ConcreteBrain("mybrain", bus)
        await brain.start()

        bus.subscribe.assert_called_once_with("mybrain", brain._message_handler)
        assert brain._running is True

        await brain.stop()
        bus.unsubscribe.assert_called_with("mybrain", brain._message_handler)
        assert brain._running is False

    @pytest.mark.asyncio
    async def test_brain_double_start_raises(self):
        """Brain raises on double-start (brain-specific behavior kept)."""
        class ConcreteBrain(BaseBrain):
            async def handle_task(self, message):
                return {}

        bus = Mock()
        bus.subscribe = Mock()
        bus.unsubscribe = Mock()
        bus.send = AsyncMock()
        bus.send_result = AsyncMock()
        bus.broadcast_event = AsyncMock()

        brain = ConcreteBrain("mybrain", bus)
        await brain.start()

        with pytest.raises(RuntimeError, match="already running"):
            await brain.start()

        await brain.stop()


class TestOrchestratorInheritsBusParticipant:
    """Verify WorkspaceOrchestrator inherits from BusParticipant."""

    def test_isinstance(self):
        """WorkspaceOrchestrator instances are BusParticipant."""
        bus = Mock()
        bus.subscribe = Mock()
        bus.unsubscribe = Mock()
        bus.send = AsyncMock()
        bus.send_result = AsyncMock()
        bus.broadcast_event = AsyncMock()

        orch = WorkspaceOrchestrator("ws", bus)
        assert isinstance(orch, BusParticipant)

    def test_mro(self):
        """BusParticipant is in WorkspaceOrchestrator's MRO."""
        assert BusParticipant in WorkspaceOrchestrator.__mro__

    @pytest.mark.asyncio
    async def test_orchestrator_start_subscribes(self):
        """Orchestrator.start() subscribes to bus (inherited plumbing)."""
        bus = Mock()
        bus.subscribe = Mock()
        bus.unsubscribe = Mock()
        bus.send = AsyncMock()
        bus.send_result = AsyncMock()
        bus.broadcast_event = AsyncMock()

        orch = WorkspaceOrchestrator("test_ws", bus)
        await orch.start()

        bus.subscribe.assert_called_once_with("orchestrator_test_ws", orch.handle_message)
        assert orch._running is True

        await orch.stop()
        bus.unsubscribe.assert_called_with("orchestrator_test_ws", orch.handle_message)
        assert orch._running is False

    @pytest.mark.asyncio
    async def test_orchestrator_double_start_raises(self):
        """Orchestrator raises on double-start."""
        bus = Mock()
        bus.subscribe = Mock()
        bus.unsubscribe = Mock()
        bus.send = AsyncMock()
        bus.send_result = AsyncMock()
        bus.broadcast_event = AsyncMock()

        orch = WorkspaceOrchestrator("test_ws", bus)
        await orch.start()

        with pytest.raises(RuntimeError, match="already running"):
            await orch.start()

        await orch.stop()

    @pytest.mark.asyncio
    async def test_orchestrator_name_derived(self):
        """Orchestrator name is derived from workspace via super().__init__."""
        bus = Mock()
        bus.subscribe = Mock()
        orch = WorkspaceOrchestrator("myws", bus)
        assert orch.name == "orchestrator_myws"


class TestBusParticipantWithRealBus:
    """Integration: BusParticipant with a real MessageBus."""

    @pytest.fixture
    def temp_log_dir(self):
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    async def bus(self, temp_log_dir):
        bus = MessageBus(log_dir=temp_log_dir)
        yield bus
        await bus.close()

    @pytest.mark.asyncio
    async def test_participant_receives_messages(self, bus):
        """BusParticipant subclass receives messages through bus."""
        received = []

        class Echo(BusParticipant):
            async def _on_message(self, msg: BusMessage) -> None:
                received.append(msg)

        echo = Echo("echo_target", bus)
        await echo.start()

        msg = BusMessage(
            type=MessageType.EVENT,
            source="sender",
            target="echo_target",
            payload={"hello": "world"},
        )
        await bus.send(msg)
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].payload == {"hello": "world"}

        await echo.stop()

        # After stop, no more messages
        msg2 = BusMessage(type=MessageType.EVENT, source="sender", target="echo_target")
        await bus.send(msg2)
        await asyncio.sleep(0.05)

        assert len(received) == 1  # still 1
