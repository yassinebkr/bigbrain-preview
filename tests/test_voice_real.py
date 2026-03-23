"""Tests for real Deepgram STT and Cartesia TTS implementations using mocks."""

import asyncio
import json
import os
import sys
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers for mocking async WebSocket iteration
# ---------------------------------------------------------------------------

class AsyncIterList:
    """Wraps a list of items into an async iterator (for mocking `async for msg in ws`)."""

    def __init__(self, items):
        self._items = list(items)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


def _make_mock_ws(messages, send=None):
    """Create a mock WS that yields `messages` via async for, with a mock send."""
    ws = MagicMock()
    ws.__aiter__ = lambda self: AsyncIterList(messages).__aiter__()
    # Make it work as `async for msg in ws:` by giving it __aiter__/__anext__
    # The trick: make the mock itself an async iterable
    _iter = AsyncIterList(messages)
    ws.__aiter__ = lambda: _iter.__aiter__()
    ws.__anext__ = lambda: _iter.__anext__()
    ws.send = send or AsyncMock()
    return ws


def _make_mock_ws_context(mock_ws):
    """Create an async context manager that returns mock_ws."""
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


class MockAsyncWS:
    """A proper mock WebSocket that supports `async for msg in ws:` and `await ws.send(data)`."""

    def __init__(self, messages):
        self._messages = list(messages)
        self._index = 0
        self._sent = []

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._messages):
            raise StopAsyncIteration
        msg = self._messages[self._index]
        self._index += 1
        return msg

    async def send(self, data):
        self._sent.append(data)


# ---------------------------------------------------------------------------
# DeepgramSTT tests
# ---------------------------------------------------------------------------


class TestDeepgramSTTInit:
    """Test DeepgramSTT initialization and parameter storage."""

    def test_init_stores_api_key(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="dg-test-key-123")
        assert stt.api_key == "dg-test-key-123"

    def test_init_stores_language(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k", language="de")
        assert stt.language == "de"

    def test_init_stores_model(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k", model="nova-2")
        assert stt.model == "nova-2"

    def test_init_defaults(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k")
        assert stt.language == "en-US"
        assert stt.model == "nova-3"
        assert stt.is_listening is False
        assert stt._ws is None

    def test_is_active_initially_false(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k")
        assert stt.is_active() is False

    def test_stop_listening(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k")
        stt.is_listening = True
        stt.stop_listening()
        assert stt.is_listening is False
        assert stt.is_active() is False

    def test_get_supported_languages(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k")
        langs = stt.get_supported_languages()
        assert "en-US" in langs
        assert "de" in langs
        assert isinstance(langs, list)


class TestDeepgramSTTBuildURL:
    """Test WebSocket URL construction."""

    def test_url_contains_base(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT, _WS_BASE
        stt = DeepgramSTT(api_key="k")
        url = stt._build_ws_url()
        assert url.startswith(_WS_BASE + "?")

    def test_url_contains_model(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k", model="nova-2")
        url = stt._build_ws_url()
        assert "model=nova-2" in url

    def test_url_contains_language(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k", language="fr")
        url = stt._build_ws_url()
        assert "language=fr" in url

    def test_url_contains_default_params(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k")
        url = stt._build_ws_url()
        assert "punctuate=true" in url
        assert "interim_results=true" in url
        assert "smart_format=true" in url
        assert "encoding=linear16" in url
        assert "sample_rate=16000" in url


class TestDeepgramSTTParseResult:
    """Test JSON response parsing."""

    def test_parse_valid_final_result(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k")
        data = {
            "type": "Results",
            "channel": {
                "alternatives": [{
                    "transcript": "hello world",
                    "confidence": 0.95,
                    "words": [
                        {"word": "hello", "start": 0.1, "end": 0.4, "confidence": 0.97},
                        {"word": "world", "start": 0.5, "end": 0.9, "confidence": 0.93},
                    ]
                }]
            },
            "is_final": True,
        }
        result = stt._parse_result(data)
        assert result is not None
        assert result["text"] == "hello world"
        assert result["is_final"] is True
        assert result["confidence"] == 0.95
        assert len(result["words"]) == 2
        assert result["language"] == "en-US"

    def test_parse_interim_result(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k")
        data = {
            "type": "Results",
            "channel": {
                "alternatives": [{
                    "transcript": "hello",
                    "confidence": 0.7,
                    "words": []
                }]
            },
            "is_final": False,
        }
        result = stt._parse_result(data)
        assert result is not None
        assert result["text"] == "hello"
        assert result["is_final"] is False

    def test_parse_non_results_type_returns_none(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k")
        data = {"type": "Metadata", "request_id": "abc"}
        assert stt._parse_result(data) is None

    def test_parse_empty_alternatives_returns_none(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k")
        data = {"type": "Results", "channel": {"alternatives": []}}
        assert stt._parse_result(data) is None

    def test_parse_empty_transcript_returns_none(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k")
        data = {
            "type": "Results",
            "channel": {"alternatives": [{"transcript": "", "confidence": 0.0}]},
            "is_final": True,
        }
        assert stt._parse_result(data) is None

    def test_parse_whitespace_transcript_returns_none(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k")
        data = {
            "type": "Results",
            "channel": {"alternatives": [{"transcript": "   ", "confidence": 0.0}]},
            "is_final": True,
        }
        assert stt._parse_result(data) is None

    def test_parse_missing_channel_returns_none(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k")
        data = {"type": "Results"}
        assert stt._parse_result(data) is None

    def test_parse_uses_configured_language(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k", language="es")
        data = {
            "type": "Results",
            "channel": {"alternatives": [{"transcript": "hola", "confidence": 0.9}]},
            "is_final": True,
        }
        result = stt._parse_result(data)
        assert result["language"] == "es"

    def test_parse_defaults_confidence_zero(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k")
        data = {
            "type": "Results",
            "channel": {"alternatives": [{"transcript": "test"}]},
        }
        result = stt._parse_result(data)
        assert result["confidence"] == 0.0

    def test_parse_defaults_is_final_false(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT
        stt = DeepgramSTT(api_key="k")
        data = {
            "type": "Results",
            "channel": {"alternatives": [{"transcript": "test", "confidence": 0.9}]},
        }
        result = stt._parse_result(data)
        assert result["is_final"] is False


class TestDeepgramSTTStream:
    """Test WebSocket streaming with mocked websockets."""

    @pytest.mark.asyncio
    async def test_stream_connects_with_correct_url_and_headers(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT

        mock_ws = MockAsyncWS([])

        async def mock_audio():
            yield b"\x00" * 320

        with patch("bigbrain.voice.deepgram_stt.websockets") as mock_websockets:
            mock_websockets.connect.return_value = _make_mock_ws_context(mock_ws)

            stt = DeepgramSTT(api_key="dg-mykey")
            results = []
            async for r in stt.stream(audio_source=mock_audio()):
                results.append(r)

            call_args = mock_websockets.connect.call_args
            url = call_args[0][0]
            headers = call_args[1].get("additional_headers", {})
            assert "wss://api.deepgram.com/v1/listen" in url
            assert headers.get("Authorization") == "Token dg-mykey"

    @pytest.mark.asyncio
    async def test_stream_yields_parsed_results(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT

        msg1 = json.dumps({
            "type": "Results",
            "channel": {"alternatives": [{"transcript": "hello", "confidence": 0.9, "words": []}]},
            "is_final": False,
        })
        msg2 = json.dumps({
            "type": "Results",
            "channel": {"alternatives": [{"transcript": "hello world", "confidence": 0.95, "words": []}]},
            "is_final": True,
        })

        mock_ws = MockAsyncWS([msg1, msg2])

        async def mock_audio():
            yield b"\x00" * 320

        with patch("bigbrain.voice.deepgram_stt.websockets") as mock_websockets:
            mock_websockets.connect.return_value = _make_mock_ws_context(mock_ws)

            stt = DeepgramSTT(api_key="k")
            results = []
            async for r in stt.stream(audio_source=mock_audio()):
                results.append(r)

            assert len(results) == 2
            assert results[0]["text"] == "hello"
            assert results[0]["is_final"] is False
            assert results[1]["text"] == "hello world"
            assert results[1]["is_final"] is True

    @pytest.mark.asyncio
    async def test_stream_skips_non_results_messages(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT

        msg_meta = json.dumps({"type": "Metadata", "request_id": "abc"})
        msg_result = json.dumps({
            "type": "Results",
            "channel": {"alternatives": [{"transcript": "test", "confidence": 0.8}]},
            "is_final": True,
        })

        mock_ws = MockAsyncWS([msg_meta, msg_result])

        async def mock_audio():
            yield b"\x00" * 320

        with patch("bigbrain.voice.deepgram_stt.websockets") as mock_websockets:
            mock_websockets.connect.return_value = _make_mock_ws_context(mock_ws)

            stt = DeepgramSTT(api_key="k")
            results = []
            async for r in stt.stream(audio_source=mock_audio()):
                results.append(r)

            assert len(results) == 1
            assert results[0]["text"] == "test"

    @pytest.mark.asyncio
    async def test_stream_sends_audio_and_empty_close(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT

        audio_chunk = b"\x01\x02" * 160

        # The receiver must wait long enough for the sender to send the audio
        # before it finishes iterating, since both run concurrently.
        class DelayedWS:
            def __init__(self):
                self._sent = []
                self._yielded = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._yielded:
                    raise StopAsyncIteration
                # Wait so sender task has time to send audio + close
                await asyncio.sleep(0.1)
                self._yielded = True
                return json.dumps({
                    "type": "Results",
                    "channel": {"alternatives": [{"transcript": "ok", "confidence": 0.9}]},
                    "is_final": True,
                })

            async def send(self, data):
                self._sent.append(data)

        mock_ws = DelayedWS()

        async def mock_audio():
            yield audio_chunk

        with patch("bigbrain.voice.deepgram_stt.websockets") as mock_websockets:
            mock_websockets.connect.return_value = _make_mock_ws_context(mock_ws)

            stt = DeepgramSTT(api_key="k")
            async for _ in stt.stream(audio_source=mock_audio()):
                pass

            # Sender should have sent audio chunk + empty bytes close signal
            assert audio_chunk in mock_ws._sent
            assert b"" in mock_ws._sent

    @pytest.mark.asyncio
    async def test_stream_sets_and_clears_listening_state(self):
        from bigbrain.voice.deepgram_stt import DeepgramSTT

        mock_ws = MockAsyncWS([])

        async def mock_audio():
            yield b"\x00"

        with patch("bigbrain.voice.deepgram_stt.websockets") as mock_websockets:
            mock_websockets.connect.return_value = _make_mock_ws_context(mock_ws)

            stt = DeepgramSTT(api_key="k")
            assert stt.is_listening is False

            async for _ in stt.stream(audio_source=mock_audio()):
                pass

            # After stream completes, should no longer be listening
            assert stt.is_listening is False
            assert stt._ws is None


class TestDeepgramSTTMicrophoneStream:
    """Test microphone stream with mocked sounddevice."""

    @pytest.mark.asyncio
    async def test_microphone_stream_setup(self):
        """Verify _microphone_stream configures sounddevice.InputStream correctly."""
        import numpy as np
        from bigbrain.voice.deepgram_stt import DeepgramSTT

        stt = DeepgramSTT(api_key="k")
        stt.is_listening = True

        captured_kwargs = {}

        class FakeInputStream:
            def __init__(self_, **kwargs):
                captured_kwargs.update(kwargs)

            def __enter__(self_):
                return self_

            def __exit__(self_, *args):
                return False

        mock_sd = MagicMock()
        mock_sd.InputStream = FakeInputStream

        # Pre-patch the module so the local import picks it up
        with patch.dict(sys.modules, {"sounddevice": mock_sd}):
            # Start the generator — this calls InputStream(...)
            gen = stt._microphone_stream(chunk_duration_ms=100)

            # Manually drive the async generator to the first yield point
            # We need to feed data through the callback, then read from the generator.
            try:
                # The generator enters `with sd.InputStream(...)` and then awaits queue.get()
                # We'll simulate the callback pushing data and then stop.
                task = asyncio.ensure_future(gen.__anext__())
                await asyncio.sleep(0.01)  # Let it enter the with block

                # Verify InputStream was called with correct params
                assert captured_kwargs.get("samplerate") == 16000
                assert captured_kwargs.get("channels") == 1
                assert captured_kwargs.get("dtype") == "float32"
                assert captured_kwargs.get("blocksize") == 1600  # 16000 * 100 / 1000
                assert "callback" in captured_kwargs

                # Simulate audio callback pushing data
                callback = captured_kwargs["callback"]
                fake_audio = np.zeros((1600, 1), dtype=np.float32)
                callback(fake_audio, 1600, None, None)

                # Now the generator should yield the chunk
                chunk = await asyncio.wait_for(task, timeout=1.0)
                assert isinstance(chunk, bytes)
                assert len(chunk) == 1600 * 2  # 1600 samples * 2 bytes (int16)

            finally:
                stt.is_listening = False
                await gen.aclose()


# ---------------------------------------------------------------------------
# CartesiaTTS tests
# ---------------------------------------------------------------------------


class TestCartesiaTTSInit:
    """Test CartesiaTTS initialization."""

    def test_init_stores_api_key(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS
        tts = CartesiaTTS(api_key="sk-cart-test")
        assert tts.api_key == "sk-cart-test"

    def test_init_stores_voice_id(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS
        tts = CartesiaTTS(api_key="k", voice_id="voice-123")
        assert tts.voice_id == "voice-123"
        assert tts.voice == "voice-123"

    def test_init_default_voice(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS
        tts = CartesiaTTS(api_key="k")
        assert tts.voice_id is None
        assert tts.voice == "default"

    def test_init_stores_model(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS
        tts = CartesiaTTS(api_key="k", model="sonic-2")
        assert tts.model == "sonic-2"

    def test_init_default_model(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS
        tts = CartesiaTTS(api_key="k")
        assert tts.model == "sonic"

    def test_init_output_format(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS, OUTPUT_FORMATS
        tts = CartesiaTTS(api_key="k", output_format="mp3")
        assert tts.output_format == OUTPUT_FORMATS["mp3"]

    def test_init_default_output_format(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS, OUTPUT_FORMATS
        tts = CartesiaTTS(api_key="k")
        assert tts.output_format == OUTPUT_FORMATS["pcm_16khz"]

    def test_init_unknown_output_format_fallback(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS, OUTPUT_FORMATS
        tts = CartesiaTTS(api_key="k", output_format="nonexistent")
        assert tts.output_format == OUTPUT_FORMATS["pcm_16khz"]

    def test_init_speed_clamped(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS
        tts_low = CartesiaTTS(api_key="k", speed=0.1)
        assert tts_low.speed == 0.5
        tts_high = CartesiaTTS(api_key="k", speed=5.0)
        assert tts_high.speed == 2.0

    def test_init_creates_httpx_client(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS
        tts = CartesiaTTS(api_key="sk-test")
        assert tts._client is not None
        assert "api.cartesia.ai" in str(tts._client.base_url)

    def test_init_httpx_client_headers(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS
        tts = CartesiaTTS(api_key="sk-test")
        headers = tts._client.headers
        assert headers.get("x-api-key") == "sk-test"
        assert headers.get("cartesia-version") == "2024-06-10"


class TestCartesiaTTSSetters:
    """Test set_voice, set_speed, estimate_duration."""

    def test_set_voice(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS
        tts = CartesiaTTS(api_key="k", voice_id="v1")
        tts.set_voice("v2")
        assert tts.voice_id == "v2"
        assert tts.voice == "v2"

    def test_set_speed(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS
        tts = CartesiaTTS(api_key="k")
        tts.set_speed(1.5)
        assert tts.speed == 1.5

    def test_set_speed_clamped_low(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS
        tts = CartesiaTTS(api_key="k")
        tts.set_speed(0.1)
        assert tts.speed == 0.5

    def test_set_speed_clamped_high(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS
        tts = CartesiaTTS(api_key="k")
        tts.set_speed(3.0)
        assert tts.speed == 2.0

    def test_estimate_duration(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS
        tts = CartesiaTTS(api_key="k", speed=1.0)
        duration = tts.estimate_duration("hello world test")
        assert abs(duration - 1.2) < 0.01

    def test_estimate_duration_with_speed(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS
        tts = CartesiaTTS(api_key="k", speed=2.0)
        duration = tts.estimate_duration("hello world test")
        assert abs(duration - 0.6) < 0.01


class TestCartesiaTTSSynthesize:
    """Test REST synthesis with mocked httpx."""

    @pytest.mark.asyncio
    async def test_synthesize_returns_audio_bytes(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        tts = CartesiaTTS(api_key="sk-test", voice_id="voice-abc")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"\x00\x01\x02\x03" * 100
        mock_response.raise_for_status = MagicMock()

        with patch.object(tts._client, "post", new_callable=AsyncMock, return_value=mock_response):
            audio = await tts.synthesize("Hello, how are you?")
            assert isinstance(audio, bytes)
            assert len(audio) == 400

    @pytest.mark.asyncio
    async def test_synthesize_sends_correct_payload(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS, OUTPUT_FORMATS

        tts = CartesiaTTS(api_key="sk-test", voice_id="voice-abc", model="sonic")
        mock_response = MagicMock()
        mock_response.content = b"\x00"
        mock_response.raise_for_status = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        with patch.object(tts._client, "post", mock_post):
            await tts.synthesize("Test text")

            call_args = mock_post.call_args
            assert call_args[0][0] == "/tts/bytes"
            payload = call_args[1]["json"]
            assert payload["transcript"] == "Test text"
            assert payload["model_id"] == "sonic"
            assert payload["voice"]["mode"] == "id"
            assert payload["voice"]["id"] == "voice-abc"
            assert payload["language"] == "en"
            assert payload["output_format"] == OUTPUT_FORMATS["pcm_16khz"]

    @pytest.mark.asyncio
    async def test_synthesize_override_voice_id(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        tts = CartesiaTTS(api_key="k", voice_id="default-voice")
        mock_response = MagicMock()
        mock_response.content = b"\x00"
        mock_response.raise_for_status = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        with patch.object(tts._client, "post", mock_post):
            await tts.synthesize("Hi", voice_id="override-voice")
            payload = mock_post.call_args[1]["json"]
            assert payload["voice"]["id"] == "override-voice"

    @pytest.mark.asyncio
    async def test_synthesize_no_voice_id_raises(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        tts = CartesiaTTS(api_key="k")
        with pytest.raises(ValueError, match="No voice_id"):
            await tts.synthesize("Hello")

    @pytest.mark.asyncio
    async def test_synthesize_http_error_raises(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        tts = CartesiaTTS(api_key="k", voice_id="v1")
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=MagicMock()
        )

        with patch.object(tts._client, "post", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(httpx.HTTPStatusError):
                await tts.synthesize("Hello")


class TestCartesiaTTSStream:
    """Test WebSocket streaming with mocked websockets."""

    @pytest.mark.asyncio
    async def test_stream_connects_with_correct_url(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        done_msg = json.dumps({"type": "done"})
        mock_ws = MockAsyncWS([done_msg])

        with patch("bigbrain.voice.cartesia_tts.websockets") as mock_websockets:
            mock_websockets.connect.return_value = _make_mock_ws_context(mock_ws)

            tts = CartesiaTTS(api_key="sk-test", voice_id="v1", model="sonic")
            async for _ in tts.stream("Hello"):
                pass

            call_args = mock_websockets.connect.call_args
            url = call_args[0][0]
            headers = call_args[1].get("additional_headers", {})
            assert "wss://api.cartesia.ai/tts/websocket" in url
            assert "model_id=sonic" in url
            assert "voice[id]=v1" in url
            assert headers.get("X-API-Key") == "sk-test"
            assert headers.get("Cartesia-Version") == "2024-06-10"

    @pytest.mark.asyncio
    async def test_stream_sends_synthesis_request(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        done_msg = json.dumps({"type": "done"})
        mock_ws = MockAsyncWS([done_msg])

        with patch("bigbrain.voice.cartesia_tts.websockets") as mock_websockets:
            mock_websockets.connect.return_value = _make_mock_ws_context(mock_ws)

            tts = CartesiaTTS(api_key="k", voice_id="v1")
            async for _ in tts.stream("Hello world"):
                pass

            assert len(mock_ws._sent) == 1
            payload = json.loads(mock_ws._sent[0])
            assert payload["transcript"] == "Hello world"
            assert payload["continue"] is False
            assert payload["context_id"] == "bigbrain"

    @pytest.mark.asyncio
    async def test_stream_yields_audio_chunks(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        audio_data = b"\x00\x01" * 16000
        done_msg = json.dumps({"type": "done"})
        mock_ws = MockAsyncWS([audio_data, done_msg])

        with patch("bigbrain.voice.cartesia_tts.websockets") as mock_websockets:
            mock_websockets.connect.return_value = _make_mock_ws_context(mock_ws)

            tts = CartesiaTTS(api_key="k", voice_id="v1")
            results = []
            async for chunk in tts.stream("Test"):
                results.append(chunk)

            assert len(results) == 2
            assert results[0]["audio"] == audio_data
            assert results[0]["is_final"] is False
            assert results[0]["duration"] > 0
            assert results[1]["is_final"] is True
            assert results[1]["audio"] == b""

    @pytest.mark.asyncio
    async def test_stream_handles_word_timing(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        word_msg = json.dumps({"word": "hello", "start": 0.0, "duration": 0.3})
        done_msg = json.dumps({"type": "done"})
        mock_ws = MockAsyncWS([word_msg, done_msg])

        with patch("bigbrain.voice.cartesia_tts.websockets") as mock_websockets:
            mock_websockets.connect.return_value = _make_mock_ws_context(mock_ws)

            tts = CartesiaTTS(api_key="k", voice_id="v1")
            results = []
            async for chunk in tts.stream("hello"):
                results.append(chunk)

            assert len(results) == 2
            assert results[0]["word"] == "hello"
            assert results[0]["start_time"] == 0.0
            assert results[0]["duration"] == 0.3
            assert results[0]["is_final"] is False

    @pytest.mark.asyncio
    async def test_stream_no_voice_id_raises(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        tts = CartesiaTTS(api_key="k")
        with pytest.raises(ValueError, match="No voice_id"):
            async for _ in tts.stream("Hello"):
                pass

    @pytest.mark.asyncio
    async def test_stream_audio_duration_calculation(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        audio_data = b"\x00" * 32000  # 32000 / (16000*2) = 1.0s
        done_msg = json.dumps({"type": "done"})
        mock_ws = MockAsyncWS([audio_data, done_msg])

        with patch("bigbrain.voice.cartesia_tts.websockets") as mock_websockets:
            mock_websockets.connect.return_value = _make_mock_ws_context(mock_ws)

            tts = CartesiaTTS(api_key="k", voice_id="v1", output_format="pcm_16khz")
            results = []
            async for chunk in tts.stream("Test"):
                results.append(chunk)

            assert abs(results[0]["duration"] - 1.0) < 0.001

    @pytest.mark.asyncio
    async def test_stream_multiple_audio_chunks_accumulate_time(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        chunk1 = b"\x00" * 16000  # 0.5s
        chunk2 = b"\x00" * 16000  # 0.5s
        done_msg = json.dumps({"type": "done"})
        mock_ws = MockAsyncWS([chunk1, chunk2, done_msg])

        with patch("bigbrain.voice.cartesia_tts.websockets") as mock_websockets:
            mock_websockets.connect.return_value = _make_mock_ws_context(mock_ws)

            tts = CartesiaTTS(api_key="k", voice_id="v1")
            results = []
            async for chunk in tts.stream("Test"):
                results.append(chunk)

            assert len(results) == 3
            assert results[0]["start_time"] == 0.0
            assert abs(results[0]["duration"] - 0.5) < 0.001
            assert abs(results[1]["start_time"] - 0.5) < 0.001
            assert abs(results[1]["duration"] - 0.5) < 0.001


class TestCartesiaTTSListVoices:
    """Test voice listing."""

    @pytest.mark.asyncio
    async def test_list_voices_returns_api_response(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        tts = CartesiaTTS(api_key="k", voice_id="v1")
        voice_data = [
            {"id": "v1", "name": "Nova", "language": "en"},
            {"id": "v2", "name": "Echo", "language": "en"},
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = voice_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(tts._client, "get", new_callable=AsyncMock, return_value=mock_response):
            voices = await tts.list_voices()
            assert len(voices) == 2
            assert voices[0]["name"] == "Nova"

    @pytest.mark.asyncio
    async def test_list_voices_calls_correct_endpoint(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        tts = CartesiaTTS(api_key="k", voice_id="v1")
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_get = AsyncMock(return_value=mock_response)
        with patch.object(tts._client, "get", mock_get):
            await tts.list_voices()
            mock_get.assert_called_once_with("/voices")


class TestCartesiaTTSWarmUp:
    """Test warm-up functionality."""

    @pytest.mark.asyncio
    async def test_warm_up_success(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        tts = CartesiaTTS(api_key="k", voice_id="v1")
        mock_response = MagicMock()
        mock_response.content = b"\x00"
        mock_response.raise_for_status = MagicMock()

        with patch.object(tts._client, "post", new_callable=AsyncMock, return_value=mock_response):
            result = await tts.warm_up()
            assert result["status"] == "ready"
            assert "latency_ms" in result
            assert result["voice"] == "v1"

    @pytest.mark.asyncio
    async def test_warm_up_error(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        tts = CartesiaTTS(api_key="k", voice_id="v1")

        with patch.object(tts._client, "post", new_callable=AsyncMock, side_effect=Exception("Connection refused")):
            result = await tts.warm_up()
            assert result["status"] == "error"
            assert "Connection refused" in result["error"]


class TestCartesiaTTSClose:
    """Test close functionality."""

    @pytest.mark.asyncio
    async def test_close_closes_client(self):
        from bigbrain.voice.cartesia_tts import CartesiaTTS

        tts = CartesiaTTS(api_key="k")
        tts._client.aclose = AsyncMock()
        await tts.close()
        tts._client.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# Factory / create_voice_manager tests
# ---------------------------------------------------------------------------


class TestCreateVoiceManager:
    """Test the create_voice_manager factory function."""

    def test_no_keys_returns_mock_providers(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("DEEPGRAM_API_KEY", "CARTESIA_API_KEY", "CARTESIA_VOICE_ID")}
        with patch.dict(os.environ, env, clear=True):
            from bigbrain.voice.voice_manager import create_voice_manager
            from bigbrain.voice.stt import MockSTT
            from bigbrain.voice.tts import MockTTS
            vm = create_voice_manager()
            assert isinstance(vm.stt, MockSTT)
            assert isinstance(vm.tts, MockTTS)

    def test_deepgram_key_only(self):
        env = {"DEEPGRAM_API_KEY": "dg-test"}
        with patch.dict(os.environ, env, clear=True):
            from bigbrain.voice.voice_manager import create_voice_manager
            from bigbrain.voice.deepgram_stt import DeepgramSTT
            from bigbrain.voice.tts import MockTTS
            vm = create_voice_manager()
            assert isinstance(vm.stt, DeepgramSTT)
            assert isinstance(vm.tts, MockTTS)

    def test_cartesia_key_only(self):
        env = {"CARTESIA_API_KEY": "sk-cart-test", "CARTESIA_VOICE_ID": "v1"}
        with patch.dict(os.environ, env, clear=True):
            from bigbrain.voice.voice_manager import create_voice_manager
            from bigbrain.voice.stt import MockSTT
            from bigbrain.voice.cartesia_tts import CartesiaTTS
            vm = create_voice_manager()
            assert isinstance(vm.stt, MockSTT)
            assert isinstance(vm.tts, CartesiaTTS)

    def test_both_keys_set(self):
        env = {
            "DEEPGRAM_API_KEY": "dg-test",
            "CARTESIA_API_KEY": "sk-cart-test",
            "CARTESIA_VOICE_ID": "v1",
        }
        with patch.dict(os.environ, env, clear=True):
            from bigbrain.voice.voice_manager import create_voice_manager
            from bigbrain.voice.deepgram_stt import DeepgramSTT
            from bigbrain.voice.cartesia_tts import CartesiaTTS
            vm = create_voice_manager()
            assert isinstance(vm.stt, DeepgramSTT)
            assert isinstance(vm.tts, CartesiaTTS)

    def test_cartesia_key_no_voice_id(self):
        env = {"CARTESIA_API_KEY": "sk-cart-test"}
        with patch.dict(os.environ, env, clear=True):
            from bigbrain.voice.voice_manager import create_voice_manager
            from bigbrain.voice.cartesia_tts import CartesiaTTS
            vm = create_voice_manager()
            assert isinstance(vm.tts, CartesiaTTS)
            assert vm.tts.voice_id is None
