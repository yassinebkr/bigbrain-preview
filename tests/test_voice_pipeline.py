"""Tests for the voice pipeline wiring: STT → VoiceBrain → TTS in TUI."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bigbrain.voice.stt import MockSTT
from bigbrain.voice.tts import MockTTS
from bigbrain.voice.voice_manager import VoiceManager, VoiceState
from bigbrain.voice.voice_brain import VoiceBrain
from bigbrain.llm.mock_provider import MockLLMProvider


# ── VoiceManager + VoiceBrain integration ────────────────────────────


@pytest.fixture
def llm_provider():
    return MockLLMProvider(token_delay_ms=0, realistic_responses=True)


@pytest.fixture
def voice_brain(llm_provider):
    return VoiceBrain(llm_provider=llm_provider)


@pytest.fixture
def voice_manager():
    return VoiceManager(stt=MockSTT(), tts=MockTTS(), auto_listen=False)


class TestVoicePipelineIntegration:
    """End-to-end voice pipeline: listen → transcribe → LLM → speak."""

    @pytest.mark.asyncio
    async def test_full_voice_turn(self, voice_manager, voice_brain):
        """STT produces text → VoiceBrain generates response → TTS streams audio."""
        await voice_brain.start()

        # 1. STT: get transcription
        voice_manager.enable_voice()
        final_text = None
        async for result in voice_manager.stt.stream():
            if result.get("is_final"):
                final_text = result["text"]
                break

        assert final_text, "STT should produce final text"

        # 2. VoiceBrain: generate spoken response
        response = await voice_brain.respond_to_voice(final_text)
        assert response, "VoiceBrain should return a response"
        assert isinstance(response, str)

        # 3. TTS: stream audio chunks
        chunks = []
        async for chunk in voice_manager.tts.stream(response):
            chunks.append(chunk)
            assert "audio" in chunk
            assert "word" in chunk
            if chunk.get("is_final"):
                break

        assert len(chunks) > 0, "TTS should produce audio chunks"
        assert chunks[-1].get("is_final"), "Last chunk should be final"

        await voice_brain.stop()

    @pytest.mark.asyncio
    async def test_voice_brain_streaming(self, voice_brain):
        """VoiceBrain stream_response yields sentence fragments."""
        await voice_brain.start()

        fragments = []
        async for fragment in voice_brain.stream_response("hello, how are you?"):
            fragments.append(fragment)

        assert len(fragments) > 0, "Should yield at least one fragment"
        full_text = "".join(fragments)
        assert len(full_text) > 0, "Combined fragments should have content"

        await voice_brain.stop()

    @pytest.mark.asyncio
    async def test_voice_brain_vocalize_event(self, voice_brain):
        """VoiceBrain converts bus events into natural speech."""
        await voice_brain.start()

        result = await voice_brain.vocalize_event(
            "PythonBrain completed fibonacci task, output: 0 1 1 2 3 5 8"
        )
        assert result, "Should produce spoken notification"
        assert isinstance(result, str)
        assert len(result) < 200, "Voice notifications should be brief"

        await voice_brain.stop()

    @pytest.mark.asyncio
    async def test_voice_brain_vocalize_result(self, voice_brain):
        """VoiceBrain summarizes task results for speech."""
        await voice_brain.start()

        result = await voice_brain.vocalize_result(
            "calculate fibonacci numbers",
            {
                "success": True,
                "data": {
                    "stdout": "0 1 1 2 3 5 8 13 21 34",
                    "stderr": "",
                    "exit_code": 0,
                },
            },
        )
        assert result, "Should produce spoken summary"
        assert isinstance(result, str)

        await voice_brain.stop()

    @pytest.mark.asyncio
    async def test_voice_manager_state_transitions(self, voice_manager):
        """Voice manager transitions through correct states."""
        assert voice_manager.state == VoiceState.IDLE
        assert not voice_manager.is_enabled

        voice_manager.enable_voice()
        assert voice_manager.is_enabled
        assert voice_manager.state == VoiceState.IDLE

        voice_manager.disable_voice()
        assert not voice_manager.is_enabled

    @pytest.mark.asyncio
    async def test_voice_toggle(self, voice_manager):
        """Toggle switches voice on and off."""
        assert not voice_manager.is_enabled

        result = voice_manager.toggle_voice()
        assert result is True
        assert voice_manager.is_enabled

        result = voice_manager.toggle_voice()
        assert result is False
        assert not voice_manager.is_enabled

    @pytest.mark.asyncio
    async def test_voice_callbacks_wired(self, voice_manager, voice_brain):
        """Callbacks fire correctly during voice pipeline."""
        transcriptions = []
        state_changes = []

        async def on_transcription(text, is_final):
            transcriptions.append((text, is_final))

        async def on_state_change(new_state, data):
            state_changes.append(new_state)

        voice_manager.set_transcription_callback(on_transcription)
        voice_manager.set_state_change_callback(on_state_change)

        voice_manager.enable_voice()
        await voice_manager.start_listening()

        # MockSTT produces transcription events → callback should fire
        assert len(transcriptions) > 0, "Transcription callback should have fired"
        # At least one final result
        finals = [t for t in transcriptions if t[1]]
        assert len(finals) > 0, "Should have at least one final transcription"

    @pytest.mark.asyncio
    async def test_stop_word_detection(self, voice_manager):
        """Stop words disable voice."""
        voice_manager.enable_voice()
        assert voice_manager.is_enabled

        # Simulate handling transcription with stop word
        await voice_manager._handle_transcription("stop", {"text": "stop", "is_final": True})
        assert not voice_manager.is_enabled, "Stop word should disable voice"

    @pytest.mark.asyncio
    async def test_voice_brain_history_management(self, voice_brain):
        """VoiceBrain keeps a short conversation history."""
        await voice_brain.start()

        # Send several messages
        for i in range(15):
            await voice_brain.respond_to_voice(f"message number {i}")

        # History should be trimmed to max_history (10)
        assert len(voice_brain._voice_history) <= voice_brain._max_history

        await voice_brain.stop()

    @pytest.mark.asyncio
    async def test_voice_brain_event_tracking(self, voice_brain):
        """VoiceBrain tracks notable bus events."""
        from bigbrain.bus.message import BusMessage, MessageType, Priority

        await voice_brain.start()

        # Simulate a notable bus event
        msg = BusMessage(
            type=MessageType.EVENT,
            source="python_brain",
            target="*",
            workspace="default",
            payload={"event": "brain.complete", "task_id": "abc123"},
            priority=Priority.NORMAL,
        )
        await voice_brain._on_bus_event(msg)

        assert len(voice_brain._recent_events) == 1
        assert "python_brain" in voice_brain._recent_events[0]["source"]

        await voice_brain.stop()

    @pytest.mark.asyncio
    async def test_voice_brain_ignores_own_events(self, voice_brain):
        """VoiceBrain doesn't track its own events."""
        from bigbrain.bus.message import BusMessage, MessageType, Priority

        await voice_brain.start()

        msg = BusMessage(
            type=MessageType.EVENT,
            source="voice_brain",
            target="*",
            workspace="default",
            payload={"event": "brain.complete"},
            priority=Priority.NORMAL,
        )
        await voice_brain._on_bus_event(msg)

        assert len(voice_brain._recent_events) == 0

        await voice_brain.stop()

    @pytest.mark.asyncio
    async def test_voice_manager_session_stats(self, voice_manager):
        """Voice manager tracks session statistics."""
        voice_manager.enable_voice()
        await voice_manager.start_listening()

        stats = voice_manager.session_stats
        assert stats["sessions_started"] >= 1
        assert stats["words_transcribed"] >= 0

    @pytest.mark.asyncio
    async def test_voice_manager_configure_stt(self, voice_manager):
        """STT configuration works."""
        assert voice_manager.configure_stt(language="fr")
        assert voice_manager.stt.language == "fr"

    @pytest.mark.asyncio
    async def test_voice_manager_configure_tts(self, voice_manager):
        """TTS configuration works."""
        assert voice_manager.configure_tts(speed=1.5)
        assert voice_manager.tts.speed == 1.5

    @pytest.mark.asyncio
    async def test_voice_manager_status(self, voice_manager):
        """Status report is comprehensive."""
        status = voice_manager.get_status()
        assert "enabled" in status
        assert "state" in status
        assert "configuration" in status
        assert "statistics" in status

    @pytest.mark.asyncio
    async def test_voice_brain_status(self, voice_brain):
        """VoiceBrain reports correct status."""
        status = voice_brain.get_status()
        assert status["running"] is False
        assert "model" in status

        await voice_brain.start()
        status = voice_brain.get_status()
        assert status["running"] is True

        await voice_brain.stop()
        status = voice_brain.get_status()
        assert status["running"] is False

    @pytest.mark.asyncio
    async def test_voice_brain_double_start_safe(self, voice_brain):
        """Starting VoiceBrain twice is safe."""
        await voice_brain.start()
        await voice_brain.start()  # Should not raise
        assert voice_brain._running is True
        await voice_brain.stop()

    @pytest.mark.asyncio
    async def test_voice_brain_double_stop_safe(self, voice_brain):
        """Stopping VoiceBrain twice is safe."""
        await voice_brain.start()
        await voice_brain.stop()
        await voice_brain.stop()  # Should not raise
        assert voice_brain._running is False


class TestMockSTTBehavior:
    """Verify MockSTT produces realistic data for testing."""

    @pytest.mark.asyncio
    async def test_stream_produces_final_result(self):
        stt = MockSTT()
        results = []
        async for result in stt.stream():
            results.append(result)
        
        assert len(results) > 0
        # Last result should be final
        assert results[-1]["is_final"] is True
        assert len(results[-1]["text"]) > 0

    @pytest.mark.asyncio
    async def test_stream_has_word_timings(self):
        stt = MockSTT()
        async for result in stt.stream():
            if result.get("is_final"):
                assert "words" in result
                assert len(result["words"]) > 0
                for w in result["words"]:
                    assert "word" in w
                    assert "start" in w
                    assert "end" in w
                break


class TestMockTTSBehavior:
    """Verify MockTTS produces realistic data for testing."""

    @pytest.mark.asyncio
    async def test_stream_produces_chunks(self):
        tts = MockTTS()
        chunks = []
        async for chunk in tts.stream("Hello, how are you today?"):
            chunks.append(chunk)

        assert len(chunks) > 0
        assert chunks[-1].get("is_final") is True

    @pytest.mark.asyncio
    async def test_stream_has_audio_bytes(self):
        tts = MockTTS()
        async for chunk in tts.stream("Test"):
            if chunk.get("audio"):
                assert isinstance(chunk["audio"], bytes)
                break

    @pytest.mark.asyncio
    async def test_synthesize_returns_bytes(self):
        tts = MockTTS()
        audio = await tts.synthesize("Hello world")
        assert isinstance(audio, bytes)
        assert len(audio) > 0

    @pytest.mark.asyncio
    async def test_duration_estimate(self):
        tts = MockTTS()
        d = tts.estimate_duration("one two three four five")
        assert d > 0
        assert d < 30  # Reasonable for 5 words
