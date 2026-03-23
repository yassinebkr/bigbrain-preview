"""
Real AssemblyAI STT — streaming speech-to-text via WebSocket (v3 API).

Protocol (v3):
  1. Connect to wss://streaming.assemblyai.com/v3/ws?params...
  2. Send raw audio bytes (16kHz, 16-bit, mono PCM)
  3. Receive JSON:  Begin, Turn (interim + final), Termination
  4. Send {"type": "Terminate"} to end session

Requires: ASSEMBLYAI_API_KEY environment variable
Docs: https://www.assemblyai.com/docs/guides/streaming
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator
from urllib.parse import urlencode

import websockets

log = logging.getLogger("bigbrain.voice.stt")

_WS_BASE = "wss://streaming.assemblyai.com/v3/ws"


class AssemblyAISTT:
    """
    Real speech-to-text using AssemblyAI v3 WebSocket streaming.

    Usage:
        stt = AssemblyAISTT(api_key="...")
        
        async for result in stt.stream():
            if result["is_final"]:
                print(f"Final: {result['text']}")
            else:
                print(f"Interim: {result['text']}")
    """

    def __init__(
        self,
        api_key: str,
        language: str = "en",
        model: str = "u3-rt-pro",
        min_turn_silence: int = 100,
        max_turn_silence: int = 1500,
    ):
        """
        Initialize AssemblyAI STT.

        Args:
            api_key: AssemblyAI API key
            language: Language code (en, es, fr, de, etc.)
            model: Speech model — u3-rt-pro (best), universal-streaming-english,
                   universal-streaming-multilingual, whisper-rt
            min_turn_silence: Min silence (ms) before end-of-turn (100-2000)
            max_turn_silence: Max silence (ms) before forced end-of-turn (100-5000)
        """
        self.api_key = api_key
        self.language = language
        self.model = model
        self.min_turn_silence = min_turn_silence
        self.max_turn_silence = max_turn_silence
        self.is_listening = False
        self._ws = None

    def _build_ws_url(self) -> str:
        """Build WebSocket URL with query parameters."""
        params = {
            "sample_rate": 16000,
            "speech_model": self.model,
            "min_turn_silence": self.min_turn_silence,
            "max_turn_silence": self.max_turn_silence,
        }
        return f"{_WS_BASE}?{urlencode(params)}"

    async def stream(self, audio_source: AsyncIterator[bytes] | None = None) -> AsyncIterator[dict]:
        """
        Stream transcription results from audio input.

        If audio_source is None, uses microphone via sounddevice.
        Otherwise, consumes the provided async iterator of audio chunks.

        Each yielded dict has:
            - text: str — transcribed text
            - is_final: bool — True if end_of_turn
            - confidence: float — 0.0 to 1.0
            - words: list[dict] — word-level timing (if available)
            - language: str — language code

        Args:
            audio_source: async iterator yielding raw audio bytes (16kHz, 16-bit, mono)
                          or None to use microphone
        """
        url = self._build_ws_url()
        headers = {"Authorization": self.api_key}

        async with websockets.connect(url, additional_headers=headers) as ws:
            self._ws = ws
            self.is_listening = True

            # If no audio_source, create one from microphone
            if audio_source is None:
                audio_source = self._microphone_stream()

            # Sender task: forward audio to AssemblyAI
            async def sender():
                try:
                    async for chunk in audio_source:
                        if not self.is_listening:
                            break
                        await ws.send(chunk)
                except asyncio.CancelledError:
                    pass
                # Signal end of session
                try:
                    await ws.send(json.dumps({"type": "Terminate"}))
                except Exception:
                    pass

            send_task = asyncio.create_task(sender())

            # Receiver: read transcription results
            try:
                async for raw_msg in ws:
                    if isinstance(raw_msg, bytes):
                        continue  # Skip binary frames (shouldn't happen)
                    data = json.loads(raw_msg)
                    result = self._parse_result(data)
                    if result is not None:
                        yield result
                        if result["is_final"]:
                            # Got a complete turn — stop listening for this cycle
                            break
                    elif data.get("type") == "Termination":
                        break
            finally:
                self.is_listening = False
                send_task.cancel()
                try:
                    await send_task
                except asyncio.CancelledError:
                    pass
                self._ws = None

    def _parse_result(self, data: dict) -> dict | None:
        """
        Parse an AssemblyAI v3 WebSocket message into our standard format.

        AssemblyAI v3 sends:
        {
            "type": "Turn",
            "transcript": "hello world",
            "end_of_turn": true,
            "words": [{"text": "hello", "start": 100, "end": 400, "confidence": 0.97}, ...]
        }

        Returns None for non-Turn messages (Begin, Termination, etc.)
        """
        msg_type = data.get("type", "")

        if msg_type != "Turn":
            return None

        transcript = data.get("transcript", "").strip()
        if not transcript:
            return None

        end_of_turn = data.get("end_of_turn", False)

        # Parse word-level timing if available
        words = []
        for w in data.get("words", []):
            words.append({
                "word": w.get("text", ""),
                "start": w.get("start", 0) / 1000.0,  # ms → seconds
                "end": w.get("end", 0) / 1000.0,
                "confidence": w.get("confidence", 0.0),
            })

        return {
            "text": transcript,
            "is_final": end_of_turn,
            "confidence": words[-1]["confidence"] if words else 0.9,
            "words": words,
            "language": self.language,
        }

    async def _microphone_stream(self, chunk_duration_ms: int = 50) -> AsyncIterator[bytes]:
        """
        Stream audio from the system microphone.

        Uses sounddevice for cross-platform mic access.
        Yields raw PCM chunks (16kHz, 16-bit, mono).

        Args:
            chunk_duration_ms: Duration of each audio chunk in milliseconds.
                               50ms = 800 samples (AssemblyAI recommended)
        """
        import sounddevice as sd
        import numpy as np

        sample_rate = 16000
        chunk_samples = int(sample_rate * chunk_duration_ms / 1000)

        audio_queue: asyncio.Queue[bytes] = asyncio.Queue()

        def audio_callback(indata, frames, time_info, status):
            """Called by sounddevice for each audio chunk."""
            pcm = (indata[:, 0] * 32767).astype(np.int16).tobytes()
            audio_queue.put_nowait(pcm)

        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            blocksize=chunk_samples,
            callback=audio_callback,
        ):
            while self.is_listening:
                chunk = await audio_queue.get()
                yield chunk

    def stop_listening(self) -> None:
        """Stop the current listening session."""
        self.is_listening = False

    def is_active(self) -> bool:
        """Check if STT is currently listening."""
        return self.is_listening

    def get_supported_languages(self) -> list[str]:
        """AssemblyAI supported languages."""
        return [
            "en", "es", "fr", "de", "it", "pt", "nl",
            "ja", "ko", "zh", "ru", "ar", "hi",
            "sv", "no", "da", "pl", "tr", "uk", "fi",
        ]
