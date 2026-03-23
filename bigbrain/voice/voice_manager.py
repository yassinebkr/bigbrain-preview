"""Voice Manager - Coordinates STT→LLM→TTS pipeline for BigBrain."""

import asyncio
import os
from enum import Enum
from typing import AsyncIterator, Callable, Optional

from .stt import MockSTT
from .tts import MockTTS


def create_voice_manager(**kwargs) -> "VoiceManager":
    """
    Factory that auto-detects real vs mock voice services.
    
    Detection chain:
      1. DEEPGRAM_API_KEY + CARTESIA_API_KEY both set → real STT + TTS
      2. Only one key set → that service is real, other is mock
      3. No keys → full mock (demo mode)
    
    Also needs CARTESIA_VOICE_ID for real TTS (get from Cartesia dashboard).
    
    Returns:
        VoiceManager configured with the best available providers
    """
    deepgram_key = os.environ.get("DEEPGRAM_API_KEY", "")
    cartesia_key = os.environ.get("CARTESIA_API_KEY", "")
    cartesia_voice = os.environ.get("CARTESIA_VOICE_ID", "")

    stt = None
    tts = None

    if deepgram_key:
        try:
            from .deepgram_stt import DeepgramSTT
            stt = DeepgramSTT(api_key=deepgram_key)
            # Quick validation: key should start with expected prefix
            if not deepgram_key.strip():
                raise ValueError("DEEPGRAM_API_KEY is empty")
            print("🎤 Deepgram Nova-3 STT loaded (real)")
        except ImportError:
            print("⚠️  websockets not installed — Deepgram STT unavailable. pip install websockets")
        except Exception as e:
            print(f"⚠️  Deepgram STT failed to init: {e} — falling back to mock")

    if cartesia_key:
        try:
            from .cartesia_tts import CartesiaTTS
            tts = CartesiaTTS(api_key=cartesia_key, voice_id=cartesia_voice or None)
            print("🔊 Cartesia Sonic TTS loaded (real)")
        except Exception as e:
            print(f"⚠️  Cartesia TTS failed to init: {e} — falling back to mock")

    if stt is None:
        stt = MockSTT()
        print("🎤 STT: mock mode (set DEEPGRAM_API_KEY for real)")
    if tts is None:
        tts = MockTTS()
        print("🔊 TTS: mock mode (set CARTESIA_API_KEY for real)")

    return VoiceManager(stt=stt, tts=tts, **kwargs)


class VoiceState(str, Enum):
    """Voice manager states."""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking" 
    SPEAKING = "speaking"
    ERROR = "error"


class VoiceManager:
    """
    Manages the voice interaction pipeline for BigBrain.
    
    Coordinates between:
    - Speech-to-Text (STT) for user input
    - LLM processing for generating responses
    - Text-to-Speech (TTS) for audio output
    - Integration with Front Brain for conversation
    
    States:
    - idle: Ready for voice input
    - listening: Recording and transcribing user speech
    - thinking: Processing with LLM
    - speaking: Playing TTS response
    - error: Error state requiring attention
    """
    
    def __init__(
        self, 
        stt: Optional[MockSTT] = None,
        tts: Optional[MockTTS] = None,
        auto_listen: bool = True
    ):
        """
        Initialize voice manager.
        
        Checks DEEPGRAM_API_KEY and CARTESIA_API_KEY from environment.
        When keys are present, voice features are available.
        When missing, voice is disabled (mock-only).
        
        Args:
            stt: Speech-to-text service (creates default if None)
            tts: Text-to-speech service (creates default if None)
            auto_listen: Automatically resume listening after speaking
        """
        import os
        
        self.deepgram_key = os.environ.get("DEEPGRAM_API_KEY", "")
        self.cartesia_key = os.environ.get("CARTESIA_API_KEY", "")
        self.is_available = bool(self.deepgram_key and self.cartesia_key)
        
        self.stt = stt or MockSTT()
        self.tts = tts or MockTTS()
        self.auto_listen = auto_listen
        
        self.state = VoiceState.IDLE
        self.is_enabled = False
        self.current_session_id = None
        
        if self.is_available:
            # Configure STT/TTS with real API keys
            self.stt.api_key = self.deepgram_key
            self.tts.api_key = self.cartesia_key
        
        # Callbacks for integration with Front Brain
        self._on_transcription: Optional[Callable] = None
        self._on_response_needed: Optional[Callable] = None
        self._on_state_change: Optional[Callable] = None
        
        # Configuration
        self.wake_words = ["bigbrain", "big brain", "hey brain"]
        self.stop_words = ["stop", "cancel", "nevermind"]
        self.voice_activity_timeout = 3.0  # seconds
        
        # Statistics
        self.session_stats = {
            "sessions_started": 0,
            "words_transcribed": 0,
            "responses_generated": 0,
            "errors_encountered": 0,
            "average_response_time": 0.0
        }
    
    def enable_voice(self) -> None:
        """Enable voice interaction."""
        self.is_enabled = True
        self._set_state(VoiceState.IDLE)
        print("🎤 Voice interaction enabled")
    
    def disable_voice(self) -> None:
        """Disable voice interaction."""
        self.is_enabled = False
        if self.stt.is_active():
            self.stt.stop_listening()
        self._set_state(VoiceState.IDLE)
        print("🔇 Voice interaction disabled")
    
    def toggle_voice(self) -> bool:
        """
        Toggle voice interaction on/off.
        
        Returns:
            New enabled state
        """
        if self.is_enabled:
            self.disable_voice()
        else:
            self.enable_voice()
        return self.is_enabled
    
    async def start_listening(self) -> None:
        """Start listening for voice input."""
        if not self.is_enabled:
            return
        
        if self.state not in [VoiceState.IDLE, VoiceState.SPEAKING]:
            return
        
        self._set_state(VoiceState.LISTENING)
        self.current_session_id = f"voice_session_{self.session_stats['sessions_started']}"
        self.session_stats["sessions_started"] += 1
        
        try:
            async for result in self.stt.stream():
                if not self.is_enabled:
                    break
                
                if result.get("is_final"):
                    text = result.get("text", "").strip()
                    if text:
                        await self._handle_transcription(text, result)
                    break
                else:
                    # Handle interim results for real-time feedback
                    if self._on_transcription:
                        await self._on_transcription(result.get("text", ""), False)
        
        except Exception as e:
            self._set_state(VoiceState.ERROR)
            self.session_stats["errors_encountered"] += 1
            print(f"Voice error: {e}")
        
        finally:
            if self.state == VoiceState.LISTENING:
                self._set_state(VoiceState.IDLE)
    
    async def speak_text(self, text: str, emotion: str = "neutral") -> None:
        """
        Convert text to speech and play it.
        
        Args:
            text: Text to speak
            emotion: Emotional expression for speech
        """
        if not self.is_enabled:
            return
        
        self._set_state(VoiceState.SPEAKING)
        
        try:
            # Stream TTS for word-level timing
            async for chunk in self.tts.stream(text, emotion):
                if not self.is_enabled:
                    break
                
                # Simulate audio playback
                word = chunk.get("word", "")
                duration = chunk.get("duration", 0.1)
                
                # In a real implementation, you'd queue audio chunks for playback
                await asyncio.sleep(duration)
                
                # Notify listeners of current word being spoken
                if self._on_state_change:
                    await self._on_state_change(
                        self.state, 
                        {"current_word": word, "progress": chunk.get("start_time", 0)}
                    )
            
            self.session_stats["responses_generated"] += 1
            
        except Exception as e:
            self._set_state(VoiceState.ERROR)
            self.session_stats["errors_encountered"] += 1
            print(f"TTS error: {e}")
            return
        
        # Auto-resume listening if enabled
        if self.auto_listen and self.is_enabled:
            await asyncio.sleep(0.5)  # Brief pause
            await self.start_listening()
        else:
            self._set_state(VoiceState.IDLE)
    
    async def process_conversation_turn(self, user_input: str) -> Optional[str]:
        """
        Process a complete conversation turn: input → LLM → output.
        
        Args:
            user_input: User's text input
            
        Returns:
            Generated response text
        """
        if not self.is_enabled:
            return None
        
        self._set_state(VoiceState.THINKING)
        
        try:
            if self._on_response_needed:
                response = await self._on_response_needed(user_input)
                if response:
                    await self.speak_text(response)
                return response
            else:
                # Fallback response
                response = f"I heard you say: {user_input}"
                await self.speak_text(response)
                return response
        
        except Exception as e:
            self._set_state(VoiceState.ERROR)
            self.session_stats["errors_encountered"] += 1
            print(f"Conversation error: {e}")
            return None
    
    def set_transcription_callback(self, callback: Callable) -> None:
        """
        Set callback for transcription events.
        
        Args:
            callback: Function to call with (text, is_final) parameters
        """
        self._on_transcription = callback
    
    def set_response_callback(self, callback: Callable) -> None:
        """
        Set callback for generating responses.
        
        Args:
            callback: Function to call with user input, should return response text
        """
        self._on_response_needed = callback
    
    def set_state_change_callback(self, callback: Callable) -> None:
        """
        Set callback for state changes.
        
        Args:
            callback: Function to call with (new_state, extra_data) parameters
        """
        self._on_state_change = callback
    
    def get_status(self) -> dict:
        """
        Get current voice manager status.
        
        Returns:
            Status dictionary with state, configuration, and statistics
        """
        return {
            "enabled": self.is_enabled,
            "state": self.state.value,
            "current_session": self.current_session_id,
            "stt_active": self.stt.is_active(),
            "configuration": {
                "auto_listen": self.auto_listen,
                "wake_words": self.wake_words,
                "voice": self.tts.voice,
                "language": self.stt.language
            },
            "statistics": self.session_stats.copy()
        }
    
    def configure_stt(self, language: str = None, model: str = None) -> bool:
        """
        Configure STT settings.
        
        Args:
            language: Language code
            model: Model name
            
        Returns:
            True if configuration was successful
        """
        try:
            if language:
                self.stt.language = language
            if model:
                self.stt.model = model
            return True
        except Exception:
            return False
    
    def configure_tts(self, voice: str = None, speed: float = None, emotion: str = None) -> bool:
        """
        Configure TTS settings.
        
        Args:
            voice: Voice name
            speed: Speech rate
            emotion: Default emotion
            
        Returns:
            True if configuration was successful
        """
        try:
            if voice:
                self.tts.set_voice(voice)
            if speed:
                self.tts.set_speed(speed)
            return True
        except Exception:
            return False
    
    async def _handle_transcription(self, text: str, result: dict) -> None:
        """
        Handle final transcription result.
        
        Args:
            text: Transcribed text
            result: Full transcription result
        """
        self.session_stats["words_transcribed"] += len(text.split())
        
        # Check for stop words
        if any(stop_word in text.lower() for stop_word in self.stop_words):
            print(f"🛑 Voice interaction stopped by user")
            self.disable_voice()
            return
        
        # Notify callback
        if self._on_transcription:
            await self._on_transcription(text, True)
        
        # Process conversation turn
        await self.process_conversation_turn(text)
    
    def _set_state(self, new_state: VoiceState) -> None:
        """
        Set voice manager state and notify listeners.
        
        Args:
            new_state: New state to set
        """
        old_state = self.state
        self.state = new_state
        
        if old_state != new_state and self._on_state_change:
            asyncio.create_task(self._on_state_change(new_state, {}))
    
    async def warm_up(self) -> dict:
        """
        Warm up voice services for better performance.
        
        Returns:
            Warm-up results
        """
        stt_ready = True  # STT doesn't need warm-up
        tts_result = await self.tts.warm_up()
        
        return {
            "stt_ready": stt_ready,
            "tts_ready": tts_result.get("status") == "ready",
            "latency_estimate_ms": tts_result.get("latency_ms", 100),
            "voice_manager_ready": True
        }