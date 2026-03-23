"""
Real Cartesia Sonic TTS — streaming text-to-speech via WebSocket.

Protocol (WebSocket mode):
  1. Connect to wss://api.cartesia.ai/tts/websocket
  2. Send JSON: {"text": "...", "voice": {"id": "..."}, "output_format": {...}}
  3. Receive binary audio chunks + JSON status messages
  4. Audio is PCM16 by default, can request mp3/opus

REST mode (simpler, non-streaming):
  POST https://api.cartesia.ai/tts/bytes
  Body: {"transcript": "...", "model_id": "sonic", "voice": {"mode": "id", "id": "..."}}
  Returns: raw audio bytes

Requires: CARTESIA_API_KEY environment variable
Docs: https://docs.cartesia.ai/api-reference
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

log = logging.getLogger("bigbrain.voice.tts")

_API_BASE = "https://api.cartesia.ai"
_WS_BASE = "wss://api.cartesia.ai/tts/websocket"

# Cartesia Sonic voices — curated selection
# Full catalog: GET https://api.cartesia.ai/voices
VOICES = {
    # You can list your own voices from the API or dashboard
    # Format: "friendly_name": "cartesia_voice_id"
    # Example IDs (get real ones from your Cartesia dashboard):
    # "nova": "a0e99841-438c-4a64-b679-ae501e7d6091",
}

# Output format presets
OUTPUT_FORMATS = {
    "pcm_16khz": {
        "container": "raw",
        "encoding": "pcm_s16le",
        "sample_rate": 16000,
    },
    "pcm_44khz": {
        "container": "raw",
        "encoding": "pcm_s16le",
        "sample_rate": 44100,
    },
    "mp3": {
        "container": "mp3",
        "encoding": "mp3",
        "sample_rate": 44100,
    },
}


class CartesiaTTS:
    """
    Real text-to-speech using Cartesia Sonic.
    
    Two modes:
    - synthesize(): REST call, returns full audio bytes (simple, higher latency)
    - stream(): WebSocket, yields audio chunks as they're generated (low latency)

    Usage:
        tts = CartesiaTTS(api_key="sk-cart-...")
        
        # Simple mode
        audio = await tts.synthesize("Hello, how are you?")
        
        # Streaming mode (low latency)
        async for chunk in tts.stream("Hello, how are you?"):
            play_audio(chunk["audio"])
    """

    def __init__(
        self,
        api_key: str,
        voice_id: str | None = None,
        model: str = "sonic",
        output_format: str = "pcm_16khz",
        speed: float = 1.0,
    ):
        """
        Initialize Cartesia TTS.
        
        Args:
            api_key: Cartesia API key
            voice_id: Voice UUID from Cartesia dashboard.
                      If None, must be set later or passed per-call.
            model: Model name ("sonic" is the fast one)
            output_format: Key from OUTPUT_FORMATS dict
            speed: Speech rate (0.5 - 2.0, normal = 1.0)
        """
        # TODO 1: Store parameters
        #   self.api_key = api_key
        #   self.voice_id = voice_id
        #   self.model = model
        #   self.output_format = OUTPUT_FORMATS.get(output_format, OUTPUT_FORMATS["pcm_16khz"])
        #   self.speed = max(0.5, min(2.0, speed))
        #   self.voice = voice_id or "default"  # friendly name for display
        #   self._client = httpx.AsyncClient(
        #       base_url=_API_BASE,
        #       headers={
        #           "X-API-Key": self.api_key,
        #           "Cartesia-Version": "2024-06-10",
        #           "Content-Type": "application/json",
        #       },
        #       timeout=30.0,
        #   )
        raise NotImplementedError("TODO 1: Store parameters")

    async def synthesize(self, text: str, voice_id: str | None = None) -> bytes:
        """
        Synthesize speech from text (REST mode — full audio returned at once).
        
        Higher latency than streaming but simpler to use.
        
        Args:
            text: Text to convert to speech
            voice_id: Override voice ID for this call
            
        Returns:
            Raw audio bytes in the configured format
        """
        # TODO 2: REST synthesis
        #
        #   vid = voice_id or self.voice_id
        #   if not vid:
        #       raise ValueError("No voice_id set — pass one or set in __init__")
        #
        #   response = await self._client.post(
        #       "/tts/bytes",
        #       json={
        #           "transcript": text,
        #           "model_id": self.model,
        #           "voice": {
        #               "mode": "id",
        #               "id": vid,
        #           },
        #           "language": "en",
        #           "output_format": self.output_format,
        #       },
        #   )
        #   response.raise_for_status()
        #   return response.content
        raise NotImplementedError("TODO 2: REST synthesis")

    async def stream(self, text: str, voice_id: str | None = None) -> AsyncIterator[dict]:
        """
        Stream synthesized speech via WebSocket (low latency).
        
        Connects to Cartesia's WebSocket endpoint, sends the text,
        and yields audio chunks as they're generated.
        
        Each yielded dict has:
            - audio: bytes — raw audio chunk
            - word: str — current word being spoken (if available)
            - start_time: float — timestamp in audio stream
            - duration: float — chunk duration in seconds
            - is_final: bool — True if this is the last chunk
        
        Protocol:
            1. Connect WebSocket with API key header
            2. Send JSON request with text + voice + format
            3. Receive messages:
               - Binary frames = audio data
               - Text frames = JSON status/word-timing
            4. "done" message signals end
        """
        # TODO 3: WebSocket streaming
        #
        #   import websockets
        #
        #   vid = voice_id or self.voice_id
        #   if not vid:
        #       raise ValueError("No voice_id set")
        #
        #   headers = {
        #       "X-API-Key": self.api_key,
        #       "Cartesia-Version": "2024-06-10",
        #   }
        #
        #   url = f"{_WS_BASE}?model_id={self.model}&voice[mode]=id&voice[id]={vid}"
        #
        #   async with websockets.connect(url, extra_headers=headers) as ws:
        #       # Send the synthesis request
        #       request = {
        #           "transcript": text,
        #           "continue": False,
        #           "context_id": "bigbrain",
        #           "output_format": self.output_format,
        #       }
        #       await ws.send(json.dumps(request))
        #
        #       current_time = 0.0
        #
        #       # Receive audio chunks
        #       async for msg in ws:
        #           if isinstance(msg, bytes):
        #               # Binary = audio data
        #               sample_rate = self.output_format.get("sample_rate", 16000)
        #               duration = len(msg) / (sample_rate * 2)  # 16-bit = 2 bytes/sample
        #               yield {
        #                   "audio": msg,
        #                   "word": "",
        #                   "start_time": current_time,
        #                   "duration": duration,
        #                   "is_final": False,
        #               }
        #               current_time += duration
        #           else:
        #               # Text = JSON status
        #               data = json.loads(msg)
        #               if data.get("type") == "done":
        #                   yield {
        #                       "audio": b"",
        #                       "word": "",
        #                       "start_time": current_time,
        #                       "duration": 0,
        #                       "is_final": True,
        #                   }
        #                   break
        #               # Word timing events, status updates, etc.
        #               if "word" in data:
        #                   yield {
        #                       "audio": b"",
        #                       "word": data["word"],
        #                       "start_time": data.get("start", current_time),
        #                       "duration": data.get("duration", 0),
        #                       "is_final": False,
        #                   }
        raise NotImplementedError("TODO 3: WebSocket streaming")

    async def list_voices(self) -> list[dict]:
        """
        List available voices from Cartesia API.
        
        Returns:
            List of voice dicts with id, name, description, language, etc.
        """
        # TODO 4: List voices
        #   response = await self._client.get("/voices")
        #   response.raise_for_status()
        #   return response.json()
        raise NotImplementedError("TODO 4: List voices")

    def set_voice(self, voice_id: str) -> None:
        """Set the active voice by ID."""
        self.voice_id = voice_id
        self.voice = voice_id

    def set_speed(self, speed: float) -> None:
        """Set speech rate (0.5-2.0)."""
        self.speed = max(0.5, min(2.0, speed))

    def estimate_duration(self, text: str) -> float:
        """Estimate speech duration for given text (rough: ~150 wpm)."""
        words = len(text.split())
        return (words / 150) * 60 / self.speed

    async def warm_up(self) -> dict:
        """
        Warm up the TTS service with a short synthesis call.
        Reduces first-call latency.
        """
        # TODO 5: Warm up
        #   try:
        #       start = time.monotonic()
        #       await self.synthesize("Hello.")
        #       latency = (time.monotonic() - start) * 1000
        #       return {"status": "ready", "latency_ms": latency, "voice": self.voice}
        #   except Exception as e:
        #       return {"status": "error", "error": str(e)}
        raise NotImplementedError("TODO 5: Warm up")

    async def close(self) -> None:
        """Close the HTTP client."""
        if hasattr(self, "_client"):
            await self._client.aclose()
