"""Tests for BigBrain bus HMAC-SHA256 authentication."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from bigbrain.bus.auth import BusAuth
from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType, Priority


class TestBusAuth:
    """Test BusAuth token management and signing."""

    def test_generate_token(self):
        """Test generating a token for a brain."""
        auth = BusAuth()
        token = auth.generate_token("brain_a")

        assert isinstance(token, str)
        assert len(token) == 64  # 32 bytes -> 64 hex chars
        assert auth.get_token("brain_a") == token

    def test_generate_token_unique(self):
        """Tokens for different brains should be different."""
        auth = BusAuth()
        t1 = auth.generate_token("brain_a")
        t2 = auth.generate_token("brain_b")
        assert t1 != t2

    def test_token_rotation(self):
        """Regenerating a token replaces the old one."""
        auth = BusAuth()
        old = auth.generate_token("brain_a")
        new = auth.generate_token("brain_a")  # rotate

        assert old != new
        assert auth.get_token("brain_a") == new

    def test_revoke_token(self):
        """Revoking a token removes it from the registry."""
        auth = BusAuth()
        auth.generate_token("brain_a")
        auth.revoke_token("brain_a")

        assert auth.get_token("brain_a") is None

    def test_revoke_nonexistent_token(self):
        """Revoking a non-existent token is a no-op."""
        auth = BusAuth()
        auth.revoke_token("ghost")  # should not raise

    def test_get_token_missing(self):
        """Getting token for unregistered brain returns None."""
        auth = BusAuth()
        assert auth.get_token("unknown") is None

    def test_sign_message(self):
        """Test signing a message produces a hex digest."""
        auth = BusAuth()
        token = auth.generate_token("brain_a")

        msg = BusMessage(
            type=MessageType.EVENT,
            source="brain_a",
            target="*",
            payload={"key": "value"},
        )

        sig = auth.sign_message(token, msg)
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA-256 hex digest

    def test_sign_message_deterministic(self):
        """Same token + same message → same signature."""
        auth = BusAuth()
        token = auth.generate_token("brain_a")

        msg = BusMessage(
            id="fixed-id",
            type=MessageType.EVENT,
            source="brain_a",
            target="*",
            payload={"k": 1},
        )

        sig1 = auth.sign_message(token, msg)
        sig2 = auth.sign_message(token, msg)
        assert sig1 == sig2

    def test_sign_message_differs_for_different_payloads(self):
        """Different payloads → different signatures."""
        auth = BusAuth()
        token = auth.generate_token("brain_a")

        base = dict(id="same-id", type=MessageType.EVENT, source="brain_a", target="*")
        msg1 = BusMessage(**base, payload={"a": 1})
        msg2 = BusMessage(**base, payload={"a": 2})

        assert auth.sign_message(token, msg1) != auth.sign_message(token, msg2)

    def test_sign_message_differs_for_different_ids(self):
        """Different message IDs → different signatures."""
        auth = BusAuth()
        token = auth.generate_token("brain_a")

        msg1 = BusMessage(id="id-1", type=MessageType.EVENT, source="brain_a", target="*", payload={})
        msg2 = BusMessage(id="id-2", type=MessageType.EVENT, source="brain_a", target="*", payload={})

        assert auth.sign_message(token, msg1) != auth.sign_message(token, msg2)

    def test_verify_message_valid(self):
        """Verify returns True for correctly signed messages."""
        auth = BusAuth()
        token = auth.generate_token("brain_a")

        msg = BusMessage(
            type=MessageType.TASK,
            source="brain_a",
            target="orchestrator",
            payload={"action": "do_stuff"},
        )
        sig = auth.sign_message(token, msg)

        assert auth.verify_message("brain_a", msg, sig) is True

    def test_verify_message_invalid_signature(self):
        """Verify returns False for tampered signature."""
        auth = BusAuth()
        auth.generate_token("brain_a")

        msg = BusMessage(
            type=MessageType.TASK,
            source="brain_a",
            target="orchestrator",
            payload={"action": "do_stuff"},
        )

        assert auth.verify_message("brain_a", msg, "0" * 64) is False

    def test_verify_message_unknown_brain(self):
        """Verify returns False for unregistered brain."""
        auth = BusAuth()

        msg = BusMessage(
            type=MessageType.TASK,
            source="ghost",
            target="orchestrator",
            payload={},
        )

        assert auth.verify_message("ghost", msg, "abc123") is False

    def test_verify_message_after_rotation(self):
        """Old signature fails after token rotation."""
        auth = BusAuth()
        old_token = auth.generate_token("brain_a")

        msg = BusMessage(
            type=MessageType.EVENT,
            source="brain_a",
            target="*",
            payload={"data": "original"},
        )
        old_sig = auth.sign_message(old_token, msg)

        # Rotate token
        auth.generate_token("brain_a")

        # Old signature should now be invalid
        assert auth.verify_message("brain_a", msg, old_sig) is False

    def test_verify_message_after_rotation_new_sig(self):
        """New signature works after token rotation."""
        auth = BusAuth()
        auth.generate_token("brain_a")

        msg = BusMessage(
            type=MessageType.EVENT,
            source="brain_a",
            target="*",
            payload={"data": "rotated"},
        )

        # Rotate
        new_token = auth.generate_token("brain_a")
        new_sig = auth.sign_message(new_token, msg)

        assert auth.verify_message("brain_a", msg, new_sig) is True

    def test_verify_message_tampered_payload(self):
        """Signature is invalid if payload was tampered with."""
        auth = BusAuth()
        token = auth.generate_token("brain_a")

        msg = BusMessage(
            id="fixed",
            type=MessageType.TASK,
            source="brain_a",
            target="orch",
            payload={"amount": 100},
        )
        sig = auth.sign_message(token, msg)

        # Tamper
        msg.payload = {"amount": 999}
        assert auth.verify_message("brain_a", msg, sig) is False


class TestMessageBusWithAuth:
    """Test MessageBus authentication integration."""

    @pytest.fixture
    def temp_log_dir(self):
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    async def auth_bus(self, temp_log_dir):
        auth = BusAuth()
        bus = MessageBus(log_dir=temp_log_dir, auth=auth)
        yield bus, auth
        await bus.close()

    @pytest.fixture
    async def no_auth_bus(self, temp_log_dir):
        bus = MessageBus(log_dir=temp_log_dir)
        yield bus
        await bus.close()

    @pytest.mark.asyncio
    async def test_auto_sign_on_send(self, auth_bus):
        """Bus auto-signs messages from registered sources."""
        bus, auth = auth_bus
        auth.generate_token("brain_a")

        received = []
        bus.subscribe("target", lambda m: received.append(m))

        msg = BusMessage(
            type=MessageType.EVENT,
            source="brain_a",
            target="target",
            payload={"data": 1},
        )
        assert msg.signature is None

        await bus.send(msg)
        await asyncio.sleep(0.05)

        assert msg.signature is not None
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_drop_unsigned_message(self, auth_bus):
        """Auth-enabled bus drops messages with no signature and no token."""
        bus, auth = auth_bus
        # Don't register "stranger" — no token

        received = []
        bus.subscribe("target", lambda m: received.append(m))

        msg = BusMessage(
            type=MessageType.EVENT,
            source="stranger",
            target="target",
            payload={},
        )

        await bus.send(msg)
        await asyncio.sleep(0.05)

        # Message should be dropped (no token → auto-sign fails → signature=None → dropped)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_drop_invalid_signature(self, auth_bus):
        """Auth-enabled bus drops messages with invalid signature."""
        bus, auth = auth_bus
        auth.generate_token("brain_a")

        received = []
        bus.subscribe("target", lambda m: received.append(m))

        msg = BusMessage(
            type=MessageType.EVENT,
            source="brain_a",
            target="target",
            payload={},
            signature="bad_signature",
        )

        await bus.send(msg)
        await asyncio.sleep(0.05)

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_no_auth_bus_ignores_signature(self, no_auth_bus):
        """Bus without auth delivers all messages regardless of signature."""
        bus = no_auth_bus
        received = []
        bus.subscribe("target", lambda m: received.append(m))

        msg = BusMessage(
            type=MessageType.EVENT,
            source="brain_a",
            target="target",
            payload={"x": 1},
        )

        await bus.send(msg)
        await asyncio.sleep(0.05)

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_broadcast_with_auth(self, auth_bus):
        """Broadcast messages are auto-signed and delivered."""
        bus, auth = auth_bus
        auth.generate_token("announcer")

        received_a = []
        received_b = []
        bus.subscribe("a", lambda m: received_a.append(m))
        bus.subscribe("b", lambda m: received_b.append(m))

        msg = BusMessage(
            type=MessageType.EVENT,
            source="announcer",
            target="*",
            payload={"event": "hello"},
        )

        await bus.send(msg)
        await asyncio.sleep(0.05)

        assert len(received_a) == 1
        assert len(received_b) == 1

    @pytest.mark.asyncio
    async def test_signature_field_on_message(self):
        """BusMessage supports optional signature field."""
        msg = BusMessage(
            type=MessageType.EVENT,
            source="test",
            target="test",
        )
        assert msg.signature is None

        msg2 = BusMessage(
            type=MessageType.EVENT,
            source="test",
            target="test",
            signature="abc123",
        )
        assert msg2.signature == "abc123"

    @pytest.mark.asyncio
    async def test_signature_in_log_dict(self):
        """to_log_dict includes the signature field."""
        msg = BusMessage(
            type=MessageType.EVENT,
            source="test",
            target="test",
            signature="sig_value",
        )
        d = msg.to_log_dict()
        assert d["signature"] == "sig_value"

        msg2 = BusMessage(type=MessageType.EVENT, source="test", target="test")
        d2 = msg2.to_log_dict()
        assert d2["signature"] is None
