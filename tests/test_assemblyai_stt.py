"""Tests for AssemblyAI STT implementation using mocked WebSocket."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bigbrain.voice.assemblyai_stt import AssemblyAISTT


class MockWebSocket:
    """Mock WebSocket that simulates AssemblyAI v3 streaming responses."""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.sent = []
        self.closed = False
        self._idx = 0

    async def send(self, data):
        self.sent.append(data)

    def __aiter__(self):
        """Must be sync — async for calls __aiter__ then __anext__."""
        self._idx = 0
        return self

    async def __anext__(self):
        if self._idx >= len(self.responses):
            raise StopAsyncIteration
        msg = self.responses[self._idx]
        self._idx += 1
        await asyncio.sleep(0.01)
        return msg

    async def close(self):
        self.closed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


def _make_turn(transcript: str, end_of_turn: bool, words=None) -> str:
    """Create an AssemblyAI v3 Turn message."""
    data = {
        "type": "Turn",
        "transcript": transcript,
        "end_of_turn": end_of_turn,
    }
    if words:
        data["words"] = words
    return json.dumps(data)


def _make_begin(session_id: str = "test-session") -> str:
    return json.dumps({"type": "Begin", "id": session_id})


def _make_termination(duration: float = 5.0) -> str:
    return json.dumps({"type": "Termination", "audio_duration_seconds": duration})


class TestAssemblyAISTT:
    """Test AssemblyAI v3 streaming STT."""

    def test_init(self):
        stt = AssemblyAISTT(api_key="test-key")
        assert stt.api_key == "test-key"
        assert stt.model == "u3-rt-pro"
        assert stt.language == "en"
        assert not stt.is_listening

    def test_build_ws_url(self):
        stt = AssemblyAISTT(api_key="k", model="u3-rt-pro")
        url = stt._build_ws_url()
        assert "streaming.assemblyai.com/v3/ws" in url
        assert "speech_model=u3-rt-pro" in url
        assert "sample_rate=16000" in url
        assert "min_turn_silence=" in url
        assert "max_turn_silence=" in url

    def test_parse_turn_interim(self):
        stt = AssemblyAISTT(api_key="k")
        result = stt._parse_result({
            "type": "Turn",
            "transcript": "hello how",
            "end_of_turn": False,
        })
        assert result is not None
        assert result["text"] == "hello how"
        assert result["is_final"] is False

    def test_parse_turn_final(self):
        stt = AssemblyAISTT(api_key="k")
        result = stt._parse_result({
            "type": "Turn",
            "transcript": "hello how are you",
            "end_of_turn": True,
            "words": [
                {"text": "hello", "start": 100, "end": 400, "confidence": 0.97},
                {"text": "how", "start": 450, "end": 600, "confidence": 0.95},
                {"text": "are", "start": 650, "end": 750, "confidence": 0.96},
                {"text": "you", "start": 800, "end": 1000, "confidence": 0.98},
            ],
        })
        assert result is not None
        assert result["text"] == "hello how are you"
        assert result["is_final"] is True
        assert result["confidence"] == 0.98
        assert len(result["words"]) == 4
        assert result["words"][0]["word"] == "hello"
        assert result["words"][0]["start"] == 0.1  # ms → seconds

    def test_parse_begin_returns_none(self):
        stt = AssemblyAISTT(api_key="k")
        assert stt._parse_result({"type": "Begin", "id": "abc"}) is None

    def test_parse_termination_returns_none(self):
        stt = AssemblyAISTT(api_key="k")
        assert stt._parse_result({"type": "Termination"}) is None

    def test_parse_empty_transcript_returns_none(self):
        stt = AssemblyAISTT(api_key="k")
        assert stt._parse_result({"type": "Turn", "transcript": "", "end_of_turn": False}) is None
        assert stt._parse_result({"type": "Turn", "transcript": "   ", "end_of_turn": False}) is None

    @pytest.mark.asyncio
    async def test_stream_with_audio_source(self):
        """Test streaming with a provided audio source (no mic)."""
        stt = AssemblyAISTT(api_key="test-key")

        ws_responses = [
            _make_begin(),
            _make_turn("hello", False),
            _make_turn("hello how are you", True,
                       words=[
                           {"text": "hello", "start": 0, "end": 300, "confidence": 0.95},
                           {"text": "how", "start": 350, "end": 500, "confidence": 0.93},
                           {"text": "are", "start": 550, "end": 650, "confidence": 0.94},
                           {"text": "you", "start": 700, "end": 900, "confidence": 0.96},
                       ]),
        ]
        mock_ws = MockWebSocket(responses=ws_responses)

        # Provide a simple audio source
        async def fake_audio():
            for _ in range(5):
                yield b"\x00" * 1600
                await asyncio.sleep(0.01)

        with patch("bigbrain.voice.assemblyai_stt.websockets.connect", return_value=mock_ws):
            results = []
            async for result in stt.stream(audio_source=fake_audio()):
                results.append(result)

        # Should get interim + final
        assert len(results) == 2
        assert results[0]["text"] == "hello"
        assert results[0]["is_final"] is False
        assert results[1]["text"] == "hello how are you"
        assert results[1]["is_final"] is True

    @pytest.mark.asyncio
    async def test_stream_sends_terminate(self):
        """Audio source exhaustion sends Terminate message."""
        stt = AssemblyAISTT(api_key="test-key")

        ws_responses = [
            _make_begin(),
            _make_turn("test", True),
        ]
        mock_ws = MockWebSocket(responses=ws_responses)

        async def short_audio():
            yield b"\x00" * 800
            await asyncio.sleep(0.01)

        with patch("bigbrain.voice.assemblyai_stt.websockets.connect", return_value=mock_ws):
            async for _ in stt.stream(audio_source=short_audio()):
                pass

        # Should have sent audio + Terminate
        terminate_msgs = [s for s in mock_ws.sent if isinstance(s, str) and "Terminate" in s]
        assert len(terminate_msgs) >= 1

    @pytest.mark.asyncio
    async def test_stream_stops_on_stop_listening(self):
        """Calling stop_listening() breaks the audio stream."""
        stt = AssemblyAISTT(api_key="test-key")

        ws_responses = [
            _make_begin(),
            _make_turn("hello world", True),
        ]
        mock_ws = MockWebSocket(responses=ws_responses)

        async def slow_audio():
            for i in range(100):
                if not stt.is_listening:
                    break
                yield b"\x00" * 800
                await asyncio.sleep(0.01)

        with patch("bigbrain.voice.assemblyai_stt.websockets.connect", return_value=mock_ws):
            results = []
            async for result in stt.stream(audio_source=slow_audio()):
                results.append(result)
                stt.stop_listening()

        assert not stt.is_listening

    def test_supported_languages(self):
        stt = AssemblyAISTT(api_key="k")
        langs = stt.get_supported_languages()
        assert "en" in langs
        assert "fr" in langs
        assert "de" in langs

    def test_is_active(self):
        stt = AssemblyAISTT(api_key="k")
        assert not stt.is_active()
        stt.is_listening = True
        assert stt.is_active()

    def test_custom_model(self):
        stt = AssemblyAISTT(api_key="k", model="whisper-rt")
        url = stt._build_ws_url()
        assert "speech_model=whisper-rt" in url

    def test_custom_turn_silence(self):
        stt = AssemblyAISTT(api_key="k", min_turn_silence=200, max_turn_silence=2000)
        url = stt._build_ws_url()
        assert "min_turn_silence=200" in url
        assert "max_turn_silence=2000" in url
