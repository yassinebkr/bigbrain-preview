"""Tests for Voice Brain — fast conversational LLM for natural speech."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bigbrain.voice.voice_brain import VoiceBrain, VOICE_SYSTEM_PROMPT
from bigbrain.bus.message import BusMessage, MessageType, Priority


class MockVoiceLLM:
    """Mock LLM for voice brain tests."""

    def __init__(self, response="Sure thing, that's done."):
        self.response = response
        self.calls = []

    async def chat_complete(self, messages, model=None, stream=False, **kwargs):
        self.calls.append({"messages": messages, "model": model, "stream": stream, **kwargs})
        if stream:
            return self._stream()
        return self.response

    async def _stream(self):
        words = self.response.split()
        for i, word in enumerate(words):
            suffix = " " if i < len(words) - 1 else ""
            yield word + suffix

    async def complete(self, prompt, **kwargs):
        return self.response


@pytest.fixture
def mock_llm():
    return MockVoiceLLM()


@pytest.fixture
def voice_brain(mock_llm):
    return VoiceBrain(llm_provider=mock_llm, voice_model="test-model")


@pytest.fixture
def voice_brain_with_bus(mock_llm):
    bus = MagicMock()
    bus.subscribe = MagicMock()
    bus.unsubscribe = MagicMock()
    return VoiceBrain(llm_provider=mock_llm, voice_model="test-model", bus=bus)


# === Initialization ===

class TestVoiceBrainInit:
    def test_basic_init(self, voice_brain):
        assert voice_brain.voice_model == "test-model"
        assert voice_brain._running is False
        assert len(voice_brain._voice_history) == 0
        assert len(voice_brain._recent_events) == 0

    def test_default_model_picks_fast(self):
        """Voice brain should pick a fast model, not Opus."""
        mock_llm = MockVoiceLLM()
        vb = VoiceBrain(llm_provider=mock_llm)
        # Should NOT pick opus — voice needs speed
        assert "opus" not in vb.voice_model.lower()

    def test_oauth_provider_picks_sonnet(self):
        """OAuth provider → Sonnet (fast Claude model)."""
        # Create a class with the right __name__ to simulate OAuth provider
        class FakeOAuthProvider(MockVoiceLLM):
            pass
        FakeOAuthProvider.__name__ = "AnthropicOAuthProvider"
        mock_llm = FakeOAuthProvider()
        vb = VoiceBrain(llm_provider=mock_llm)
        assert "sonnet" in vb.voice_model.lower()

    def test_bus_subscription(self, voice_brain_with_bus):
        vb = voice_brain_with_bus
        assert vb.bus is not None


# === Start / Stop ===

class TestVoiceBrainLifecycle:
    @pytest.mark.asyncio
    async def test_start(self, voice_brain_with_bus):
        vb = voice_brain_with_bus
        await vb.start()
        assert vb._running is True
        vb.bus.subscribe.assert_called_once_with("*", vb._on_bus_event)

    @pytest.mark.asyncio
    async def test_stop(self, voice_brain_with_bus):
        vb = voice_brain_with_bus
        await vb.start()
        await vb.stop()
        assert vb._running is False
        vb.bus.unsubscribe.assert_called_once_with("*", vb._on_bus_event)

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self, voice_brain_with_bus):
        vb = voice_brain_with_bus
        await vb.start()
        await vb.start()  # Should not crash or double-subscribe
        assert vb._running is True
        assert vb.bus.subscribe.call_count == 1

    @pytest.mark.asyncio
    async def test_stop_without_start(self, voice_brain):
        await voice_brain.stop()  # Should not crash


# === Voice Response Generation ===

class TestVoiceResponses:
    @pytest.mark.asyncio
    async def test_respond_to_voice(self, voice_brain, mock_llm):
        response = await voice_brain.respond_to_voice("What's happening?")
        assert response == mock_llm.response
        assert len(mock_llm.calls) == 1
        assert mock_llm.calls[0]["model"] == "test-model"

    @pytest.mark.asyncio
    async def test_voice_uses_system_prompt(self, voice_brain, mock_llm):
        await voice_brain.respond_to_voice("Hello")
        messages = mock_llm.calls[0]["messages"]
        assert messages[0]["role"] == "system"
        assert "voice" in messages[0]["content"].lower()

    @pytest.mark.asyncio
    async def test_voice_history_accumulates(self, voice_brain, mock_llm):
        await voice_brain.respond_to_voice("First question")
        await voice_brain.respond_to_voice("Second question")
        assert len(voice_brain._voice_history) == 4  # 2 user + 2 assistant

    @pytest.mark.asyncio
    async def test_voice_history_trimmed(self, voice_brain, mock_llm):
        voice_brain._max_history = 4
        for i in range(10):
            await voice_brain.respond_to_voice(f"Question {i}")
        assert len(voice_brain._voice_history) <= 4

    @pytest.mark.asyncio
    async def test_max_tokens_is_low(self, voice_brain, mock_llm):
        """Voice responses should request short output."""
        await voice_brain.respond_to_voice("Tell me everything")
        assert mock_llm.calls[0]["max_tokens"] <= 200

    @pytest.mark.asyncio
    async def test_temperature_is_conversational(self, voice_brain, mock_llm):
        """Voice should be slightly creative for natural speech."""
        await voice_brain.respond_to_voice("Hey")
        assert mock_llm.calls[0].get("temperature", 0.7) >= 0.7

    @pytest.mark.asyncio
    async def test_error_handling(self, voice_brain):
        """Errors should produce a short spoken fallback, not crash."""
        voice_brain.llm_provider = MagicMock()
        voice_brain.llm_provider.chat_complete = AsyncMock(side_effect=Exception("API down"))
        response = await voice_brain.respond_to_voice("Hello")
        assert "snag" in response.lower() or "sorry" in response.lower()


# === Streaming Responses ===

class TestStreamingResponses:
    @pytest.mark.asyncio
    async def test_stream_response(self, voice_brain, mock_llm):
        mock_llm.response = "Sure thing. That's done."
        chunks = []
        async for chunk in voice_brain.stream_response("Do the thing"):
            chunks.append(chunk)
        full = "".join(chunks)
        assert "Sure" in full or "done" in full

    @pytest.mark.asyncio
    async def test_stream_updates_history(self, voice_brain, mock_llm):
        mock_llm.response = "Got it."
        async for _ in voice_brain.stream_response("Test"):
            pass
        assert len(voice_brain._voice_history) == 2  # user + assistant


# === Event Vocalization ===

class TestEventVocalization:
    @pytest.mark.asyncio
    async def test_vocalize_event(self, voice_brain, mock_llm):
        mock_llm.response = "Your fibonacci task just finished."
        result = await voice_brain.vocalize_event("PythonBrain completed fibonacci, output: 0 1 1 2 3")
        assert len(result) > 0
        assert mock_llm.calls[0]["max_tokens"] <= 100

    @pytest.mark.asyncio
    async def test_vocalize_result_success(self, voice_brain, mock_llm):
        mock_llm.response = "That ran perfectly. Output looks good."
        result = await voice_brain.vocalize_result(
            "calculate fibonacci",
            {"success": True, "data": {"stdout": "0 1 1 2 3", "exit_code": 0}},
        )
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_vocalize_result_failure(self, voice_brain, mock_llm):
        mock_llm.response = "That didn't work out."
        result = await voice_brain.vocalize_result(
            "run broken code",
            {"success": False, "data": {"error": "SyntaxError"}},
        )
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_vocalize_event_error_fallback(self, voice_brain):
        """If LLM fails, should still return something speakable."""
        voice_brain.llm_provider = MagicMock()
        voice_brain.llm_provider.chat_complete = AsyncMock(side_effect=Exception("fail"))
        result = await voice_brain.vocalize_event("task completed, output: 42")
        assert len(result) > 0  # Should fallback, not crash


# === Bus Event Tracking ===

class TestBusEventTracking:
    @pytest.mark.asyncio
    async def test_tracks_notable_events(self, voice_brain):
        voice_brain._running = True
        msg = BusMessage(
            type=MessageType.EVENT,
            source="python_brain",
            target="*",
            payload={"event": "brain.complete", "task_id": "123"},
        )
        await voice_brain._on_bus_event(msg)
        assert len(voice_brain._recent_events) == 1
        assert "python_brain" in voice_brain._recent_events[0]["source"]

    @pytest.mark.asyncio
    async def test_ignores_routine_events(self, voice_brain):
        voice_brain._running = True
        msg = BusMessage(
            type=MessageType.EVENT,
            source="python_brain",
            target="*",
            payload={"event": "brain.progress"},  # Routine, not notable
        )
        await voice_brain._on_bus_event(msg)
        assert len(voice_brain._recent_events) == 0

    @pytest.mark.asyncio
    async def test_ignores_own_events(self, voice_brain):
        voice_brain._running = True
        msg = BusMessage(
            type=MessageType.EVENT,
            source="voice_brain",
            target="*",
            payload={"event": "brain.complete"},
        )
        await voice_brain._on_bus_event(msg)
        assert len(voice_brain._recent_events) == 0

    @pytest.mark.asyncio
    async def test_event_limit(self, voice_brain):
        voice_brain._running = True
        voice_brain._max_events = 3
        for i in range(10):
            msg = BusMessage(
                type=MessageType.EVENT,
                source=f"brain_{i}",
                target="*",
                payload={"event": "brain.complete"},
            )
            await voice_brain._on_bus_event(msg)
        assert len(voice_brain._recent_events) <= 3

    @pytest.mark.asyncio
    async def test_events_feed_into_context(self, voice_brain, mock_llm):
        """Recent events should appear in the voice LLM's context."""
        voice_brain._running = True
        msg = BusMessage(
            type=MessageType.EVENT,
            source="python_brain",
            target="*",
            payload={"event": "brain.complete"},
        )
        await voice_brain._on_bus_event(msg)

        await voice_brain.respond_to_voice("What just happened?")
        messages = mock_llm.calls[0]["messages"]
        # Should have system prompt + event context + user message
        assert any("activity" in m.get("content", "").lower() for m in messages if m["role"] == "system")

    @pytest.mark.asyncio
    async def test_not_running_ignores_events(self, voice_brain):
        voice_brain._running = False
        msg = BusMessage(
            type=MessageType.EVENT,
            source="python_brain",
            target="*",
            payload={"event": "brain.complete"},
        )
        await voice_brain._on_bus_event(msg)
        assert len(voice_brain._recent_events) == 0


# === Status ===

class TestVoiceBrainStatus:
    def test_get_status(self, voice_brain):
        status = voice_brain.get_status()
        assert status["running"] is False
        assert status["model"] == "test-model"
        assert status["history_turns"] == 0
        assert status["recent_events"] == 0

    @pytest.mark.asyncio
    async def test_status_updates(self, voice_brain, mock_llm):
        await voice_brain.respond_to_voice("Hi")
        status = voice_brain.get_status()
        assert status["history_turns"] == 2  # user + assistant
