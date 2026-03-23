"""
Real Deepgram Nova-3 STT — streaming speech-to-text via WebSocket.

Protocol:
  1. Open WebSocket to wss://api.deepgram.com/v1/listen
  2. Send raw audio bytes (16kHz, 16-bit, mono)
  3. Receive JSON transcription events (interim + final)
  4. Send empty byte b"" or close to signal end-of-speech

Requires: DEEPGRAM_API_KEY environment variable
Docs: https://developers.deepgram.com/docs/getting-started-with-live-streaming-audio
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

log = logging.getLogger("bigbrain.voice.stt")

# WebSocket URL with query params for Nova-3
_WS_BASE = "wss://api.deepgram.com/v1/listen"
_DEFAULT_PARAMS = {
    "model": "nova-3",
    "language": "en-US",
    "punctuate": "true",
    "interim_results": "true",
    "endpointing": "300",          # ms of silence → final result
    "vad_events": "true",          # voice activity detection
    "smart_format": "true",        # numbers, dates, etc.
    "encoding": "linear16",
    "sample_rate": "16000",
    "channels": "1",
}


class DeepgramSTT:
    """
    Real speech-to-text using Deepgram Nova-3 WebSocket streaming.

    Usage:
        stt = DeepgramSTT(api_key="dg-...")
        
        async for result in stt.stream_microphone():
            if result["is_final"]:
                print(f"Final: {result['text']}")
            else:
                print(f"Interim: {result['text']}")
    """

    def __init__(
        self,
        api_key: str,
        language: str = "en-US",
        model: str = "nova-3",
    ):
        """
        Initialize Deepgram STT.
        
        Args:
            api_key: Deepgram API key (starts with "dg-" or similar)
            language: BCP-47 language code
            model: Deepgram model name (nova-3, nova-2, enhanced, base)
        """
        # TODO 1: Store parameters
        #   self.api_key = api_key
        #   self.language = language
        #   self.model = model
        #   self.is_listening = False
        #   self._ws = None  (will hold the websocket connection)
        raise NotImplementedError("TODO 1: Store parameters")

    def _build_ws_url(self) -> str:
        """
        Build the WebSocket URL with query parameters.
        
        Starts from _WS_BASE, overrides model and language from self,
        then joins all _DEFAULT_PARAMS as ?key=value&key=value.
        
        Returns:
            Full WebSocket URL string
        """
        # TODO 2: Build URL
        #   params = dict(_DEFAULT_PARAMS)
        #   params["model"] = self.model
        #   params["language"] = self.language
        #   query = "&".join(f"{k}={v}" for k, v in params.items())
        #   return f"{_WS_BASE}?{query}"
        raise NotImplementedError("TODO 2: Build WebSocket URL")

    async def stream(self, audio_source: AsyncIterator[bytes] | None = None) -> AsyncIterator[dict]:
        """
        Stream transcription results from audio input.
        
        If audio_source is None, uses microphone via sounddevice.
        Otherwise, consumes the provided async iterator of audio chunks.
        
        Each yielded dict has:
            - text: str — transcribed text
            - is_final: bool — True if this is a final result
            - confidence: float — 0.0 to 1.0
            - words: list[dict] — word-level timing [{word, start, end, confidence}]
            - language: str — detected language
        
        Protocol:
            1. Connect WebSocket with Authorization header
            2. Start two concurrent tasks:
               a) sender: reads audio chunks, sends to WS
               b) receiver: reads JSON from WS, yields results
            3. When audio ends, send close signal
            4. Yield remaining results, close WS
        
        Args:
            audio_source: async iterator yielding raw audio bytes (16kHz, 16-bit, mono)
                          or None to use microphone
        """
        # TODO 3: Implement WebSocket streaming
        #
        # Use the `websockets` library:
        #   import websockets
        #
        #   url = self._build_ws_url()
        #   headers = {"Authorization": f"Token {self.api_key}"}
        #
        #   async with websockets.connect(url, extra_headers=headers) as ws:
        #       self._ws = ws
        #       self.is_listening = True
        #
        #       # If no audio_source, create one from microphone
        #       if audio_source is None:
        #           audio_source = self._microphone_stream()
        #
        #       # Sender task: forward audio to Deepgram
        #       async def sender():
        #           async for chunk in audio_source:
        #               if not self.is_listening:
        #                   break
        #               await ws.send(chunk)
        #           # Signal end of audio
        #           await ws.send(b"")
        #
        #       # Start sender in background
        #       send_task = asyncio.create_task(sender())
        #
        #       # Receiver: read transcription results
        #       try:
        #           async for raw_msg in ws:
        #               data = json.loads(raw_msg)
        #               result = self._parse_result(data)
        #               if result:
        #                   yield result
        #       finally:
        #           send_task.cancel()
        #           self.is_listening = False
        #           self._ws = None
        raise NotImplementedError("TODO 3: WebSocket streaming")

    def _parse_result(self, data: dict) -> dict | None:
        """
        Parse a Deepgram WebSocket JSON message into our standard format.
        
        Deepgram sends messages like:
        {
            "type": "Results",
            "channel": {
                "alternatives": [{
                    "transcript": "hello world",
                    "confidence": 0.95,
                    "words": [
                        {"word": "hello", "start": 0.1, "end": 0.4, "confidence": 0.97},
                        {"word": "world", "start": 0.5, "end": 0.9, "confidence": 0.93}
                    ]
                }]
            },
            "is_final": true,
            "speech_final": true
        }
        
        Returns None for non-transcription messages (metadata, etc.)
        """
        # TODO 4: Parse Deepgram response
        #   if data.get("type") != "Results":
        #       return None
        #   
        #   channel = data.get("channel", {})
        #   alternatives = channel.get("alternatives", [])
        #   if not alternatives:
        #       return None
        #   
        #   best = alternatives[0]
        #   transcript = best.get("transcript", "").strip()
        #   if not transcript:
        #       return None
        #   
        #   return {
        #       "text": transcript,
        #       "is_final": data.get("is_final", False),
        #       "confidence": best.get("confidence", 0.0),
        #       "words": best.get("words", []),
        #       "language": self.language,
        #   }
        raise NotImplementedError("TODO 4: Parse Deepgram response")

    async def _microphone_stream(self, chunk_duration_ms: int = 100) -> AsyncIterator[bytes]:
        """
        Stream audio from the system microphone.
        
        Uses sounddevice library for cross-platform mic access.
        Yields raw PCM chunks (16kHz, 16-bit, mono).
        
        Args:
            chunk_duration_ms: Duration of each audio chunk in milliseconds
        """
        # TODO 5: Microphone capture
        #
        #   import sounddevice as sd
        #   import numpy as np
        #
        #   sample_rate = 16000
        #   chunk_samples = int(sample_rate * chunk_duration_ms / 1000)
        #   
        #   # Use an asyncio.Queue to bridge sounddevice callback → async iterator
        #   audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        #   
        #   def audio_callback(indata, frames, time_info, status):
        #       """Called by sounddevice for each audio chunk."""
        #       # Convert float32 → int16 PCM
        #       pcm = (indata[:, 0] * 32767).astype(np.int16).tobytes()
        #       audio_queue.put_nowait(pcm)
        #   
        #   with sd.InputStream(
        #       samplerate=sample_rate,
        #       channels=1,
        #       dtype="float32",
        #       blocksize=chunk_samples,
        #       callback=audio_callback,
        #   ):
        #       while self.is_listening:
        #           chunk = await audio_queue.get()
        #           yield chunk
        raise NotImplementedError("TODO 5: Microphone capture")

    def stop_listening(self) -> None:
        """Stop the current listening session."""
        self.is_listening = False
        # WebSocket will close naturally when sender stops

    def is_active(self) -> bool:
        """Check if STT is currently listening."""
        return self.is_listening

    def get_supported_languages(self) -> list[str]:
        """Deepgram Nova-3 supported languages (subset — full list at docs)."""
        return [
            "en-US", "en-GB", "en-AU", "en-IN",
            "es", "es-419", "fr", "fr-CA",
            "de", "it", "pt", "pt-BR",
            "ja", "ko", "zh", "zh-TW",
            "ru", "ar", "hi", "nl", "sv", "no", "da", "pl", "tr", "uk",
        ]
