"""Mock Text-to-Speech (TTS) implementation simulating Cartesia Sonic."""

import asyncio
import random
from typing import AsyncIterator


class MockTTS:
    """
    Mock Text-to-Speech service simulating Cartesia Sonic.
    
    Provides realistic synthesis simulation with:
    - High-quality neural voices
    - Streaming audio generation
    - Word-level timing synchronization
    - Multiple voice options
    - Emotional expression controls
    """
    
    def __init__(self, voice: str = "nova", speed: float = 1.0, pitch: float = 1.0):
        """
        Initialize mock TTS service.
        
        Args:
            voice: Voice name (e.g., "nova", "alloy", "echo", "fable")
            speed: Speech rate multiplier (0.5-2.0)
            pitch: Pitch adjustment multiplier (0.5-2.0)
        """
        self.voice = voice
        self.speed = max(0.5, min(2.0, speed))
        self.pitch = max(0.5, min(2.0, pitch))
        
        # Available voices with characteristics
        self._voices = {
            "nova": {"gender": "female", "age": "young_adult", "accent": "american"},
            "alloy": {"gender": "male", "age": "adult", "accent": "american"},
            "echo": {"gender": "male", "age": "middle_aged", "accent": "british"},
            "fable": {"gender": "female", "age": "adult", "accent": "british"},
            "onyx": {"gender": "male", "age": "adult", "accent": "american"},
            "shimmer": {"gender": "female", "age": "young_adult", "accent": "american"}
        }
        
        # Emotional expression presets
        self._emotions = {
            "neutral": {"energy": 0.5, "warmth": 0.5, "clarity": 0.9},
            "excited": {"energy": 0.9, "warmth": 0.7, "clarity": 0.8},
            "calm": {"energy": 0.3, "warmth": 0.8, "clarity": 0.9},
            "professional": {"energy": 0.6, "warmth": 0.4, "clarity": 1.0},
            "friendly": {"energy": 0.7, "warmth": 0.9, "clarity": 0.8},
            "serious": {"energy": 0.4, "warmth": 0.3, "clarity": 1.0}
        }
    
    async def synthesize(self, text: str, emotion: str = "neutral") -> bytes:
        """
        Synthesize speech from text.
        
        Args:
            text: Text to convert to speech
            emotion: Emotional expression preset
            
        Returns:
            Audio data as bytes (simulated)
        """
        # Estimate synthesis time based on text length and speed
        word_count = len(text.split())
        base_duration = word_count * 0.6  # ~0.6 seconds per word baseline
        actual_duration = base_duration / self.speed
        
        # Simulate processing time (faster than real-time)
        processing_time = min(actual_duration * 0.3, 2.0)
        await asyncio.sleep(processing_time)
        
        # Generate mock audio data (just bytes representing audio)
        audio_size = int(actual_duration * 22050 * 2)  # 22.05kHz, 16-bit
        audio_data = bytes([random.randint(0, 255) for _ in range(min(audio_size, 10000))])
        
        return audio_data
    
    async def stream(self, text: str, emotion: str = "neutral") -> AsyncIterator[dict]:
        """
        Stream synthesized speech with word-level timing.
        
        Args:
            text: Text to convert to speech
            emotion: Emotional expression preset
            
        Yields:
            Audio chunks with timing and word alignment data
        """
        words = text.split()
        if not words:
            return
        
        emotion_config = self._emotions.get(emotion, self._emotions["neutral"])
        current_time = 0.0
        
        for i, word in enumerate(words):
            # Calculate word duration based on length, speed, and emotion
            base_duration = len(word) * 0.08 + random.uniform(0.1, 0.3)
            duration = base_duration / self.speed
            
            # Adjust for emotion (excited = faster, calm = slower)
            if emotion == "excited":
                duration *= 0.85
            elif emotion == "calm":
                duration *= 1.2
            
            # Generate audio chunk for this word
            chunk_size = int(duration * 22050 * 2)
            audio_chunk = bytes([random.randint(0, 255) for _ in range(min(chunk_size, 1000))])
            
            yield {
                "audio": audio_chunk,
                "word": word,
                "start_time": current_time,
                "duration": duration,
                "emotion": emotion,
                "voice": self.voice,
                "confidence": random.uniform(0.95, 0.99),
                "is_final": i == len(words) - 1
            }
            
            current_time += duration
            
            # Simulate real-time generation delay
            await asyncio.sleep(duration * 0.1)  # 10% of audio duration
    
    def set_voice(self, voice: str) -> bool:
        """
        Change the active voice.
        
        Args:
            voice: Voice name
            
        Returns:
            True if voice was set successfully
        """
        if voice in self._voices:
            self.voice = voice
            return True
        return False
    
    def set_speed(self, speed: float) -> None:
        """
        Set speech rate.
        
        Args:
            speed: Speed multiplier (0.5-2.0)
        """
        self.speed = max(0.5, min(2.0, speed))
    
    def set_pitch(self, pitch: float) -> None:
        """
        Set pitch adjustment.
        
        Args:
            pitch: Pitch multiplier (0.5-2.0)
        """
        self.pitch = max(0.5, min(2.0, pitch))
    
    def get_available_voices(self) -> dict:
        """
        Get available voices and their characteristics.
        
        Returns:
            Dictionary of voice names and their properties
        """
        return self._voices.copy()
    
    def get_available_emotions(self) -> list[str]:
        """
        Get available emotional expression presets.
        
        Returns:
            List of emotion names
        """
        return list(self._emotions.keys())
    
    def estimate_duration(self, text: str) -> float:
        """
        Estimate speech duration for given text.
        
        Args:
            text: Text to estimate
            
        Returns:
            Estimated duration in seconds
        """
        word_count = len(text.split())
        base_duration = word_count * 0.6  # ~0.6 seconds per word
        return base_duration / self.speed
    
    def get_voice_info(self, voice: str = None) -> dict:
        """
        Get information about a voice.
        
        Args:
            voice: Voice name (uses current voice if None)
            
        Returns:
            Voice information dictionary
        """
        voice = voice or self.voice
        
        if voice not in self._voices:
            return {}
        
        return {
            "name": voice,
            "characteristics": self._voices[voice],
            "current_settings": {
                "speed": self.speed,
                "pitch": self.pitch
            },
            "supported_emotions": list(self._emotions.keys())
        }
    
    async def warm_up(self) -> dict:
        """
        Warm up the TTS engine for better performance.
        
        Returns:
            Warm-up results and performance metrics
        """
        # Simulate engine initialization
        await asyncio.sleep(0.5)
        
        return {
            "status": "ready",
            "voice": self.voice,
            "latency_ms": random.randint(50, 150),
            "quality": "high",
            "stream_capable": True,
            "max_text_length": 4096
        }