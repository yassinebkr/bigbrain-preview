"""Mock Speech-to-Text (STT) implementation simulating Deepgram Nova-3."""

import asyncio
import random
from typing import AsyncIterator


class MockSTT:
    """
    Mock Speech-to-Text service simulating Deepgram Nova-3.
    
    Provides realistic transcription simulation with:
    - Partial results (interim transcriptions)
    - Final results with punctuation
    - Word-level timing
    - Confidence scores
    - Real-time streaming simulation
    """
    
    def __init__(self, language: str = "en-US", model: str = "nova-3"):
        """
        Initialize mock STT service.
        
        Args:
            language: Language code (e.g., "en-US", "es", "fr")
            model: Model name (e.g., "nova-3", "whisper", "enhanced")
        """
        self.language = language
        self.model = model
        self.is_listening = False
        
        # Sample phrases for realistic demo
        self._sample_phrases = [
            "hello bigbrain can you help me with a coding task",
            "I need to analyze some data and create a report",
            "what's the status of the current project",
            "can you research machine learning best practices",
            "help me write a python function for data processing",
            "show me the focus mode and workspace status",
            "I want to switch to deep focus mode",
            "run a test on the python brain system",
            "create a new task for the orchestrator",
            "what are the recent bus messages and events"
        ]
        
        # Common words and phrases for partial results
        self._partial_words = [
            "can", "you", "help", "me", "with", "a", "the", "and", "or", "but",
            "hello", "hi", "please", "thank", "thanks", "okay", "sure", "yes", "no"
        ]
    
    async def transcribe(self, audio_chunk: bytes) -> dict:
        """
        Transcribe a single audio chunk.
        
        Args:
            audio_chunk: Raw audio data (simulated)
            
        Returns:
            Transcription result with text, confidence, and timing
        """
        # Simulate processing delay
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        # Select a random phrase for simulation
        phrase = random.choice(self._sample_phrases)
        
        return {
            "text": phrase,
            "confidence": random.uniform(0.85, 0.98),
            "is_final": True,
            "language": self.language,
            "duration": len(audio_chunk) / 16000 if audio_chunk else 2.5,  # Assume 16kHz sample rate
            "words": self._generate_word_timings(phrase)
        }
    
    async def stream(self) -> AsyncIterator[dict]:
        """
        Stream real-time transcription results.
        
        Yields:
            Transcription results with partial and final text
        """
        if self.is_listening:
            return
        
        self.is_listening = True
        
        try:
            # Simulate a conversation session
            phrase = random.choice(self._sample_phrases)
            words = phrase.split()
            
            current_text = ""
            
            # Stream partial results as words are "spoken"
            for i, word in enumerate(words):
                if not self.is_listening:
                    break
                
                current_text += (" " if current_text else "") + word
                
                # Sometimes yield partial interim results
                if i > 0 and random.random() < 0.3:
                    yield {
                        "text": current_text + "...",
                        "confidence": random.uniform(0.6, 0.8),
                        "is_final": False,
                        "interim": True,
                        "language": self.language
                    }
                
                # Delay between words
                await asyncio.sleep(random.uniform(0.2, 0.5))
            
            # Yield final result
            yield {
                "text": current_text,
                "confidence": random.uniform(0.88, 0.97),
                "is_final": True,
                "interim": False,
                "language": self.language,
                "duration": len(words) * 0.4,  # Estimate duration
                "words": self._generate_word_timings(current_text)
            }
            
            # Simulate end of speech detection
            await asyncio.sleep(0.5)
            
        finally:
            self.is_listening = False
    
    def start_listening(self) -> None:
        """Start listening for audio input."""
        self.is_listening = True
    
    def stop_listening(self) -> None:
        """Stop listening for audio input."""
        self.is_listening = False
    
    def is_active(self) -> bool:
        """Check if STT is currently listening."""
        return self.is_listening
    
    def get_supported_languages(self) -> list[str]:
        """Get list of supported language codes."""
        return [
            "en-US", "en-GB", "en-AU", "en-CA",
            "es", "es-MX", "es-AR",
            "fr", "fr-CA",
            "de", "it", "pt", "pt-BR",
            "ja", "ko", "zh", "zh-CN",
            "ru", "ar", "hi", "nl", "sv", "no", "da"
        ]
    
    def _generate_word_timings(self, text: str) -> list[dict]:
        """
        Generate word-level timing information.
        
        Args:
            text: Transcribed text
            
        Returns:
            List of word timing dictionaries
        """
        words = text.split()
        word_timings = []
        
        current_time = 0.0
        
        for word in words:
            # Estimate word duration based on length
            duration = max(0.2, len(word) * 0.08 + random.uniform(0.1, 0.2))
            
            word_timings.append({
                "word": word,
                "start": current_time,
                "end": current_time + duration,
                "confidence": random.uniform(0.85, 0.98),
                "speaker": 0  # Single speaker for now
            })
            
            current_time += duration + random.uniform(0.05, 0.15)  # Gap between words
        
        return word_timings
    
    async def calibrate_noise_level(self, duration_seconds: float = 2.0) -> dict:
        """
        Calibrate background noise level for better recognition.
        
        Args:
            duration_seconds: How long to sample background noise
            
        Returns:
            Calibration results
        """
        await asyncio.sleep(duration_seconds)
        
        # Simulate noise level measurement
        noise_level = random.uniform(-40, -20)  # dB
        snr_estimate = random.uniform(15, 30)    # Signal-to-noise ratio
        
        return {
            "noise_level_db": noise_level,
            "snr_estimate_db": snr_estimate,
            "quality": "excellent" if snr_estimate > 25 else "good" if snr_estimate > 15 else "fair",
            "recommended_sensitivity": 0.8 if snr_estimate > 20 else 0.6
        }